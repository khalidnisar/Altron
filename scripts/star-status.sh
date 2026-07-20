#!/usr/bin/env bash
# STAR-style status for Altron Orchestrator

echo "=== Altron star-Style Orchestrator Status ==="
echo ""

echo "Workspaces (sidebar):"
if [ -f workspaces.yaml ]; then
  grep -E '^- id:|^  task_id:|^  name:|^  owner:|^  status:' workspaces.yaml | head -20
else
  echo "  (no workspaces.yaml)"
fi
echo ""

echo "Notifications:"
if [ -f .star-notifications.json ]; then
  node -e '
    const d = require("./.star-notifications.json");
    console.log("  Unread:", d.unread || 0);
    console.log("  Latest:", (d.notifications?.[0]?.message || "none"));
  ' 2>/dev/null || cat .star-notifications.json | head -c 300
else
  echo "  (no notifications yet)"
fi
echo ""

echo "star.json custom commands:"
if [ -f star.json ]; then
  node -e '
    const c = require("./star.json");
    console.log(Object.keys(c.custom_commands || {}).join(", "));
  ' 2>/dev/null
fi
echo ""

echo "MCP server has star tools:"
grep -o '"[^"]*browser[^"]*"' skills/claude-orchestrator/assets/orchestrator-mcp/index.js | head -5 || echo "  (check index.js)"

echo ""
echo "To test browser: node skills/claude-orchestrator/assets/orchestrator-mcp/star-browser.js"
echo "To send notify: node skills/claude-orchestrator/assets/orchestrator-mcp/star-notify.js --message 'test'"
