#!/bin/bash
# scripts/verify-fix-testability.sh — Acceptance test for testability infrastructure
# Run: cd frontend && bash scripts/verify-fix-testability.sh
# Evidence saved to: evidence/fix-testability/
set -euo pipefail
EVIDENCE_DIR="evidence/fix-testability"
mkdir -p "$EVIDENCE_DIR"
BASE_URL="${E2E_BASE_URL:-http://localhost:3001}"

echo "=== Test 1: Health check ==="
curl -sf "$BASE_URL/api/health" | tee "$EVIDENCE_DIR/health.json" | python3 -m json.tool
echo "PASS: Health check"

echo "=== Test 2: Trial reset ==="
curl -sf -X DELETE "$BASE_URL/api/test/trial-reset" | tee "$EVIDENCE_DIR/trial-reset.json" | python3 -m json.tool
echo "PASS: Trial reset"

echo "=== Test 3: Trial status shows remaining ==="
REMAINING=$(curl -sf "$BASE_URL/api/pricing/trial-status" | python3 -c "import sys,json; print(json.load(sys.stdin)['remaining'])")
if [ "$REMAINING" -gt 0 ]; then
  echo "PASS: Trial remaining=$REMAINING after reset"
else
  echo "FAIL: Trial still exhausted after reset (remaining=$REMAINING)"
  exit 1
fi

echo "=== Test 4: Magic link debug ==="
curl -sf -X POST "$BASE_URL/api/test/auth/magic-link" \
  -H "Content-Type: application/json" \
  -d '{"email":"test-verify@example.com"}' | tee "$EVIDENCE_DIR/magic-link.json" | python3 -m json.tool
TOKEN=$(python3 -c "import json; print(json.load(open('$EVIDENCE_DIR/magic-link.json'))['token'])")
if [ -n "$TOKEN" ]; then
  echo "PASS: Magic link token returned"
else
  echo "FAIL: No token in response"
  exit 1
fi

echo "=== Test 5: Token verifies and sets cookie ==="
curl -sf -v "$BASE_URL/api/auth/verify?token=$TOKEN" 2>&1 | tee "$EVIDENCE_DIR/verify-response.txt" | grep -i "set-cookie"
echo "PASS: Auth verify sets session cookie"

echo "=== Test 6: Stripe webhook mock ==="
# Extract userId from the session (via the verify response or a separate call)
SESSION_COOKIE=$(grep -i "set-cookie" "$EVIDENCE_DIR/verify-response.txt" | head -1 | sed 's/.*session=//;s/;.*//')
curl -sf -X POST "$BASE_URL/api/test/stripe-webhook" \
  -H "Content-Type: application/json" \
  -H "Cookie: session=$SESSION_COOKIE" \
  -d '{"amountCents": 500}' | tee "$EVIDENCE_DIR/stripe-webhook.json" | python3 -m json.tool
echo "PASS: Stripe webhook mock"

echo "=== Test 7: Balance updated ==="
BALANCE=$(curl -sf "$BASE_URL/api/balance" -H "Cookie: session=$SESSION_COOKIE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('balance',0))")
if [ "$BALANCE" -gt 0 ]; then
  echo "PASS: Balance=$BALANCE after webhook"
else
  echo "FAIL: Balance still 0 after webhook"
  exit 1
fi

echo "=== Test 8: Playwright tests pass ==="
cd "$(dirname "$0")/.."
E2E_BASE_URL="$BASE_URL" npx playwright test --reporter=list 2>&1 | tee "$EVIDENCE_DIR/playwright-output.txt" | tail -5
echo "PASS: Playwright tests"

echo ""
echo "=== ALL TESTS PASSED ==="
echo "Evidence saved to $EVIDENCE_DIR/"
