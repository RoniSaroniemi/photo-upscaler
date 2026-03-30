#!/bin/bash
set -euo pipefail
EVIDENCE_DIR="evidence/magic-link"
mkdir -p "$EVIDENCE_DIR"
BASE_URL="${E2E_BASE_URL:-http://localhost:3001}"

echo "=== Test 1: Send magic link ==="
curl -sf -X POST "$BASE_URL/api/auth/send-magic-link" \
  -H "Content-Type: application/json" \
  -d '{"email":"verify-test@example.com"}' | tee "$EVIDENCE_DIR/send-response.json"
echo ""

echo "=== Test 2: Capture sent email ==="
curl -sf "$BASE_URL/api/test/auth/last-email" | tee "$EVIDENCE_DIR/email-content.json" | python3 -m json.tool
# Verify email has: to, subject, magic link URL

echo "=== Test 3: Extract and verify magic link ==="
LINK=$(python3 -c "import json; print(json.load(open('$EVIDENCE_DIR/email-content.json'))['magicLinkUrl'])")
echo "Magic link: $LINK"
curl -sf -v "$LINK" 2>&1 | grep -i "set-cookie\|location" | tee "$EVIDENCE_DIR/verify-response.txt"
echo "PASS: Magic link works end-to-end"

echo "=== Test 4: Dev login shortcut ==="
curl -sf -X POST "$BASE_URL/api/test/auth/dev-login" \
  -H "Content-Type: application/json" \
  -d '{}' -v 2>&1 | grep -iE "set-cookie|userId|email" | tee "$EVIDENCE_DIR/dev-login.txt"
echo "PASS: Dev login works"

echo "=== Test 5: Account reset ==="
curl -sf -X POST "$BASE_URL/api/test/auth/reset-account" \
  -H "Content-Type: application/json" \
  -d '{}' | tee "$EVIDENCE_DIR/reset-response.json" | python3 -m json.tool
echo "PASS: Account reset works"

echo ""
echo "=== ALL MAGIC LINK TESTS PASSED ==="
