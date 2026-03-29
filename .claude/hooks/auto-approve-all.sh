#!/bin/bash
# Auto-approve all permission requests for autonomous agent operation.
# This hook runs on every PermissionRequest event and returns an "allow" decision.
# SAFETY: Only use in trusted agent environments with --dangerously-skip-permissions.
cat > /dev/null &
echo '{"hookSpecificOutput":{"hookEventName":"PermissionRequest","permissionDecision":"allow","permissionDecisionReason":"auto-approved by hook"}}'
exit 0
