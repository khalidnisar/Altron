# 🎯 Claude Code Skill: Hybrid + star Orchestrator (v2.2)

> **The actual skill lives in [`skills/claude-orchestrator/`](skills/claude-orchestrator/SKILL.md)**
> (SKILL.md + references + bundled MCP server). Install by copying that folder
> to `~/.claude/skills/claude-orchestrator`. This file is a historical summary.

**Title:** Orchestrating Multiple Coding Agents (Hybrid 30/70 + star features)

## What This Skill Now Includes

### Core Hybrid Model (from previous version)
- Claude plans every task
- Claude keeps 30-40% hard work (`claim_task_for_claude`)
- Sub-agents do long/easy work
- Automatic escalation after 3 retries

### star Features Integrated (portable analogs)

| star Feature                  | Our Implementation                                      | MCP Tool(s) |
|-------------------------------|---------------------------------------------------------|-------------|
| **Vertical tabs / Sidebar**   | Rich workspace metadata (branch, ports, owner, last note) | `list_workspaces` |
| **Notification rings + panel**| Agents "light up" when waiting. Full history panel     | `send_notification`, `get_notifications` |
| **Scriptable in-app browser** | Full Playwright control (click, fill, navigate, eval)  | `launch_browser`, `navigate_browser`, `browser_click`, `get_browser_state` |
| **Custom commands**           | Project commands from `star.json` (command palette)    | `run_custom_command` |
| **Hooks**                     | Post-dispatch, on-waiting, on-escalate hooks           | `scripts/star/hooks/` + `star-notify.js` |
| **Workspace metadata**        | `workspaces.yaml` (git, ports, notifications)          | Auto-updated |
| **Programmable**              | Everything exposed as first-class MCP tools            | All above |

---

## Key Files Added/Updated for star

- `star.json` — configuration + custom commands
- `workspaces.yaml` — sidebar state
- `orchestrator-mcp/star-notify.js`
- `orchestrator-mcp/star-browser.js` (Playwright)
- `orchestrator-mcp/star-integration.js`
- `scripts/star/hooks/`
- New MCP tools in `orchestrator-mcp/index.js`

---

## How Claude Should Use the New Features

**Every session start:**
```json
list_tasks()
list_workspaces()          // star sidebar
get_notifications()
```

**When dispatching:**
```json
dispatch_task(...)
send_notification({
  "task_id": "T-001",
  "message": "Waiting on auth error handling",
  "type": "waiting"
})
```

**When needing browser interaction:**
```json
launch_browser({ "headless": false })
navigate_browser({ "url": "http://localhost:8080" })
browser_click({ "selector": "#login-button" })
```

**Custom commands:**
```json
run_custom_command({ "name": "test-all" })
```

---

## Current Status

✅ Hybrid 30/70 model  
✅ Full star-inspired workspace + notification system  
✅ Scriptable browser (Playwright)  
✅ Hooks + notify CLI  
✅ Custom commands  
✅ Updated CLAUDE.md with star guidance

**Version**: 2.1.0 (Hybrid + star)
