#!/bin/bash
set -euo pipefail
EVIDENCE_DIR="evidence/j3-resend"
mkdir -p "$EVIDENCE_DIR"
BASE_URL="${E2E_BASE_URL:-http://localhost:3001}"

echo '=== Test: Send magic link email ==='
SEND_RESP=$(curl -sf -X POST "$BASE_URL/api/auth/send-magic-link" \
  -H 'Content-Type: application/json' \
  -d '{"email":"test@resend.dev"}' 2>&1) || SEND_RESP="ERROR: $?"
echo "$SEND_RESP" | tee "$EVIDENCE_DIR/send-response.json"

echo ''
echo '=== Check: Resend API response ==='
EMAIL_CAPTURE=$(curl -sf "$BASE_URL/api/test/auth/last-email" 2>&1) || EMAIL_CAPTURE="ERROR: $?"
echo "$EMAIL_CAPTURE" | tee "$EVIDENCE_DIR/email-capture.json" | python3 -m json.tool 2>/dev/null || echo "$EMAIL_CAPTURE"

echo ''
echo '=== Investigation findings ==='
echo "$EMAIL_CAPTURE" | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    resp = data.get('resendResponse', {})
    if isinstance(resp, dict):
        if resp.get('data') and resp['data'].get('id'):
            print(f'PASS: Email sent successfully (id={resp[\"data\"][\"id\"]})')
        elif resp.get('error'):
            print(f'FAIL: Resend error: {resp[\"error\"]}')
        else:
            print(f'INVESTIGATE: Unexpected response: {json.dumps(resp)}')
    else:
        print(f'INVESTIGATE: Response is not dict: {resp}')
except Exception as e:
    print(f'ERROR: Could not parse response: {e}')
" 2>&1

echo ''
echo '=== Health check ==='
curl -sf "$BASE_URL/api/health" && echo ' OK' || echo 'HEALTH CHECK FAILED'
