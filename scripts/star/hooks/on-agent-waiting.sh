#!/usr/bin/env bash
# STAR-style hook: called when an agent appears to be waiting

TASK_ID="$1"
MESSAGE="$2"

REPO_ROOT="${ORCHESTRATOR_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
NOTIFY="$REPO_ROOT/skills/claude-orchestrator/assets/orchestrator-mcp/star-notify.js"

echo "[star] Agent waiting: $TASK_ID - $MESSAGE" >&2

node "$NOTIFY" \
  --task "$TASK_ID" \
  --message "$MESSAGE" \
  --type "waiting" || true
