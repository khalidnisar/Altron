#!/usr/bin/env bash
# STAR-style tmux workspace creator for Altron Orchestrator
# Creates a dedicated tmux session + window for an agent workspace

set -euo pipefail

TASK_ID="${1:-}"
WORKER="${2:-}"
WORKDIR="${3:-}"
SESSION_NAME="${4:-altron-${TASK_ID}}"

if [ -z "$TASK_ID" ]; then
  echo "Usage: $0 <TASK_ID> <WORKER> <WORKDIR> [SESSION_NAME]" >&2
  exit 1
fi

if ! command -v tmux &> /dev/null; then
  echo "ERROR: tmux is not installed. Install with: sudo apt install tmux" >&2
  echo "Falling back to non-tmux mode." >&2
  exit 2
fi

# Normalize session name (tmux limits + safe chars)
SESSION_NAME=$(echo "$SESSION_NAME" | tr -cd '[:alnum:]_-' | cut -c1-32)
WINDOW_NAME="${TASK_ID}-${WORKER}"

# Create session if it doesn't exist
if ! tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
  tmux new-session -d -s "$SESSION_NAME" -n "$WINDOW_NAME" -c "$(realpath "$WORKDIR")"
  echo "[tmux] Created new session: $SESSION_NAME"
else
  # Create new window in existing session
  tmux new-window -t "$SESSION_NAME:" -n "$WINDOW_NAME" -c "$(realpath "$WORKDIR")"
  echo "[tmux] Added window to existing session: $SESSION_NAME:$WINDOW_NAME"
fi

# Set some useful options per window
tmux set-option -t "$SESSION_NAME:$WINDOW_NAME" automatic-rename off
tmux set-option -t "$SESSION_NAME:$WINDOW_NAME" allow-rename off

# Send initial banner
tmux send-keys -t "$SESSION_NAME:$WINDOW_NAME" "echo '=== Altron star Workspace: $TASK_ID ($WORKER) ==='" C-m
tmux send-keys -t "$SESSION_NAME:$WINDOW_NAME" "echo 'Workdir: $(pwd)'" C-m
tmux send-keys -t "$SESSION_NAME:$WINDOW_NAME" "echo 'Branch: $(git branch --show-current 2>/dev/null || echo main)'" C-m
tmux send-keys -t "$SESSION_NAME:$WINDOW_NAME" "echo 'Ready for agent commands...'" C-m

echo "$SESSION_NAME:$WINDOW_NAME"
