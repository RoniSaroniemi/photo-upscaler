#!/bin/bash
set -euo pipefail
EVIDENCE_DIR="evidence/j4-stripe"
mkdir -p "$EVIDENCE_DIR"
BASE_URL="${E2E_BASE_URL:-http://localhost:3001}"

echo "=== Setup: Get auth session ==="
curl -sf -X POST "$BASE_URL/api/test/auth/dev-login" \
  -H "Content-Type: application/json" -d '{}' -c /tmp/j4-cookies.txt \
  | tee "$EVIDENCE_DIR/auth-response.json"
echo ""

echo "=== Test 1: Create Stripe checkout session ==="
CHECKOUT=$(curl -sf -X POST "$BASE_URL/api/balance/add-funds" \
  -H "Content-Type: application/json" \
  -d '{"amount_cents": 500}' \
  -b /tmp/j4-cookies.txt)
echo "$CHECKOUT" | tee "$EVIDENCE_DIR/checkout-response.json" | python3 -m json.tool

URL=$(echo "$CHECKOUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('url','') or d.get('checkout_url','') or d.get('checkoutUrl',''))")
if echo "$URL" | grep -q "checkout.stripe.com"; then
  echo "PASS: Valid Stripe checkout URL generated"
  echo "$URL" > "$EVIDENCE_DIR/checkout-url.txt"
else
  echo "FAIL: No valid Stripe checkout URL"
  exit 1
fi

echo ""
echo "=== ALL J4 STRIPE TESTS PASSED ==="
