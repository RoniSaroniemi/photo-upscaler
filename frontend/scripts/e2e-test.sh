#!/bin/bash
# scripts/e2e-test.sh — Run E2E tests with trial reset
# Usage: cd frontend && bash scripts/e2e-test.sh
set -euo pipefail

BASE_URL="${E2E_BASE_URL:-http://localhost:3001}"
EVIDENCE_DIR="evidence/e2e-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$EVIDENCE_DIR"

echo "=== Checking app is running on $BASE_URL ==="
if ! curl -sf "$BASE_URL/api/health" > /dev/null 2>&1; then
  echo "App not running. Starting on port 3001..."
  PORT=3001 npm run dev &
  APP_PID=$!
  echo "Waiting for app to start (PID $APP_PID)..."
  for i in $(seq 1 30); do
    if curl -sf "$BASE_URL/api/health" > /dev/null 2>&1; then
      echo "App ready."
      break
    fi
    if [ "$i" -eq 30 ]; then
      echo "ERROR: App failed to start within 30s"
      kill "$APP_PID" 2>/dev/null || true
      exit 1
    fi
    sleep 1
  done
fi

echo "=== Resetting trial ==="
curl -sf -X DELETE "$BASE_URL/api/test/trial-reset" | tee "$EVIDENCE_DIR/trial-reset.json"
echo ""

echo "=== Running Playwright tests ==="
E2E_BASE_URL="$BASE_URL" npx playwright test --reporter=list 2>&1 | tee "$EVIDENCE_DIR/playwright-output.txt"

echo ""
echo "=== Done. Evidence saved to $EVIDENCE_DIR/ ==="
