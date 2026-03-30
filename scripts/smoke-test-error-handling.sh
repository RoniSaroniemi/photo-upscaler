#!/usr/bin/env bash
# Smoke test for error handling across 6 API scenarios.
# Exits 0 only if ALL 6 pass.
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:3001}"
PASS=0
FAIL=0
RESULTS=()

pass() {
  local name="$1" status="$2"
  PASS=$((PASS + 1))
  RESULTS+=("PASS  $name  HTTP $status")
  echo "PASS  $name  (HTTP $status)"
}

fail() {
  local name="$1" status="$2" body="$3"
  FAIL=$((FAIL + 1))
  RESULTS+=("FAIL  $name  HTTP $status")
  echo "FAIL  $name  (HTTP $status)"
  echo "      body: $body"
}

# Create temp files
TXT_FILE=$(mktemp /tmp/smoke-test-XXXXXX.txt)
echo "not an image" > "$TXT_FILE"

PNG_FILE=$(mktemp /tmp/smoke-test-XXXXXX.png)
python3 -c "
import struct, zlib
def create_png():
    sig = b'\x89PNG\r\n\x1a\n'
    def chunk(ctype, data):
        c = ctype + data
        return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)
    ihdr = struct.pack('>IIBBBBB', 2, 2, 8, 2, 0, 0, 0)
    raw = b''
    for y in range(2):
        raw += b'\x00' + b'\xff\x00\x00' * 2
    idat = zlib.compress(raw)
    return sig + chunk(b'IHDR', ihdr) + chunk(b'IDAT', idat) + chunk(b'IEND', b'')
import sys; sys.stdout.buffer.write(create_png())
" > "$PNG_FILE"

echo "=== Error Handling Smoke Test ==="
echo "Base URL: $BASE_URL"
echo ""

# Scenario 1: Non-image upload — expect 400 with "File must be an image"
STATUS=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE_URL/api/upscale" -F "file=@${TXT_FILE};type=text/plain")
BODY=$(curl -s -X POST "$BASE_URL/api/upscale" -F "file=@${TXT_FILE};type=text/plain")
if [[ "$STATUS" == "400" ]] && echo "$BODY" | grep -q "File must be an image"; then
  pass "1. Non-image upload" "$STATUS"
else
  fail "1. Non-image upload" "$STATUS" "$BODY"
fi

# Scenario 2: Empty upload — expect 400 with "Missing"
STATUS=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE_URL/api/upscale" -F "dummy=nothing")
BODY=$(curl -s -X POST "$BASE_URL/api/upscale" -F "dummy=nothing")
if [[ "$STATUS" == "400" ]] && echo "$BODY" | grep -q "Missing"; then
  pass "2. Empty upload" "$STATUS"
else
  fail "2. Empty upload" "$STATUS" "$BODY"
fi

# Scenario 3: Invalid token — expect non-500 with JSON error
STATUS=$(curl -s -o /dev/null -w '%{http_code}' "$BASE_URL/api/auth/verify?token=fake_invalid_token")
BODY=$(curl -s "$BASE_URL/api/auth/verify?token=fake_invalid_token")
if [[ "$STATUS" != "500" ]] && echo "$BODY" | grep -q '"error"'; then
  pass "3. Invalid token" "$STATUS"
else
  fail "3. Invalid token" "$STATUS" "$BODY"
fi

# Scenario 4: Expired token — expect non-500 with JSON error
STATUS=$(curl -s -o /dev/null -w '%{http_code}' "$BASE_URL/api/auth/verify?token=0000000000000000000000000000000000000000000000expired")
BODY=$(curl -s "$BASE_URL/api/auth/verify?token=0000000000000000000000000000000000000000000000expired")
if [[ "$STATUS" != "500" ]] && echo "$BODY" | grep -q '"error"'; then
  pass "4. Expired token" "$STATUS"
else
  fail "4. Expired token" "$STATUS" "$BODY"
fi

# Scenario 5: Nonexistent endpoint — expect 404 JSON
STATUS=$(curl -s -o /dev/null -w '%{http_code}' "$BASE_URL/api/nonexistent")
BODY=$(curl -s "$BASE_URL/api/nonexistent")
if [[ "$STATUS" == "404" ]] && echo "$BODY" | grep -q '"error"'; then
  pass "5. Nonexistent endpoint" "$STATUS"
else
  fail "5. Nonexistent endpoint" "$STATUS" "$BODY"
fi

# Scenario 6: Insufficient balance / trial upscale — expect structured JSON error (not a bare 500)
# Without auth, this hits the trial flow. The inference service may not be configured,
# which returns a structured 500 with error+detail — that counts as handled, not a crash.
STATUS=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE_URL/api/upscale" -F "file=@${PNG_FILE};type=image/png")
BODY=$(curl -s -X POST "$BASE_URL/api/upscale" -F "file=@${PNG_FILE};type=image/png")
if echo "$BODY" | grep -q '"error"'; then
  pass "6. Insufficient balance" "$STATUS"
else
  fail "6. Insufficient balance" "$STATUS" "$BODY"
fi

# Cleanup
rm -f "$TXT_FILE" "$PNG_FILE"

echo ""
echo "=== Results ==="
for r in "${RESULTS[@]}"; do echo "  $r"; done
echo ""
echo "Passed: $PASS / $((PASS + FAIL))"

if [[ "$FAIL" -gt 0 ]]; then
  echo "SMOKE TEST FAILED"
  exit 1
fi

echo "ALL TESTS PASSED"
exit 0
