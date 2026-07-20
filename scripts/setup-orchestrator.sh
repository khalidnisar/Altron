#!/usr/bin/env bash
# Altron Orchestrator Skill - One-time Setup Script
# Run from the Altron root directory

set -euo pipefail

echo "🚀 Setting up Altron Claude Orchestrator Skill..."

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# 1. Ensure worktrees exist
echo "📁 Ensuring git worktrees..."
git worktree list

# Create any missing worktrees
if [ ! -d "/home/user/work-opencode" ]; then
    echo "Creating work-opencode..."
    git worktree add /home/user/work-opencode -b task/opencode-1 || true
fi

if [ ! -d "/home/user/work-cursor" ]; then
    echo "Creating work-cursor..."
    git worktree add /home/user/work-cursor -b task/cursor-1 || true
fi

if [ ! -d "/home/user/work-hermes" ]; then
    echo "Creating work-hermes..."
    git worktree add /home/user/work-hermes -b task/hermes-1 || true
fi

# 2. Install MCP server dependencies
echo "📦 Installing orchestrator-mcp dependencies..."
cd orchestrator-mcp
npm install
cd "$REPO_ROOT"

# 3. Make scripts executable
chmod +x scripts/*.sh 2>/dev/null || true

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
    "altron-orchestrator": {
      "command": "node",
      "args": ["/home/user/Altron/orchestrator-mcp/index.js"]
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
echo "  2. Open the Altron project"
echo "  3. Tell Claude: \"You are the orchestrator. Read tasks.yaml and start working.\""
echo ""
echo "Useful commands:"
echo "  git worktree list"
echo "  cat tasks.yaml"
echo "  node orchestrator-mcp/index.js   # (test MCP server manually)"
echo ""
echo "To add a new worktree later:"
echo "  git worktree add ../work-opencode-2 -b task/opencode-2"
