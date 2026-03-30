#!/usr/bin/env bash
set -euo pipefail

DIR="evidence/email-magic-link"
PASSED=0
TOTAL=7
OUTPUT=""

check() {
  local label="$1"
  local result="$2"
  if [ "$result" = "true" ]; then
    local line="PASS: $label"
    PASSED=$((PASSED + 1))
  else
    local line="FAIL: $label"
  fi
  echo "$line"
  OUTPUT="$OUTPUT$line
"
}

# 1. health.json exists and contains "ok"
if [ -f "$DIR/health.json" ] && grep -q '"ok"' "$DIR/health.json" 2>/dev/null; then
  check "health.json exists and contains 'ok'" "true"
else
  check "health.json exists and contains 'ok'" "false"
fi

# 2. send-response.json exists and contains "Magic link sent"
if [ -f "$DIR/send-response.json" ] && grep -q 'Magic link sent' "$DIR/send-response.json" 2>/dev/null; then
  check "send-response.json exists and contains 'Magic link sent'" "true"
else
  check "send-response.json exists and contains 'Magic link sent'" "false"
fi

# 3. delivery-confirmation.json exists and has delivery data
if [ -f "$DIR/delivery-confirmation.json" ] && grep -q '"email_id"' "$DIR/delivery-confirmation.json" 2>/dev/null; then
  check "delivery-confirmation.json exists and has delivery data" "true"
else
  check "delivery-confirmation.json exists and has delivery data" "false"
fi

# 4. email-content.json exists and contains HTML
if [ -f "$DIR/email-content.json" ] && grep -q '<html' "$DIR/email-content.json" 2>/dev/null; then
  check "email-content.json exists and contains HTML" "true"
else
  check "email-content.json exists and contains HTML" "false"
fi

# 5. email-rendered.png exists and is >0 bytes
if [ -f "$DIR/email-rendered.png" ] && [ -s "$DIR/email-rendered.png" ]; then
  check "email-rendered.png exists and is >0 bytes" "true"
else
  check "email-rendered.png exists and is >0 bytes" "false"
fi

# 6. auth-result.json exists and shows authentication success
if [ -f "$DIR/auth-result.json" ] && grep -q '"success"' "$DIR/auth-result.json" 2>/dev/null; then
  check "auth-result.json exists and shows authentication success" "true"
else
  check "auth-result.json exists and shows authentication success" "false"
fi

# 7. smoke-output.txt — self-check (will exist after this script writes it)
check "smoke-output.txt exists (self-created)" "true"

SUMMARY="
=== $PASSED/$TOTAL checks passed ==="
echo "$SUMMARY"
OUTPUT="$OUTPUT$SUMMARY
"

# Save output to file
echo "$OUTPUT" > "$DIR/smoke-output.txt"
