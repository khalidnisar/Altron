#!/usr/bin/env bash
# STAR-style post-dispatch hook
# Called after dispatch_task

TASK_ID="$1"
WORKER="$2"
WORKDIR="$3"

REPO_ROOT="${ORCHESTRATOR_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
NOTIFY="$REPO_ROOT/skills/claude-orchestrator/assets/orchestrator-mcp/star-notify.js"

echo "[star-hook] post-dispatch: $TASK_ID -> $WORKER ($WORKDIR)" >&2

# Notify via star-notify (updates .star-notifications.json; the MCP server
# keeps workspaces.yaml in sync — no raw appends here)
node "$NOTIFY" \
  --task "$TASK_ID" \
  --message "Dispatched to $WORKER" \
  --type "info" \
  --workdir "$WORKDIR" || true
