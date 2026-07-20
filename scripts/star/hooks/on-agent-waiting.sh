#!/usr/bin/env bash
# STAR-style hook: called when an agent appears to be waiting

TASK_ID="$1"
MESSAGE="$2"

echo "[star] Agent waiting: $TASK_ID - $MESSAGE" >&2

node /home/user/Altron/orchestrator-mcp/star-notify.js \
  --task "$TASK_ID" \
  --message "$MESSAGE" \
  --type "waiting" || true
