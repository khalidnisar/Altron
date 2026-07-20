# star Features Integrated into Altron Orchestrator

## What We Studied from https://github.com/manaflow-ai/star

star is a **native macOS terminal** (Swift + libghostty) built specifically for running many AI coding agents in parallel. Key innovations:

### Core star Differentiators
- Rich sidebar (vertical tabs) showing per-workspace: git branch, PR #, cwd, listening ports, **latest notification**
- **Notification rings** — panes + tabs visually indicate when an agent is waiting
- Notification panel + quick jump (Cmd+I / Cmd+Shift+U)
- Built-in **scriptable browser** pane (agents can control it programmatically)
- `star notify` + hooks system for agents to signal "I need attention"
- `star.json` for custom commands (command palette)
- Full programmability via CLI + socket

## What We Added (Portable Version)

Because we are on Linux/headless (no macOS GUI or Ghostty), we implemented **high-fidelity logical analogs** inside the existing MCP orchestrator.

### 1. Workspaces Sidebar (`list_workspaces`)
- `workspaces.yaml` — acts as the "sidebar"
- Tracks per workspace:
  - task_id, name, workdir, branch, owner
  - git_status, listening_ports
  - last_notification, notification_count
  - split preference

**MCP Tool:** `list_workspaces`

### 2. Notification System (`send_notification` / `get_notifications`)
- Equivalent to star "blue rings + notification panel"
- Stored in `.star-notifications.json`
- Types: `waiting`, `done`, `error`, `info`, `stuck`
- Auto-appended to agent `.agent-log.txt`
- Updates `workspaces.yaml`

**MCP Tools:**
- `send_notification`
- `get_notifications`

**CLI:** `node orchestrator-mcp/star-notify.js`

### 3. Scriptable Browser (Playwright)
- Full equivalent of star's in-app browser with agent control
- Tools exposed:
  - `launch_browser`
  - `navigate_browser`
  - `browser_click`
  - `get_browser_state`

**File:** `orchestrator-mcp/star-browser.js`

### 4. Custom Commands
- `star.json` → `custom_commands`
- Run via `run_custom_command`

### 5. Hooks System
- `scripts/star/hooks/`
  - `post-dispatch.sh`
  - `on-agent-waiting.sh` (template)
  - `on-escalate.sh` (template)
- `star-notify.js` used by hooks

### 6. Auto-Integration
- Dispatch now writes `[star]` markers
- `list_workspaces()` + `get_notifications()` encouraged at session start
- Updated `CLAUDE.md` with star guidance

## New MCP Tools (Total ~20)

Hybrid tools (previous) + new star tools:
- `list_workspaces`
- `send_notification`
- `get_notifications`
- `launch_browser`
- `navigate_browser`
- `browser_click`
- `get_browser_state`
- `run_custom_command`

## Files Added/Changed for star

```
star.json
workspaces.yaml
orchestrator-mcp/star-notify.js
orchestrator-mcp/star-browser.js
orchestrator-mcp/star-integration.js
scripts/star/hooks/
scripts/star-status.sh
orchestrator-mcp/index.js   ← +8 new tools
CLAUDE.md                   ← star instructions
```

## Usage Example in Claude

```text
You are the hybrid orchestrator with star awareness.

1. list_tasks()
2. list_workspaces()          # see sidebar
3. get_notifications()        # see what needs attention

Then dispatch + send_notification when agents are waiting.
Use the browser tools when needed.
```

## Trade-offs

- No real GUI / Ghostty terminal (we are headless)
- No native tmux-style multiplexing (scripts can still use tmux if installed on host)
- Browser is Playwright instead of embedded WebKit
- All features are exposed via **MCP tools** so Claude can control everything programmatically

This gives us **most of the value** of star (visibility, notifications, browser control, hooks, programmability) without requiring a macOS GUI.

**Version**: 2.1.0
