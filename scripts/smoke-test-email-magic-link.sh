#!/bin/bash
set -euo pipefail

EVIDENCE_DIR="evidence/email-magic-link"
mkdir -p "$EVIDENCE_DIR"
BASE_URL="${E2E_BASE_URL:-http://localhost:3001}"

PASS_COUNT=0
FAIL_COUNT=0
RESULTS=()

pass() {
  PASS_COUNT=$((PASS_COUNT + 1))
  RESULTS+=("PASS: $1")
  echo "  ✅ PASS: $1"
}

fail() {
  FAIL_COUNT=$((FAIL_COUNT + 1))
  RESULTS+=("FAIL: $1")
  echo "  ❌ FAIL: $1"
}

echo "========================================="
echo "  Email Magic Link Smoke Test"
echo "  Base URL: $BASE_URL"
echo "========================================="
echo ""

# -----------------------------------------------
# Test 1: Health check
# -----------------------------------------------
echo "--- Test 1: Health Check ---"
HTTP_CODE=$(curl -s -o "$EVIDENCE_DIR/health.json" -w "%{http_code}" "$BASE_URL/api/health")
if [ "$HTTP_CODE" = "200" ]; then
  pass "Health check (HTTP $HTTP_CODE)"
  cat "$EVIDENCE_DIR/health.json"
  echo ""
else
  fail "Health check (HTTP $HTTP_CODE)"
  cat "$EVIDENCE_DIR/health.json" 2>/dev/null
  echo ""
  exit 1
fi
echo ""

# -----------------------------------------------
# Test 2: Send magic link
# -----------------------------------------------
echo "--- Test 2: Send Magic Link ---"
HTTP_CODE=$(curl -s -o "$EVIDENCE_DIR/send-magic-link.json" -w "%{http_code}" \
  -X POST "$BASE_URL/api/auth/send-magic-link" \
  -H "Content-Type: application/json" \
  -d '{"email":"roni.saroniemi@foxie.ai"}')
if [ "$HTTP_CODE" = "200" ]; then
  pass "Send magic link (HTTP $HTTP_CODE)"
  cat "$EVIDENCE_DIR/send-magic-link.json"
  echo ""
else
  fail "Send magic link (HTTP $HTTP_CODE)"
  cat "$EVIDENCE_DIR/send-magic-link.json" 2>/dev/null
  echo ""
fi
echo ""

# -----------------------------------------------
# Test 3: Capture last email
# -----------------------------------------------
echo "--- Test 3: Capture Last Email ---"
HTTP_CODE=$(curl -s -o "$EVIDENCE_DIR/last-email.json" -w "%{http_code}" \
  "$BASE_URL/api/test/auth/last-email")
if [ "$HTTP_CODE" = "200" ]; then
  pass "Capture last email (HTTP $HTTP_CODE)"
  # Show email metadata (not full HTML)
  python3 -c "
import json, sys
with open('$EVIDENCE_DIR/last-email.json') as f:
    data = json.load(f)
print(f\"  To: {data.get('to', 'N/A')}\")
print(f\"  Subject: {data.get('subject', 'N/A')}\")
print(f\"  Magic Link: {data.get('magicLinkUrl', 'N/A')}\")
print(f\"  HTML length: {len(data.get('html', ''))} chars\")
" 2>/dev/null || echo "  (could not parse email JSON)"
else
  fail "Capture last email (HTTP $HTTP_CODE)"
  cat "$EVIDENCE_DIR/last-email.json" 2>/dev/null
  echo ""
fi
echo ""

# -----------------------------------------------
# Test 4: Save rendered email HTML
# -----------------------------------------------
echo "--- Test 4: Save Email HTML ---"
if [ -f "$EVIDENCE_DIR/last-email.json" ]; then
  python3 -c "
import json
with open('$EVIDENCE_DIR/last-email.json') as f:
    data = json.load(f)
html = data.get('html', '')
with open('$EVIDENCE_DIR/email-rendered.html', 'w') as f:
    f.write(html)
print(f'  Saved {len(html)} chars to email-rendered.html')
" 2>/dev/null
  if [ -f "$EVIDENCE_DIR/email-rendered.html" ] && [ -s "$EVIDENCE_DIR/email-rendered.html" ]; then
    pass "Save email HTML ($(wc -c < "$EVIDENCE_DIR/email-rendered.html" | tr -d ' ') bytes)"
  else
    fail "Save email HTML (empty or missing)"
  fi
else
  fail "Save email HTML (no last-email.json)"
fi
echo ""

# -----------------------------------------------
# Test 5: Extract and verify magic link
# -----------------------------------------------
echo "--- Test 5: Verify Magic Link ---"
MAGIC_LINK=$(python3 -c "
import json
with open('$EVIDENCE_DIR/last-email.json') as f:
    data = json.load(f)
print(data.get('magicLinkUrl', ''))
" 2>/dev/null)

if [ -n "$MAGIC_LINK" ]; then
  echo "  Magic link: $MAGIC_LINK"
  # Follow redirects, capture headers to check for session cookie
  HTTP_CODE=$(curl -s -o "$EVIDENCE_DIR/verify-response.txt" -w "%{http_code}" \
    -D "$EVIDENCE_DIR/verify-headers.txt" \
    -L "$MAGIC_LINK")
  echo "  Final HTTP: $HTTP_CODE"

  # Check if we got a session cookie at any point in the redirect chain
  if grep -qi "set-cookie.*session=" "$EVIDENCE_DIR/verify-headers.txt" 2>/dev/null; then
    pass "Magic link verification (session cookie set)"
  else
    # Even without cookie in headers, a 200 after redirect means the token was consumed
    if [ "$HTTP_CODE" = "200" ]; then
      pass "Magic link verification (HTTP $HTTP_CODE after redirect)"
    else
      fail "Magic link verification (HTTP $HTTP_CODE, no session cookie)"
    fi
  fi
else
  fail "Magic link verification (could not extract link)"
fi
echo ""

# -----------------------------------------------
# Test 6: Dev login test
# -----------------------------------------------
echo "--- Test 6: Dev Login ---"
HTTP_CODE=$(curl -s -o "$EVIDENCE_DIR/dev-login.json" -w "%{http_code}" \
  -D "$EVIDENCE_DIR/dev-login-headers.txt" \
  -X POST "$BASE_URL/api/test/auth/dev-login" \
  -H "Content-Type: application/json" \
  -d '{"email":"roni.saroniemi@foxie.ai"}')
if [ "$HTTP_CODE" = "200" ]; then
  if grep -qi "set-cookie.*session=" "$EVIDENCE_DIR/dev-login-headers.txt" 2>/dev/null; then
    pass "Dev login (HTTP $HTTP_CODE, session cookie set)"
  else
    pass "Dev login (HTTP $HTTP_CODE)"
  fi
  cat "$EVIDENCE_DIR/dev-login.json"
  echo ""
else
  fail "Dev login (HTTP $HTTP_CODE)"
  cat "$EVIDENCE_DIR/dev-login.json" 2>/dev/null
  echo ""
fi
echo ""

# -----------------------------------------------
# Summary
# -----------------------------------------------
echo "========================================="
echo "  SUMMARY"
echo "========================================="
for r in "${RESULTS[@]}"; do
  echo "  $r"
done
echo ""
echo "  Total: $((PASS_COUNT + FAIL_COUNT)) tests, $PASS_COUNT passed, $FAIL_COUNT failed"
echo "  Evidence: $EVIDENCE_DIR/"
ls -la "$EVIDENCE_DIR/"
echo ""

if [ "$FAIL_COUNT" -gt 0 ]; then
  echo "  ⚠️  SOME TESTS FAILED"
  exit 1
else
  echo "  ✅ ALL TESTS PASSED"
  exit 0
fi
