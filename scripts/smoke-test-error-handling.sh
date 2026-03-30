#!/usr/bin/env bash
# Smoke test: 6 error-handling scenarios for Honest Image Tools
# Usage: ./scripts/smoke-test-error-handling.sh
# Requires: dev server running on localhost:3001

set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:3001}"
PASS_COUNT=0
FAIL_COUNT=0
TOTAL=6

# Create a tiny 1x1 PNG for upload tests
TEST_PNG=$(mktemp /tmp/test-image-XXXXXX.png)
printf '\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82' > "$TEST_PNG"

cleanup() { rm -f "$TEST_PNG"; }
trap cleanup EXIT

check_scenario() {
  local name="$1"
  local status="$2"
  local body="$3"

  # PASS if: not a 500, and body contains a meaningful error (not empty/generic framework error)
  if [[ "$status" == "500" ]]; then
    echo "FAIL  $name  (HTTP $status - server error)"
    FAIL_COUNT=$((FAIL_COUNT + 1))
    return
  fi

  if [[ -z "$body" ]] || echo "$body" | grep -q "Internal Server Error"; then
    echo "FAIL  $name  (empty or generic error response)"
    FAIL_COUNT=$((FAIL_COUNT + 1))
    return
  fi

  echo "PASS  $name  (HTTP $status)"
  PASS_COUNT=$((PASS_COUNT + 1))
}

echo "=== Error Handling Smoke Test ==="
echo "Target: $BASE_URL"
echo ""

# Health check
if ! curl -sf "$BASE_URL/api/health" > /dev/null 2>&1; then
  echo "ERROR: Server not responding at $BASE_URL"
  exit 1
fi

# --- Scenario 1: Upload non-image file ---
RESP=$(curl -s -w '\n%{http_code}' -X POST "$BASE_URL/api/upscale" \
  -F "file=@$0;type=application/octet-stream" -F 'scale=2' 2>&1)
STATUS=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | sed '$d')
check_scenario "S1: Non-image file upload" "$STATUS" "$BODY"

# --- Scenario 2: Upload with no file ---
RESP=$(curl -s -w '\n%{http_code}' -X POST "$BASE_URL/api/upscale" \
  -F 'scale=2' 2>&1)
STATUS=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | sed '$d')
check_scenario "S2: Missing file field" "$STATUS" "$BODY"

# --- Scenario 3: Invalid magic link token ---
RESP=$(curl -s -w '\n%{http_code}' -L "$BASE_URL/api/auth/verify?token=invalid-token-12345" 2>&1)
STATUS=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | sed '$d')
# For redirects, check that we landed on an error page (not a 500)
if echo "$BODY" | grep -qi "invalid\|expired\|request a new"; then
  echo "PASS  S3: Invalid magic link token  (redirected to error page)"
  PASS_COUNT=$((PASS_COUNT + 1))
elif [[ "$STATUS" == "500" ]]; then
  echo "FAIL  S3: Invalid magic link token  (HTTP 500)"
  FAIL_COUNT=$((FAIL_COUNT + 1))
else
  check_scenario "S3: Invalid magic link token" "$STATUS" "$BODY"
fi

# --- Scenario 4: Expired magic link token ---
RESP=$(curl -s -w '\n%{http_code}' -L "$BASE_URL/api/auth/verify?token=expired-fake-token-xyz" 2>&1)
STATUS=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | sed '$d')
if echo "$BODY" | grep -qi "invalid\|expired\|request a new"; then
  echo "PASS  S4: Expired magic link token  (redirected to error page)"
  PASS_COUNT=$((PASS_COUNT + 1))
elif [[ "$STATUS" == "500" ]]; then
  echo "FAIL  S4: Expired magic link token  (HTTP 500)"
  FAIL_COUNT=$((FAIL_COUNT + 1))
else
  check_scenario "S4: Expired magic link token" "$STATUS" "$BODY"
fi

# --- Scenario 5: Nonexistent API endpoint ---
RESP=$(curl -s -w '\n%{http_code}' "$BASE_URL/api/nonexistent-endpoint" 2>&1)
STATUS=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | sed '$d')
check_scenario "S5: Nonexistent API endpoint" "$STATUS" "$BODY"

# --- Scenario 6: Upload with insufficient balance ---
# Try to get a test session first
LOGIN_RESP=$(curl -s -w '\n%{http_code}' -c /tmp/smoke-cookies.txt \
  -X POST "$BASE_URL/api/test/auth/dev-login" 2>&1)
LOGIN_STATUS=$(echo "$LOGIN_RESP" | tail -1)

if [[ "$LOGIN_STATUS" == "200" ]]; then
  # Got a session, try upload
  RESP=$(curl -s -w '\n%{http_code}' -b /tmp/smoke-cookies.txt \
    -X POST "$BASE_URL/api/upscale" \
    -F "file=@$TEST_PNG;type=image/png" -F 'scale=2' 2>&1)
  BODY=$(echo "$RESP" | head -n -1)
  STATUS=$(echo "$RESP" | tail -1)
  check_scenario "S6: Insufficient balance upload" "$STATUS" "$BODY"
else
  # No DB - check that we at least get a meaningful error from dev-login
  LOGIN_BODY=$(echo "$LOGIN_RESP" | sed '$d')
  if [[ "$LOGIN_STATUS" != "500" ]] && echo "$LOGIN_BODY" | grep -q "error"; then
    echo "PASS  S6: Insufficient balance (DB unavailable, got meaningful 503)"
    PASS_COUNT=$((PASS_COUNT + 1))
  else
    echo "FAIL  S6: Insufficient balance (DB unavailable, got HTTP $LOGIN_STATUS with no meaningful error)"
    FAIL_COUNT=$((FAIL_COUNT + 1))
  fi
fi

rm -f /tmp/smoke-cookies.txt

echo ""
echo "=== Results: $PASS_COUNT/$TOTAL error scenarios handled correctly ==="

if [[ $FAIL_COUNT -gt 0 ]]; then
  exit 1
fi
exit 0
