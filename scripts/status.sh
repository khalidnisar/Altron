#!/usr/bin/env bash
# Quick status for the orchestrator
# Run from Altron root

echo "=== Altron Orchestrator Status ==="
echo ""
echo "Git worktrees:"
git worktree list
echo ""

echo "Current tasks (from tasks.yaml):"
if [ -f tasks.yaml ]; then
    grep -E '^- id:|^  title:|^  assigned_to:|^  status:' tasks.yaml | head -30
else
    echo "tasks.yaml not found"
fi
echo ""

echo "MCP Server package:"
if [ -d orchestrator-mcp/node_modules ]; then
    echo "✅ orchestrator-mcp installed"
else
    echo "❌ Run: cd orchestrator-mcp && npm install"
fi
echo ""

echo "To start manual MCP test:"
echo "  node orchestrator-mcp/index.js"
echo ""
echo "In Claude Code, the tools should be available after restart."
