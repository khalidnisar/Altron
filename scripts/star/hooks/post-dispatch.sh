#!/usr/bin/env bash
# STAR-style post-dispatch hook
# Called after dispatch_task

TASK_ID="$1"
WORKER="$2"
WORKDIR="$3"

echo "[star-hook] post-dispatch: $TASK_ID -> $WORKER ($WORKDIR)" >&2

# Notify via star-notify
node /home/user/Altron/orchestrator-mcp/star-notify.js \
  --task "$TASK_ID" \
  --message "Dispatched to $WORKER" \
  --type "info" \
  --workdir "$WORKDIR" || true

# Update workspaces.yaml (simple append)
echo "  last_notification: \"Dispatched to $WORKER\"" >> /home/user/Altron/workspaces.yaml 2>/dev/null || true
