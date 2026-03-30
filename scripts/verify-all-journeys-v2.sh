#!/usr/bin/env bash
# =============================================================================
# Honest Image Tools — Full Journey Verification Script v2
# Run from project root: bash scripts/verify-all-journeys-v2.sh
# =============================================================================
set -euo pipefail

PORT="${PORT:-3001}"
BASE="http://localhost:${PORT}"
EVIDENCE_DIR="evidence/verify-journeys-$(date +%Y%m%d)"
TEST_IMAGE="/tmp/test-image.png"

mkdir -p "$EVIDENCE_DIR"

# --- Helpers ---
json_or_error() {
  python3 -c "
import sys,json,re
d=sys.stdin.read()
try:
  j=json.loads(d); print(json.dumps(j,indent=2))
except:
  m=re.search(r'\"message\":\"([^\"]+)\"',d)
  print('ERROR:', m.group(1) if m else d[:300])
"
}

# --- Create test image ---
echo "[setup] Creating test image..."
python3 -c "
import struct,zlib
d=b'\x00'+b'\xff\x00\x00'*100
r=struct.pack('>IHHI',100,100,8,2)
c=zlib.compress(d*100)
f=open('$TEST_IMAGE','wb')
f.write(b'\x89PNG\r\n\x1a\n')
[f.write(struct.pack('>I',len(x))+t+x+struct.pack('>I',zlib.crc32(t+x)&0xffffffff)) for t,x in [(b'IHDR',r),(b'IDAT',c),(b'IEND',b'')]]
f.close()
"

# --- Health check ---
echo "[setup] Health check..."
curl -sf "${BASE}/api/health" | json_or_error | tee "$EVIDENCE_DIR/health.txt"

# =============================================================================
# J1: Discovery
# =============================================================================
echo ""
echo "=== J1: Discovery ===" | tee "$EVIDENCE_DIR/j1-results.txt"
curl -sf "${BASE}/" -o "$EVIDENCE_DIR/j1-homepage.html"
curl -sf "${BASE}/pricing" -o "$EVIDENCE_DIR/j1-pricing.html"
echo "Homepage: $(wc -c < "$EVIDENCE_DIR/j1-homepage.html") bytes" | tee -a "$EVIDENCE_DIR/j1-results.txt"
echo "Pricing:  $(wc -c < "$EVIDENCE_DIR/j1-pricing.html") bytes" | tee -a "$EVIDENCE_DIR/j1-results.txt"
echo "--- Homepage keywords ---" >> "$EVIDENCE_DIR/j1-results.txt"
grep -i "honest\|upscal\|pricing\|price\|\$" "$EVIDENCE_DIR/j1-homepage.html" | head -10 >> "$EVIDENCE_DIR/j1-results.txt" 2>&1 || true
echo "--- Pricing keywords ---" >> "$EVIDENCE_DIR/j1-results.txt"
grep -i "honest\|upscal\|pricing\|price\|\$" "$EVIDENCE_DIR/j1-pricing.html" | head -10 >> "$EVIDENCE_DIR/j1-results.txt" 2>&1 || true

# =============================================================================
# J2: Free Trial
# =============================================================================
echo ""
echo "=== J2: Free Trial ===" | tee "$EVIDENCE_DIR/j2-results.txt"
echo "--- Trial reset ---" | tee -a "$EVIDENCE_DIR/j2-results.txt"
curl -s -X DELETE "${BASE}/api/test/trial-reset" 2>&1 | json_or_error | tee -a "$EVIDENCE_DIR/j2-results.txt"

for i in 1 2 3; do
  label="Upload attempt $i"
  [[ $i -eq 3 ]] && label="Upload attempt 3 (expect rejection)"
  echo "--- $label ---" | tee -a "$EVIDENCE_DIR/j2-results.txt"
  curl -s -X POST "${BASE}/api/upscale" -F "file=@${TEST_IMAGE}" --max-time 120 2>&1 | json_or_error | tee -a "$EVIDENCE_DIR/j2-results.txt"
done

# =============================================================================
# J3: Sign Up (magic link)
# =============================================================================
echo ""
echo "=== J3: Sign Up ===" | tee "$EVIDENCE_DIR/j3-results.txt"
echo "--- Send magic link ---" | tee -a "$EVIDENCE_DIR/j3-results.txt"
curl -s -X POST "${BASE}/api/auth/send-magic-link" -H "Content-Type: application/json" \
  -d '{"email":"test-verify@example.com"}' 2>&1 | json_or_error | tee -a "$EVIDENCE_DIR/j3-results.txt"

echo "--- Capture email ---" | tee -a "$EVIDENCE_DIR/j3-results.txt"
curl -s "${BASE}/api/test/auth/last-email" 2>&1 | json_or_error | tee -a "$EVIDENCE_DIR/j3-results.txt"

echo "--- Dev login ---" | tee -a "$EVIDENCE_DIR/j3-results.txt"
curl -s -X POST "${BASE}/api/test/auth/dev-login" -H "Content-Type: application/json" \
  -d '{"email":"test-verify@example.com"}' -c /tmp/cookies.txt 2>&1 | json_or_error | tee -a "$EVIDENCE_DIR/j3-results.txt"

echo "--- Verify session ---" | tee -a "$EVIDENCE_DIR/j3-results.txt"
curl -s "${BASE}/api/balance" -b /tmp/cookies.txt 2>&1 | json_or_error | tee -a "$EVIDENCE_DIR/j3-results.txt"

# =============================================================================
# J4: Add Funds
# =============================================================================
echo ""
echo "=== J4: Add Funds ===" | tee "$EVIDENCE_DIR/j4-results.txt"
echo "--- Reset account ---" | tee -a "$EVIDENCE_DIR/j4-results.txt"
curl -s -X POST "${BASE}/api/test/auth/reset-account" -b /tmp/cookies.txt 2>&1 | json_or_error | tee -a "$EVIDENCE_DIR/j4-results.txt"

echo "--- Create checkout ---" | tee -a "$EVIDENCE_DIR/j4-results.txt"
curl -s -X POST "${BASE}/api/balance/add-funds" -H "Content-Type: application/json" \
  -d '{"amount_cents":500}' -b /tmp/cookies.txt 2>&1 | json_or_error | tee -a "$EVIDENCE_DIR/j4-results.txt"

echo "--- Session check ---" | tee -a "$EVIDENCE_DIR/j4-results.txt"
curl -s "${BASE}/api/auth/session" -b /tmp/cookies.txt 2>&1 | json_or_error | tee -a "$EVIDENCE_DIR/j4-results.txt"

echo "--- Balance check ---" | tee -a "$EVIDENCE_DIR/j4-results.txt"
curl -s "${BASE}/api/balance" -b /tmp/cookies.txt 2>&1 | json_or_error | tee -a "$EVIDENCE_DIR/j4-results.txt"

# =============================================================================
# J5: Paid Upload
# =============================================================================
echo ""
echo "=== J5: Paid Upload ===" | tee "$EVIDENCE_DIR/j5-results.txt"
echo "--- Upload with balance ---" | tee -a "$EVIDENCE_DIR/j5-results.txt"
curl -s -X POST "${BASE}/api/upscale" -F "file=@${TEST_IMAGE}" -b /tmp/cookies.txt --max-time 120 2>&1 | json_or_error | tee -a "$EVIDENCE_DIR/j5-results.txt"

echo "--- Balance after upload ---" | tee -a "$EVIDENCE_DIR/j5-results.txt"
curl -s "${BASE}/api/balance" -b /tmp/cookies.txt 2>&1 | json_or_error | tee -a "$EVIDENCE_DIR/j5-results.txt"

# =============================================================================
# J6: Job History
# =============================================================================
echo ""
echo "=== J6: Job History ===" | tee "$EVIDENCE_DIR/j6-results.txt"
echo "--- List jobs ---" | tee -a "$EVIDENCE_DIR/j6-results.txt"
curl -s "${BASE}/api/upscale/jobs" -b /tmp/cookies.txt 2>&1 | json_or_error | tee -a "$EVIDENCE_DIR/j6-results.txt"

# =============================================================================
# J7: Error Handling
# =============================================================================
echo ""
echo "=== J7: Error Handling ===" | tee "$EVIDENCE_DIR/j7-results.txt"
echo "--- Non-image upload ---" | tee -a "$EVIDENCE_DIR/j7-results.txt"
echo "not an image" > /tmp/test.txt
curl -s -X POST "${BASE}/api/upscale" -F "file=@/tmp/test.txt" --max-time 30 2>&1 | json_or_error | tee -a "$EVIDENCE_DIR/j7-results.txt"

echo "--- Insufficient balance ---" | tee -a "$EVIDENCE_DIR/j7-results.txt"
curl -s -X POST "${BASE}/api/test/auth/dev-login" -H "Content-Type: application/json" \
  -d '{"email":"zero-balance@example.com"}' -c /tmp/cookies-zero.txt 2>&1 | json_or_error | tee -a "$EVIDENCE_DIR/j7-results.txt"
curl -s -X POST "${BASE}/api/test/auth/reset-account" -b /tmp/cookies-zero.txt 2>&1 | json_or_error | tee -a "$EVIDENCE_DIR/j7-results.txt"
curl -s -X POST "${BASE}/api/upscale" -F "file=@${TEST_IMAGE}" -b /tmp/cookies-zero.txt --max-time 30 2>&1 | json_or_error | tee -a "$EVIDENCE_DIR/j7-results.txt"

echo "--- Invalid magic link ---" | tee -a "$EVIDENCE_DIR/j7-results.txt"
curl -s "${BASE}/api/auth/verify?token=bogus" 2>&1 | json_or_error | tee -a "$EVIDENCE_DIR/j7-results.txt"

# =============================================================================
# HTTP Status Summary
# =============================================================================
echo ""
echo "=== HTTP Status Codes ===" | tee "$EVIDENCE_DIR/http-status-codes.txt"
for endpoint in \
  "GET /" \
  "GET /pricing" \
  "GET /api/health" \
  "DELETE /api/test/trial-reset" \
  "POST /api/auth/send-magic-link" \
  "GET /api/auth/verify?token=bogus" \
  "GET /api/balance" \
  "GET /api/upscale/jobs"; do
  method=$(echo "$endpoint" | awk '{print $1}')
  path=$(echo "$endpoint" | awk '{print $2}')
  code=$(curl -s -o /dev/null -w "%{http_code}" -X "$method" "${BASE}${path}" 2>&1)
  echo "$method $path -> $code" | tee -a "$EVIDENCE_DIR/http-status-codes.txt"
done

echo ""
echo "=== Verification complete. Evidence in: $EVIDENCE_DIR ==="
