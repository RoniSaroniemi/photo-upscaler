#!/usr/bin/env bash
set -euo pipefail

EVIDENCE_DIR="$(cd "$(dirname "$0")/.." && pwd)/evidence/auth-journey"
PASS=0
FAIL=0

check_file() {
  local file="$1"
  local path="$EVIDENCE_DIR/$file"
  if [ -f "$path" ] && [ -s "$path" ]; then
    echo "PASS: $file ($(wc -c < "$path" | tr -d ' ') bytes)"
    PASS=$((PASS + 1))
  else
    echo "FAIL: $file"
    FAIL=$((FAIL + 1))
  fi
}

echo "=== Auth Journey Smoke Test ==="
echo "Evidence dir: $EVIDENCE_DIR"
echo ""

check_file "01-homepage.png"
check_file "02-login-page.png"
check_file "03-check-email.png"
check_file "04-email-rendered.png"
check_file "05-verify-landing.png"
check_file "06-authenticated.png"
check_file "journey-report.md"

echo ""
echo "Results: $PASS passed, $FAIL failed"

if [ "$FAIL" -gt 0 ]; then
  exit 1
fi
echo "All checks passed."
