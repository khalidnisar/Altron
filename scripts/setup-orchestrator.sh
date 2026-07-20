#!/usr/bin/env bash
# Claude Orchestrator Skill - One-time Setup Script
# Run from the project root directory (any machine — no hardcoded paths)

set -euo pipefail

echo "🚀 Setting up Claude Orchestrator Skill..."

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
MCP_DIR="$REPO_ROOT/skills/claude-orchestrator/assets/orchestrator-mcp"

# 1. Ensure worktrees exist (siblings of the repo root)
echo "📁 Ensuring git worktrees..."
git worktree list

for worker in opencode cursor hermes; do
    WT="$REPO_ROOT/../work-$worker"
    if [ ! -d "$WT" ]; then
        echo "Creating work-$worker..."
        git worktree add "$WT" -b "task/$worker-1" || true
    fi
done

# 2. Install MCP server dependencies
echo "📦 Installing orchestrator-mcp dependencies..."
(cd "$MCP_DIR" && npm install)

# 3. Make scripts executable
chmod +x scripts/*.sh scripts/star/hooks/*.sh scripts/star/tmux/*.sh 2>/dev/null || true

# 4. Verify tasks.yaml
echo "📋 Verifying tasks.yaml..."
if [ -f tasks.yaml ]; then
    echo "✅ tasks.yaml found"
else
    echo "❌ tasks.yaml missing!"
    exit 1
fi

# 5. Check for .mcp.json
if [ -f .mcp.json ]; then
    echo "✅ .mcp.json found (Claude Code will auto-register the MCP server)"
else
    echo "⚠️  .mcp.json missing — creating now..."
    cat > .mcp.json << 'EOF'
{
  "mcpServers": {
    "claude-orchestrator": {
      "command": "node",
      "args": ["skills/claude-orchestrator/assets/orchestrator-mcp/index.js"]
    }
  }
}
EOF
fi

# 6. Show next steps
echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "  1. Restart Claude Code (or Claude Desktop) completely"
echo "  2. Open this project"
echo "  3. Tell Claude: \"You are the orchestrator. Read tasks.yaml and start working.\""
echo ""
echo "Useful commands:"
echo "  git worktree list"
echo "  cat tasks.yaml"
echo "  node \"$MCP_DIR/index.js\"   # (test MCP server manually — run from project root)"
echo ""
echo "To add a new worktree later:"
echo "  git worktree add ../work-opencode-2 -b task/opencode-2"
