#!/usr/bin/env bash
# Start the Altron Orchestrator inside a tmux session with nice layout
# This gives you the full STAR-style experience

set -euo pipefail

SESSION="altron-orchestrator"

if ! command -v tmux &>/dev/null; then
  echo "tmux is not installed. Please install it first."
  exit 1
fi

cd "$(dirname "$0")/../../.."

# Kill old session if exists
tmux kill-session -t "$SESSION" 2>/dev/null || true

# Create main session
tmux new-session -d -s "$SESSION" -n "orchestrator" -c "$PWD"

# Split: left = Claude / orchestrator, right = status
tmux split-window -h -t "$SESSION:orchestrator" -p 30

# Bottom pane for logs
tmux split-window -v -t "$SESSION:orchestrator" -p 25

# Set up panes
tmux send-keys -t "$SESSION:orchestrator.0" 'echo "=== Altron Orchestrator (Main) ==="' C-m
tmux send-keys -t "$SESSION:orchestrator.1" 'watch -n 3 "node -e \"const m=require(\\\"./orchestrator-mcp/tmux-integration.js\\\"); console.log(JSON.stringify(m.getTmuxStatus(),null,2))\" 2>/dev/null || echo \"tmux status\"" ' C-m
tmux send-keys -t "$SESSION:orchestrator.2" 'tail -f .star-notifications.json 2>/dev/null || echo "No notifications yet"' C-m

tmux select-pane -t "$SESSION:orchestrator.0"

echo "✅ Started tmux session: $SESSION"
echo ""
echo "Attach with: tmux attach -t $SESSION"
echo "Inside the session you can run Claude Code or the MCP server."
echo ""
echo "Useful tmux commands from inside:"
echo "  Prefix + d          detach"
echo "  Prefix + c          new window (agent workspace)"
echo "  Prefix + space      next layout"
