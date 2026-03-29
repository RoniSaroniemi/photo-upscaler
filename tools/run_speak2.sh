#!/bin/bash
# Launch the Speak2 voice transcription service
# TEMPORARY: Uses bundled binary from vendor/speak2/
set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SPEAK2_APP="$SCRIPT_DIR/../vendor/speak2/Speak2.app"

if [ ! -d "$SPEAK2_APP" ]; then
  echo "Speak2 not found at $SPEAK2_APP"
  echo "Voice transcription will not be available."
  exit 1
fi

echo "Starting Speak2 voice transcription service..."
open "$SPEAK2_APP"
echo "Speak2 launched. Service should be available at http://127.0.0.1:8768"
echo "Check health: curl -s http://127.0.0.1:8768/health"
