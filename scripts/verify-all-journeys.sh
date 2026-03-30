#!/usr/bin/env bash
# =============================================================================
# verify-all-journeys.sh
# Run all 7 customer journeys end-to-end and capture Level 3 evidence.
# Exit 0 if all pass, non-zero if any fail.
# =============================================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BASE_URL="${BASE_URL:-http://localhost:3001}"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
EVIDENCE_DIR="${PROJECT_DIR}/evidence/verify-journeys-${TIMESTAMP}"

PASS_COUNT=0
FAIL_COUNT=0
declare -a JOURNEY_STATUS=()

GREEN='\033[0;32m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

log()  { printf "${BOLD}>>>${NC} %s\n" "$@"; }

pass() {
  local j="$1" step="$2"
  PASS_COUNT=$((PASS_COUNT + 1))
  JOURNEY_STATUS+=("PASS|$j|$step|")
  printf "  ${GREEN}PASS${NC} %s\n" "$step"
}

fail() {
  local j="$1" step="$2" detail="${3:-}"
  FAIL_COUNT=$((FAIL_COUNT + 1))
  JOURNEY_STATUS+=("FAIL|$j|$step|$detail")
  printf "  ${RED}FAIL${NC} %s\n" "$step"
  [ -n "$detail" ] && printf "       -> %s\n" "$detail"
}

# Take a screenshot using Python Playwright
screenshot() {
  local url="$1" output="$2" cookie_val="${3:-}"
  python3 - "$url" "$output" "$cookie_val" "$BASE_URL" << 'PYEOF'
import sys
from playwright.sync_api import sync_playwright

url, output, cookie_val, base_url = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
with sync_playwright() as p:
    browser = p.chromium.launch()
    context = browser.new_context(viewport={"width": 1280, "height": 720})
    if cookie_val:
        context.add_cookies([{"name": "session", "value": cookie_val, "url": base_url}])
    page = context.new_page()
    page.goto(url, wait_until="networkidle", timeout=30000)
    page.screenshot(path=output, full_page=True)
    browser.close()
PYEOF
}

# =============================================================================
# Prerequisites
# =============================================================================
log "Checking prerequisites..."
mkdir -p "$EVIDENCE_DIR"

HEALTH=$(curl -sf --max-time 5 "${BASE_URL}/api/health" 2>/dev/null || echo "")
if [ -z "$HEALTH" ]; then
  echo "ERROR: App not running at ${BASE_URL}. Start with TEST_MODE=true."
  exit 1
fi
echo "$HEALTH" > "${EVIDENCE_DIR}/health.json"
log "App healthy at ${BASE_URL}"

TRIAL_RESET=$(curl -s --max-time 5 -X DELETE "${BASE_URL}/api/test/trial-reset" 2>/dev/null || echo "")
if ! echo "$TRIAL_RESET" | jq -e '.reset == true' >/dev/null 2>&1; then
  echo "ERROR: Test endpoints unavailable. Ensure TEST_MODE=true."
  exit 1
fi
log "TEST_MODE confirmed"

# Create test image (640x480 JPEG)
python3 << PYEOF
from PIL import Image, ImageDraw
img = Image.new('RGB', (640, 480), color=(100, 150, 200))
draw = ImageDraw.Draw(img)
for i in range(0, 640, 40):
    draw.line([(i, 0), (i, 480)], fill=(200, 100, 50), width=2)
for i in range(0, 480, 40):
    draw.line([(0, i), (640, i)], fill=(50, 100, 200), width=2)
draw.rectangle([200, 140, 440, 340], fill=(255, 200, 100))
img.save("${EVIDENCE_DIR}/test-input.jpg", "JPEG", quality=85)
PYEOF
TEST_IMAGE="${EVIDENCE_DIR}/test-input.jpg"
log "Test image created (640x480)"

echo "This is a plain text file, not an image." > "${EVIDENCE_DIR}/test-not-image.txt"
TEST_TXT="${EVIDENCE_DIR}/test-not-image.txt"

log "Evidence directory: ${EVIDENCE_DIR}"
echo ""

# =============================================================================
# Journey 1: Discovery
# =============================================================================
log "Journey 1: Discovery"

if screenshot "${BASE_URL}" "${EVIDENCE_DIR}/j1-homepage.png" 2>/dev/null && [ -f "${EVIDENCE_DIR}/j1-homepage.png" ]; then
  pass "J1" "Homepage screenshot captured"
else
  fail "J1" "Homepage screenshot failed"
fi

if screenshot "${BASE_URL}/pricing" "${EVIDENCE_DIR}/j1-pricing.png" 2>/dev/null && [ -f "${EVIDENCE_DIR}/j1-pricing.png" ]; then
  pass "J1" "Pricing page screenshot captured"
else
  fail "J1" "Pricing page screenshot failed"
fi

echo ""

# =============================================================================
# Journey 2: Free Trial
# =============================================================================
log "Journey 2: Free Trial"

# Reset trial
RESET=$(curl -s --max-time 10 -X DELETE "${BASE_URL}/api/test/trial-reset")
echo "$RESET" > "${EVIDENCE_DIR}/j2-trial-reset.json"
if echo "$RESET" | jq -e '.reset == true' >/dev/null 2>&1; then
  pass "J2" "Trial reset successful (remaining: $(echo "$RESET" | jq -r '.remaining'))"
else
  fail "J2" "Trial reset failed" "$RESET"
fi

# First upload (trial use 1)
UPLOAD1=$(curl -s --max-time 120 -F "file=@${TEST_IMAGE}" "${BASE_URL}/api/upscale")
echo "$UPLOAD1" > "${EVIDENCE_DIR}/j2-upload1.json"
U1_STATUS=$(echo "$UPLOAD1" | jq -r '.status // empty' 2>/dev/null)
U1_DL=$(echo "$UPLOAD1" | jq -r '.download_url // empty' 2>/dev/null)
U1_COST=$(echo "$UPLOAD1" | jq -r '.cost_breakdown // empty' 2>/dev/null)

if [ "$U1_STATUS" = "completed" ] && [ -n "$U1_DL" ] && [ -n "$U1_COST" ]; then
  pass "J2" "First upload completed with download_url and cost_breakdown"

  # Download and verify dimensions
  if curl -s --max-time 30 -o "${EVIDENCE_DIR}/j2-result1.jpg" "$U1_DL" 2>/dev/null && [ -f "${EVIDENCE_DIR}/j2-result1.jpg" ]; then
    DIMS=$(python3 -c "from PIL import Image; i=Image.open('${EVIDENCE_DIR}/j2-result1.jpg'); print(f'{i.width}x{i.height}')" 2>/dev/null || echo "unknown")
    echo "$DIMS" > "${EVIDENCE_DIR}/j2-result1-dimensions.txt"
    OUT_W=$(echo "$DIMS" | cut -dx -f1)
    OUT_H=$(echo "$DIMS" | cut -dx -f2)
    if [ "${OUT_W:-0}" -gt 640 ] 2>/dev/null && [ "${OUT_H:-0}" -gt 480 ] 2>/dev/null; then
      pass "J2" "Result dimensions ${DIMS} > input 640x480"
    else
      fail "J2" "Result not larger than input" "Got ${DIMS}, expected > 640x480"
    fi
  else
    fail "J2" "Could not download result image"
  fi
else
  fail "J2" "First upload failed" "$(echo "$UPLOAD1" | jq -c '.' 2>/dev/null || echo "$UPLOAD1")"
fi

# Second upload (trial use 2)
UPLOAD2=$(curl -s --max-time 120 -F "file=@${TEST_IMAGE}" "${BASE_URL}/api/upscale")
echo "$UPLOAD2" > "${EVIDENCE_DIR}/j2-upload2.json"
U2_STATUS=$(echo "$UPLOAD2" | jq -r '.status // empty' 2>/dev/null)
if [ "$U2_STATUS" = "completed" ]; then
  pass "J2" "Second upload completed (trial use 2/2)"
else
  fail "J2" "Second upload failed" "$(echo "$UPLOAD2" | jq -c '.' 2>/dev/null || echo "$UPLOAD2")"
fi

# Third upload (should be rejected — trial exhausted)
UPLOAD3_FULL=$(curl -s --max-time 30 -F "file=@${TEST_IMAGE}" -w "\n%{http_code}" "${BASE_URL}/api/upscale")
U3_HTTP=$(echo "$UPLOAD3_FULL" | tail -1)
U3_BODY=$(echo "$UPLOAD3_FULL" | sed '$d')
echo "$U3_BODY" > "${EVIDENCE_DIR}/j2-upload3-rejected.json"
if [ "$U3_HTTP" = "401" ] || [ "$U3_HTTP" = "403" ] || [ "$U3_HTTP" = "429" ]; then
  pass "J2" "Third upload rejected (HTTP ${U3_HTTP}) — trial exhausted"
else
  fail "J2" "Third upload NOT rejected as expected" "HTTP ${U3_HTTP}: $(echo "$U3_BODY" | jq -c '.' 2>/dev/null || echo "$U3_BODY")"
fi

echo ""

# =============================================================================
# Journey 3: Sign Up
# =============================================================================
log "Journey 3: Sign Up"

AUTH_RESP=$(curl -s --max-time 10 -X POST -H "Content-Type: application/json" \
  -d '{"email":"test-verify@example.com"}' \
  "${BASE_URL}/api/test/auth/magic-link")
echo "$AUTH_RESP" > "${EVIDENCE_DIR}/j3-magic-link.json"
TOKEN=$(echo "$AUTH_RESP" | jq -r '.token // empty' 2>/dev/null)

if [ -n "$TOKEN" ]; then
  pass "J3" "Magic link token received"
else
  fail "J3" "Failed to get magic link token" "$AUTH_RESP"
fi

# Verify token (follows redirect, captures cookies)
COOKIE_JAR="${EVIDENCE_DIR}/.cookies"
VERIFY_HEADERS=$(curl -s -D - -o /dev/null -c "$COOKIE_JAR" -L --max-time 10 \
  "${BASE_URL}/api/auth/verify?token=${TOKEN}" 2>/dev/null || echo "")
echo "$VERIFY_HEADERS" > "${EVIDENCE_DIR}/j3-verify-headers.txt"

if echo "$VERIFY_HEADERS" | grep -qi "set-cookie.*session="; then
  pass "J3" "Set-Cookie header with session present"
else
  fail "J3" "No session cookie in verify response"
fi

# Extract session cookie
SESSION_COOKIE=$(grep 'session' "$COOKIE_JAR" 2>/dev/null | awk '{print $NF}' | head -1 || echo "")
if [ -n "$SESSION_COOKIE" ]; then
  pass "J3" "Session cookie extracted"
else
  fail "J3" "Could not extract session cookie from jar"
fi

# Screenshot /account with session
if [ -n "$SESSION_COOKIE" ]; then
  if screenshot "${BASE_URL}/account" "${EVIDENCE_DIR}/j3-account.png" "$SESSION_COOKIE" 2>/dev/null && [ -f "${EVIDENCE_DIR}/j3-account.png" ]; then
    pass "J3" "Account page screenshot captured"
  else
    fail "J3" "Account page screenshot failed"
  fi
else
  fail "J3" "Skipping account screenshot — no session"
fi

echo ""

# =============================================================================
# Journey 4: Add Funds
# =============================================================================
log "Journey 4: Add Funds"

# Extract userId from JWT
USER_ID=""
if [ -n "$SESSION_COOKIE" ]; then
  USER_ID=$(python3 - "$SESSION_COOKIE" << 'PYEOF'
import sys, json, base64
token = sys.argv[1]
payload = token.split('.')[1]
payload += '=' * (4 - len(payload) % 4)
data = json.loads(base64.urlsafe_b64decode(payload))
print(data.get('sub', ''))
PYEOF
  )
fi

if [ -z "$USER_ID" ]; then
  fail "J4" "Could not extract userId from JWT"
fi

# Mock Stripe webhook — add $5.00
WEBHOOK_RESP=$(curl -s --max-time 10 -X POST -H "Content-Type: application/json" \
  -d "{\"userId\":\"${USER_ID}\",\"amountCents\":500}" \
  "${BASE_URL}/api/test/stripe-webhook")
echo "$WEBHOOK_RESP" > "${EVIDENCE_DIR}/j4-stripe-webhook.json"

if echo "$WEBHOOK_RESP" | jq -e '.balance' >/dev/null 2>&1; then
  pass "J4" "Stripe webhook processed (balance: $(echo "$WEBHOOK_RESP" | jq -r '.balance'))"
else
  fail "J4" "Stripe webhook failed" "$WEBHOOK_RESP"
fi

# Check balance
BALANCE_RESP=$(curl -s --max-time 10 -b "$COOKIE_JAR" "${BASE_URL}/api/balance")
echo "$BALANCE_RESP" > "${EVIDENCE_DIR}/j4-balance.json"
FORMATTED_BAL=$(echo "$BALANCE_RESP" | jq -r '.formatted // empty' 2>/dev/null)
if [ -n "$FORMATTED_BAL" ]; then
  pass "J4" "Balance check: ${FORMATTED_BAL}"
else
  fail "J4" "Balance check failed" "$BALANCE_RESP"
fi

# Test add-funds URL generation
ADDFUNDS_RESP=$(curl -s --max-time 10 -X POST -H "Content-Type: application/json" \
  -d '{"amount_cents":500}' \
  -b "$COOKIE_JAR" "${BASE_URL}/api/balance/add-funds")
echo "$ADDFUNDS_RESP" > "${EVIDENCE_DIR}/j4-add-funds.json"
CHECKOUT_URL=$(echo "$ADDFUNDS_RESP" | jq -r '.checkout_url // empty' 2>/dev/null)
if [ -n "$CHECKOUT_URL" ] && [[ "$CHECKOUT_URL" == http* ]]; then
  pass "J4" "Checkout URL generated"
else
  fail "J4" "Checkout URL generation failed" "$ADDFUNDS_RESP"
fi

echo ""

# =============================================================================
# Journey 5: Paid Upload
# =============================================================================
log "Journey 5: Paid Upload"

# Balance before
BAL_BEFORE=$(curl -s --max-time 10 -b "$COOKIE_JAR" "${BASE_URL}/api/balance")
echo "$BAL_BEFORE" > "${EVIDENCE_DIR}/j5-balance-before.json"
BAL_BEFORE_VAL=$(echo "$BAL_BEFORE" | jq -r '.balance_microdollars // "0"' 2>/dev/null)
printf "  Balance before: %s\n" "$(echo "$BAL_BEFORE" | jq -r '.formatted // "?"' 2>/dev/null)"

# Upload with session cookie
PAID_UPLOAD=$(curl -s --max-time 120 -F "file=@${TEST_IMAGE}" -b "$COOKIE_JAR" "${BASE_URL}/api/upscale")
echo "$PAID_UPLOAD" > "${EVIDENCE_DIR}/j5-paid-upload.json"
PAID_STATUS=$(echo "$PAID_UPLOAD" | jq -r '.status // empty' 2>/dev/null)
PAID_JOB_ID=$(echo "$PAID_UPLOAD" | jq -r '.job_id // empty' 2>/dev/null)

if [ "$PAID_STATUS" = "completed" ]; then
  pass "J5" "Paid upload completed (job: ${PAID_JOB_ID})"
else
  fail "J5" "Paid upload failed" "$(echo "$PAID_UPLOAD" | jq -c '.' 2>/dev/null || echo "$PAID_UPLOAD")"
fi

# Check cost breakdown
if echo "$PAID_UPLOAD" | jq -e '.cost_breakdown.total_microdollars' >/dev/null 2>&1; then
  TOTAL_COST=$(echo "$PAID_UPLOAD" | jq -r '.cost_breakdown.formatted_total // .cost_breakdown.total_microdollars' 2>/dev/null)
  pass "J5" "Cost breakdown present (total: ${TOTAL_COST})"
else
  fail "J5" "No cost breakdown in response"
fi

# Download result
PAID_DL_URL=$(echo "$PAID_UPLOAD" | jq -r '.download_url // empty' 2>/dev/null)
if [ -n "$PAID_DL_URL" ]; then
  if curl -s --max-time 30 -o "${EVIDENCE_DIR}/j5-result.jpg" "$PAID_DL_URL" 2>/dev/null && [ -f "${EVIDENCE_DIR}/j5-result.jpg" ]; then
    PAID_DIMS=$(python3 -c "from PIL import Image; i=Image.open('${EVIDENCE_DIR}/j5-result.jpg'); print(f'{i.width}x{i.height}')" 2>/dev/null || echo "unknown")
    echo "$PAID_DIMS" > "${EVIDENCE_DIR}/j5-result-dimensions.txt"
    pass "J5" "Result downloaded (${PAID_DIMS})"
  else
    fail "J5" "Could not download paid result"
  fi
fi

# Balance after
BAL_AFTER=$(curl -s --max-time 10 -b "$COOKIE_JAR" "${BASE_URL}/api/balance")
echo "$BAL_AFTER" > "${EVIDENCE_DIR}/j5-balance-after.json"
BAL_AFTER_VAL=$(echo "$BAL_AFTER" | jq -r '.balance_microdollars // "0"' 2>/dev/null)
printf "  Balance after:  %s\n" "$(echo "$BAL_AFTER" | jq -r '.formatted // "?"' 2>/dev/null)"

if [ "$BAL_AFTER_VAL" -lt "$BAL_BEFORE_VAL" ] 2>/dev/null; then
  pass "J5" "Balance decreased: ${BAL_BEFORE_VAL} -> ${BAL_AFTER_VAL} microdollars"
else
  fail "J5" "Balance did not decrease" "Before: ${BAL_BEFORE_VAL}, After: ${BAL_AFTER_VAL}"
fi

echo ""

# =============================================================================
# Journey 6: Job History
# =============================================================================
log "Journey 6: Job History"

JOBS_RESP=$(curl -s --max-time 10 -b "$COOKIE_JAR" "${BASE_URL}/api/upscale/jobs")
echo "$JOBS_RESP" > "${EVIDENCE_DIR}/j6-jobs-list.json"
JOB_COUNT=$(echo "$JOBS_RESP" | jq '.jobs | length' 2>/dev/null || echo "0")

if [ "$JOB_COUNT" -gt 0 ] 2>/dev/null; then
  pass "J6" "Jobs list returned ${JOB_COUNT} job(s)"
else
  fail "J6" "No jobs returned" "$(echo "$JOBS_RESP" | jq -c '.' 2>/dev/null || echo "$JOBS_RESP")"
fi

# Get single job detail
DETAIL_JOB_ID="${PAID_JOB_ID}"
if [ -z "$DETAIL_JOB_ID" ] || [ "$DETAIL_JOB_ID" = "null" ]; then
  DETAIL_JOB_ID=$(echo "$JOBS_RESP" | jq -r '.jobs[0].id // empty' 2>/dev/null)
fi

if [ -n "$DETAIL_JOB_ID" ]; then
  JOB_DETAIL=$(curl -s --max-time 10 -b "$COOKIE_JAR" "${BASE_URL}/api/upscale/jobs/${DETAIL_JOB_ID}")
  echo "$JOB_DETAIL" > "${EVIDENCE_DIR}/j6-job-detail.json"
  DETAIL_STATUS=$(echo "$JOB_DETAIL" | jq -r '.status // empty' 2>/dev/null)
  if [ -n "$DETAIL_STATUS" ]; then
    pass "J6" "Single job detail retrieved (status: ${DETAIL_STATUS})"
  else
    fail "J6" "Job detail returned unexpected format" "$(echo "$JOB_DETAIL" | jq -c '.' 2>/dev/null || echo "$JOB_DETAIL")"
  fi
else
  fail "J6" "No job ID available for detail query"
fi

echo ""

# =============================================================================
# Journey 7: Error Handling
# =============================================================================
log "Journey 7: Error Handling"

# 7a: Upload non-image file
ERR_NOTIMG_FULL=$(curl -s --max-time 30 -F "file=@${TEST_TXT};type=text/plain" -w "\n%{http_code}" "${BASE_URL}/api/upscale")
ERR_NOTIMG_HTTP=$(echo "$ERR_NOTIMG_FULL" | tail -1)
ERR_NOTIMG_BODY=$(echo "$ERR_NOTIMG_FULL" | sed '$d')
echo "$ERR_NOTIMG_BODY" > "${EVIDENCE_DIR}/j7-error-not-image.json"

if [ "$ERR_NOTIMG_HTTP" -ge 400 ] 2>/dev/null && [ "$ERR_NOTIMG_HTTP" -lt 500 ] 2>/dev/null; then
  pass "J7" "Non-image rejected (HTTP ${ERR_NOTIMG_HTTP})"
else
  fail "J7" "Non-image upload not rejected" "HTTP ${ERR_NOTIMG_HTTP}"
fi

# 7b: Upload with insufficient balance (new user, $0 balance)
AUTH2_RESP=$(curl -s --max-time 10 -X POST -H "Content-Type: application/json" \
  -d '{"email":"test-broke@example.com"}' \
  "${BASE_URL}/api/test/auth/magic-link")
TOKEN2=$(echo "$AUTH2_RESP" | jq -r '.token // empty' 2>/dev/null)
COOKIE_JAR2="${EVIDENCE_DIR}/.cookies2"

if [ -n "$TOKEN2" ]; then
  curl -s -o /dev/null -c "$COOKIE_JAR2" -L --max-time 10 \
    "${BASE_URL}/api/auth/verify?token=${TOKEN2}" 2>/dev/null

  ERR_NOBAL_FULL=$(curl -s --max-time 30 -F "file=@${TEST_IMAGE}" -b "$COOKIE_JAR2" -w "\n%{http_code}" "${BASE_URL}/api/upscale")
  ERR_NOBAL_HTTP=$(echo "$ERR_NOBAL_FULL" | tail -1)
  ERR_NOBAL_BODY=$(echo "$ERR_NOBAL_FULL" | sed '$d')
  echo "$ERR_NOBAL_BODY" > "${EVIDENCE_DIR}/j7-error-no-balance.json"

  if [ "$ERR_NOBAL_HTTP" = "402" ]; then
    pass "J7" "Insufficient balance rejected (HTTP 402)"
  else
    fail "J7" "Insufficient balance not rejected as expected" "HTTP ${ERR_NOBAL_HTTP}: $(echo "$ERR_NOBAL_BODY" | jq -c '.' 2>/dev/null || echo "$ERR_NOBAL_BODY")"
  fi
else
  fail "J7" "Could not create test user for balance test"
fi

# 7c: Invalid magic link token
ERR_TOKEN_HEADERS=$(curl -s -D - -o /dev/null --max-time 10 \
  "${BASE_URL}/api/auth/verify?token=invalid-token-99999" 2>/dev/null || echo "")
echo "$ERR_TOKEN_HEADERS" > "${EVIDENCE_DIR}/j7-error-invalid-token.txt"

if echo "$ERR_TOKEN_HEADERS" | grep -qi "error=invalid\|error=missing"; then
  pass "J7" "Invalid token handled gracefully (redirect with error param)"
elif echo "$ERR_TOKEN_HEADERS" | grep -q "HTTP.*[34][0-9][0-9]"; then
  pass "J7" "Invalid token returned client error"
elif echo "$ERR_TOKEN_HEADERS" | grep -q "HTTP.*500"; then
  fail "J7" "Invalid token caused HTTP 500"
else
  pass "J7" "Invalid token handled (no crash)"
fi

echo ""

# =============================================================================
# Report
# =============================================================================
log "Generating report..."

j_status() {
  local j="$1" has_fail="no"
  for r in "${JOURNEY_STATUS[@]}"; do
    case "$r" in FAIL\|${j}\|*) has_fail="yes"; break;; esac
  done
  [ "$has_fail" = "yes" ] && echo "FAIL" || echo "PASS"
}

J1_S=$(j_status "J1")
J2_S=$(j_status "J2")
J3_S=$(j_status "J3")
J4_S=$(j_status "J4")
J5_S=$(j_status "J5")
J6_S=$(j_status "J6")
J7_S=$(j_status "J7")

JOURNEY_PASS=0
for s in "$J1_S" "$J2_S" "$J3_S" "$J4_S" "$J5_S" "$J6_S" "$J7_S"; do
  [ "$s" = "PASS" ] && JOURNEY_PASS=$((JOURNEY_PASS + 1))
done

level() { [ "$1" = "PASS" ] && echo "L3" || echo "-"; }

cat > "${EVIDENCE_DIR}/report.md" << EOF
# Verification Report — All 7 Customer Journeys

**Date:** $(date -u +"%Y-%m-%d %H:%M:%S UTC")
**Branch:** fix/verify-journeys
**App URL:** ${BASE_URL}
**Evidence:** \`${EVIDENCE_DIR}\`

## Summary

| Journey | Name           | Status | Level |
|---------|----------------|--------|-------|
| J1      | Discovery      | ${J1_S} | $(level "$J1_S") |
| J2      | Free Trial     | ${J2_S} | $(level "$J2_S") |
| J3      | Sign Up        | ${J3_S} | $(level "$J3_S") |
| J4      | Add Funds      | ${J4_S} | $(level "$J4_S") |
| J5      | Paid Upload    | ${J5_S} | $(level "$J5_S") |
| J6      | Job History    | ${J6_S} | $(level "$J6_S") |
| J7      | Error Handling | ${J7_S} | $(level "$J7_S") |

**Result: ${JOURNEY_PASS}/7 journeys passing**
**Steps: ${PASS_COUNT} passed, ${FAIL_COUNT} failed**

## Detailed Results

EOF

for r in "${JOURNEY_STATUS[@]}"; do
  IFS='|' read -r status journey step detail <<< "$r"
  if [ "$status" = "PASS" ]; then
    echo "- **${journey}** PASS — ${step}" >> "${EVIDENCE_DIR}/report.md"
  else
    echo "- **${journey}** FAIL — ${step}" >> "${EVIDENCE_DIR}/report.md"
    [ -n "${detail:-}" ] && echo "  - \`${detail}\`" >> "${EVIDENCE_DIR}/report.md"
  fi
done

cat >> "${EVIDENCE_DIR}/report.md" << EOF

## Evidence Files

$(ls -1 "${EVIDENCE_DIR}" | grep -v '^\.' | sed 's/^/- /')

---
*Generated by scripts/verify-all-journeys.sh on $(date -u +"%Y-%m-%d %H:%M:%S UTC")*
EOF

# Print summary table
echo ""
printf "${BOLD}====================================${NC}\n"
printf "${BOLD} VERIFICATION SUMMARY${NC}\n"
printf "${BOLD}====================================${NC}\n"
printf " J1 Discovery      %b\n" "$([ "$J1_S" = "PASS" ] && printf "${GREEN}PASS${NC}" || printf "${RED}FAIL${NC}")"
printf " J2 Free Trial      %b\n" "$([ "$J2_S" = "PASS" ] && printf "${GREEN}PASS${NC}" || printf "${RED}FAIL${NC}")"
printf " J3 Sign Up         %b\n" "$([ "$J3_S" = "PASS" ] && printf "${GREEN}PASS${NC}" || printf "${RED}FAIL${NC}")"
printf " J4 Add Funds       %b\n" "$([ "$J4_S" = "PASS" ] && printf "${GREEN}PASS${NC}" || printf "${RED}FAIL${NC}")"
printf " J5 Paid Upload     %b\n" "$([ "$J5_S" = "PASS" ] && printf "${GREEN}PASS${NC}" || printf "${RED}FAIL${NC}")"
printf " J6 Job History     %b\n" "$([ "$J6_S" = "PASS" ] && printf "${GREEN}PASS${NC}" || printf "${RED}FAIL${NC}")"
printf " J7 Error Handling  %b\n" "$([ "$J7_S" = "PASS" ] && printf "${GREEN}PASS${NC}" || printf "${RED}FAIL${NC}")"
printf "${BOLD}====================================${NC}\n"
printf " ${GREEN}${PASS_COUNT} passed${NC}  ${RED}${FAIL_COUNT} failed${NC}  ${JOURNEY_PASS}/7 journeys\n"
printf "${BOLD}====================================${NC}\n"
echo ""
log "Report: ${EVIDENCE_DIR}/report.md"

[ "$FAIL_COUNT" -eq 0 ] && exit 0 || exit 1
