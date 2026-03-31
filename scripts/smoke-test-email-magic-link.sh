#!/usr/bin/env bash
set -euo pipefail

###############################################################################
# Email Magic Link — Full E2E Smoke Test
#
# Runs the REAL end-to-end flow against a live dev server:
#   1. Health check
#   2. Send magic link email
#   3. Capture email content via test endpoint
#   4. Extract delivery confirmation from Resend response
#   5. Render email HTML to PNG screenshot
#   6. Verify token (auth flow: token → JWT session cookie → redirect)
#   7. Single-use rejection test (same token again)
#   8. Invalid token test (garbage token)
#
# All evidence is saved to evidence/email-magic-link/
###############################################################################

BASE_URL="${BASE_URL:-http://localhost:3001}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DIR="$PROJECT_ROOT/evidence/email-magic-link"

PASSED=0
FAILED=0
TOTAL=0
OUTPUT=""

# Ensure evidence directory exists
mkdir -p "$DIR"

log() {
  local msg="$1"
  echo "$msg"
  OUTPUT+="$msg"$'\n'
}

pass() {
  local label="$1"
  TOTAL=$((TOTAL + 1))
  PASSED=$((PASSED + 1))
  log "PASS: $label"
}

fail() {
  local label="$1"
  local detail="${2:-}"
  TOTAL=$((TOTAL + 1))
  FAILED=$((FAILED + 1))
  log "FAIL: $label"
  [ -n "$detail" ] && log "      Detail: $detail"
}

###############################################################################
# Step 0: Ensure app is running
###############################################################################
log ""
log "=== Email Magic Link E2E Smoke Test ==="
log "Base URL: $BASE_URL"
log "Evidence: $DIR"
log "Started:  $(date -u +%Y-%m-%dT%H:%M:%SZ)"
log ""

if ! curl -sf "$BASE_URL/api/health" > /dev/null 2>&1; then
  log "App not running on $BASE_URL — starting dev server..."
  cd "$PROJECT_ROOT/frontend"
  PORT=3001 npm run dev > /dev/null 2>&1 &
  DEV_PID=$!
  log "Dev server PID: $DEV_PID"

  # Wait up to 30s for health check
  for i in $(seq 1 30); do
    if curl -sf "$BASE_URL/api/health" > /dev/null 2>&1; then
      log "Dev server ready after ${i}s"
      break
    fi
    sleep 1
    if [ "$i" -eq 30 ]; then
      log "FATAL: Dev server failed to start within 30s"
      exit 1
    fi
  done
else
  log "App already running on $BASE_URL"
fi

###############################################################################
# Step 1: Health check
###############################################################################
log ""
log "--- Step 1: Health Check ---"

HEALTH_RESPONSE=$(curl -sf "$BASE_URL/api/health")
echo "$HEALTH_RESPONSE" | jq . > "$DIR/health.json"

if echo "$HEALTH_RESPONSE" | jq -e '.status == "ok"' > /dev/null 2>&1; then
  DB_STATUS=$(echo "$HEALTH_RESPONSE" | jq -r '.db // "unknown"')
  pass "Health check OK (db=$DB_STATUS)"
else
  fail "Health check" "Response: $HEALTH_RESPONSE"
fi

###############################################################################
# Step 2: Send magic link email
###############################################################################
log ""
log "--- Step 2: Send Magic Link ---"

SEND_RESPONSE=$(curl -sf -X POST "$BASE_URL/api/auth/send-magic-link" \
  -H "Content-Type: application/json" \
  -d '{"email":"roni.saroniemi@foxie.ai"}')
echo "$SEND_RESPONSE" | jq . > "$DIR/send-response.json"

if echo "$SEND_RESPONSE" | jq -e '.message == "Magic link sent."' > /dev/null 2>&1; then
  pass "Magic link sent to roni.saroniemi@foxie.ai"
else
  fail "Send magic link" "Response: $SEND_RESPONSE"
fi

###############################################################################
# Step 3: Capture email content via test endpoint
###############################################################################
log ""
log "--- Step 3: Capture Email Content ---"

# Small delay to ensure email capture is complete
sleep 0.5

EMAIL_CONTENT=$(curl -sf "$BASE_URL/api/test/auth/last-email")
echo "$EMAIL_CONTENT" | jq . > "$DIR/email-content.json"

if echo "$EMAIL_CONTENT" | jq -e '.html' > /dev/null 2>&1 && \
   echo "$EMAIL_CONTENT" | jq -e '.magicLinkUrl' > /dev/null 2>&1; then
  EMAIL_TO=$(echo "$EMAIL_CONTENT" | jq -r '.to')
  EMAIL_SUBJECT=$(echo "$EMAIL_CONTENT" | jq -r '.subject')
  log "  To: $EMAIL_TO"
  log "  Subject: $EMAIL_SUBJECT"
  pass "Email content captured (has HTML + magicLinkUrl)"
else
  fail "Capture email content" "Missing html or magicLinkUrl"
fi

###############################################################################
# Step 4: Extract delivery confirmation
###############################################################################
log ""
log "--- Step 4: Delivery Confirmation ---"

# Extract Resend response data from email content
RESEND_DATA=$(echo "$EMAIL_CONTENT" | jq -r '.resendResponse // empty')

if [ -n "$RESEND_DATA" ]; then
  # Build delivery confirmation from Resend response
  EMAIL_ID=$(echo "$RESEND_DATA" | jq -r '.data.id // .id // "unknown"')
  RESEND_TO=$(echo "$EMAIL_CONTENT" | jq -r '.to')
  RESEND_SUBJECT=$(echo "$EMAIL_CONTENT" | jq -r '.subject')
  CAPTURE_TS=$(echo "$EMAIL_CONTENT" | jq -r '.timestamp')

  jq -n \
    --arg email_id "$EMAIL_ID" \
    --arg to "$RESEND_TO" \
    --arg subject "$RESEND_SUBJECT" \
    --arg resend_status "sent" \
    --arg timestamp "$CAPTURE_TS" \
    --argjson resend_response "$RESEND_DATA" \
    '{
      email_id: $email_id,
      to: $to,
      subject: $subject,
      resend_status: $resend_status,
      timestamp: $timestamp,
      resend_response: $resend_response
    }' > "$DIR/delivery-confirmation.json"

  log "  Email ID: $EMAIL_ID"
  log "  Timestamp: $CAPTURE_TS"
  pass "Delivery confirmation extracted (email_id=$EMAIL_ID)"
else
  # Still create the file but mark as unavailable
  jq -n '{email_id: "unavailable", error: "No Resend response in captured email"}' > "$DIR/delivery-confirmation.json"
  fail "Delivery confirmation" "No resendResponse in email content"
fi

###############################################################################
# Step 5: Render email to screenshot
###############################################################################
log ""
log "--- Step 5: Email Screenshot ---"

cd "$PROJECT_ROOT"
NODE_PATH="$PROJECT_ROOT/frontend/node_modules" node scripts/screenshot-email.js 2>&1 || true

if [ -f "$DIR/email-rendered.png" ] && [ -s "$DIR/email-rendered.png" ]; then
  PNG_SIZE=$(wc -c < "$DIR/email-rendered.png" | tr -d ' ')
  pass "Email screenshot rendered (${PNG_SIZE} bytes)"
else
  fail "Email screenshot" "email-rendered.png missing or empty"
fi

###############################################################################
# Step 6: Verify token — full auth flow
###############################################################################
log ""
log "--- Step 6: Token Verification (Auth Flow) ---"

MAGIC_LINK_URL=$(echo "$EMAIL_CONTENT" | jq -r '.magicLinkUrl')

if [ -z "$MAGIC_LINK_URL" ] || [ "$MAGIC_LINK_URL" = "null" ]; then
  fail "Token verification" "No magic link URL found in email"
else
  # Extract token from URL
  TOKEN=$(echo "$MAGIC_LINK_URL" | sed 's/.*token=//')
  log "  Token: ${TOKEN:0:16}..."

  # The magic link URL points to /auth/verify?token=... (a page that redirects to the API).
  # Call the API endpoint directly for cleaner testing.
  VERIFY_URL="$BASE_URL/api/auth/verify?token=$TOKEN"

  # Use -D to capture headers, don't follow redirects (-s no progress, -S show errors)
  VERIFY_HEADERS=$(mktemp)
  VERIFY_BODY=$(curl -s -S -D "$VERIFY_HEADERS" -o - "$VERIFY_URL" 2>&1 || true)
  VERIFY_STATUS=$(head -1 "$VERIFY_HEADERS" | grep -oE '[0-9]{3}' | head -1 || echo "000")
  REDIRECT_LOCATION=$(grep -i '^location:' "$VERIFY_HEADERS" | sed 's/[Ll]ocation: *//' | tr -d '\r' || echo "")
  SESSION_COOKIE=$(grep -i 'set-cookie.*session=' "$VERIFY_HEADERS" | sed 's/.*session=//;s/;.*//' | tr -d '\r' || echo "")

  log "  Status: $VERIFY_STATUS"
  log "  Redirect: $REDIRECT_LOCATION"
  log "  Session cookie: ${SESSION_COOKIE:0:32}..."

  # Determine success: 307 redirect to /account with a session cookie
  AUTH_SUCCESS="false"
  if [ "$VERIFY_STATUS" = "307" ] && echo "$REDIRECT_LOCATION" | grep -q '/account' && [ -n "$SESSION_COOKIE" ]; then
    AUTH_SUCCESS="true"
  fi

  ###########################################################################
  # Step 7: Single-use rejection test (reuse same token)
  ###########################################################################
  log ""
  log "--- Step 7: Single-Use Token Rejection ---"

  REUSE_HEADERS=$(mktemp)
  REUSE_BODY=$(curl -s -S -D "$REUSE_HEADERS" -o - "$VERIFY_URL" 2>&1 || true)
  REUSE_STATUS=$(head -1 "$REUSE_HEADERS" | grep -oE '[0-9]{3}' | head -1 || echo "000")
  REUSE_ERROR=$(echo "$REUSE_BODY" | jq -r '.error // empty' 2>/dev/null || echo "")

  log "  Reuse status: $REUSE_STATUS"
  log "  Reuse error: $REUSE_ERROR"

  REUSE_REJECTED="false"
  if [ "$REUSE_STATUS" = "400" ]; then
    REUSE_REJECTED="true"
    pass "Single-use token rejection (status=$REUSE_STATUS)"
  else
    fail "Single-use token rejection" "Expected 400, got $REUSE_STATUS"
  fi

  ###########################################################################
  # Step 8: Invalid token test
  ###########################################################################
  log ""
  log "--- Step 8: Invalid Token Rejection ---"

  INVALID_HEADERS=$(mktemp)
  INVALID_BODY=$(curl -s -S -D "$INVALID_HEADERS" -o - "$BASE_URL/api/auth/verify?token=totally-invalid-garbage-token-1234" 2>&1 || true)
  INVALID_STATUS=$(head -1 "$INVALID_HEADERS" | grep -oE '[0-9]{3}' | head -1 || echo "000")
  INVALID_ERROR=$(echo "$INVALID_BODY" | jq -r '.error // empty' 2>/dev/null || echo "")

  log "  Invalid token status: $INVALID_STATUS"
  log "  Invalid token error: $INVALID_ERROR"

  INVALID_REJECTED="false"
  if [ "$INVALID_STATUS" = "400" ]; then
    INVALID_REJECTED="true"
    pass "Invalid token rejection (status=$INVALID_STATUS)"
  else
    fail "Invalid token rejection" "Expected 400, got $INVALID_STATUS"
  fi

  # Now assess the primary auth flow (Step 6)
  if [ "$AUTH_SUCCESS" = "true" ]; then
    pass "Token verification — 307 redirect to /account with session cookie"
  else
    fail "Token verification" "status=$VERIFY_STATUS redirect=$REDIRECT_LOCATION cookie_present=$([ -n \"$SESSION_COOKIE\" ] && echo yes || echo no)"
  fi

  # Build comprehensive auth-result.json
  jq -n \
    --arg success "$AUTH_SUCCESS" \
    --arg status_code "$VERIFY_STATUS" \
    --arg redirect_location "$REDIRECT_LOCATION" \
    --arg session_cookie "$SESSION_COOKIE" \
    --arg token_used "$TOKEN" \
    --arg response_body "$VERIFY_BODY" \
    --arg reuse_rejected "$REUSE_REJECTED" \
    --arg reuse_status "$REUSE_STATUS" \
    --arg reuse_error "$REUSE_ERROR" \
    --arg invalid_rejected "$INVALID_REJECTED" \
    --arg invalid_status "$INVALID_STATUS" \
    --arg invalid_error "$INVALID_ERROR" \
    --arg timestamp "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    '{
      success: ($success == "true"),
      status_code: ($status_code | tonumber),
      redirect_location: $redirect_location,
      session_cookie: $session_cookie,
      token_used: $token_used,
      response_body: $response_body,
      timestamp: $timestamp,
      reuse_test: {
        rejected: ($reuse_rejected == "true"),
        status_code: ($reuse_status | tonumber),
        error: $reuse_error,
        description: "Second use of same token — should be rejected"
      },
      invalid_token_test: {
        rejected: ($invalid_rejected == "true"),
        status_code: ($invalid_status | tonumber),
        error: $invalid_error,
        token_used: "totally-invalid-garbage-token-1234",
        description: "Garbage token — should return 400"
      }
    }' > "$DIR/auth-result.json"

  # Cleanup temp files
  rm -f "$VERIFY_HEADERS" "$REUSE_HEADERS" "$INVALID_HEADERS"
fi

###############################################################################
# Summary
###############################################################################
log ""
log "==========================================="
log "  RESULTS: $PASSED passed, $FAILED failed (of $((PASSED + FAILED)) tests)"
log "==========================================="
log ""
log "Evidence files:"
for f in health.json send-response.json email-content.json delivery-confirmation.json email-rendered.png auth-result.json smoke-output.txt; do
  if [ -f "$DIR/$f" ]; then
    SIZE=$(wc -c < "$DIR/$f" | tr -d ' ')
    log "  ✓ $f (${SIZE} bytes)"
  else
    log "  ✗ $f (MISSING)"
  fi
done

# Write full output to smoke-output.txt
echo "$OUTPUT" > "$DIR/smoke-output.txt"

log ""
if [ "$FAILED" -eq 0 ]; then
  log "ALL TESTS PASSED"
  exit 0
else
  log "SOME TESTS FAILED"
  exit 1
fi
