# Claude Orchestrator Skill

**Orchestrating Multiple Coding Agents with Claude as the "Manager"**

This is a complete, production-ready implementation of the **Orchestrator → Worker** pattern for Claude Code.

Claude acts purely as the **project manager**. It never writes code itself. Instead it:

- Breaks down work using `tasks.yaml`
- Dispatches tasks to isolated headless coding agents (`opencode`, `cursor-agent`, `hermes`, etc.)
- Monitors progress via logs and git diffs
- Reviews output before recommending merges

---

## What's Included

| File/Folder                        | Purpose |
|------------------------------------|--------|
| `tasks.yaml` (root)                | Single source of truth project board |
| `orchestrator-mcp/`                | Full MCP server exposing orchestration tools |
| `.mcp.json`                        | Claude Code registration for the MCP server |
| `CLAUDE.md`                        | System instructions for Claude (the orchestrator) |
| `skills/claude-orchestrator/`      | This skill documentation + helpers |
| `scripts/`                         | Utility scripts (setup, monitor, etc.) |

---

## Prerequisites

- Claude Code (or Claude Desktop with MCP support)
- Node.js 18+ (for the MCP server)
- Git (worktrees support)
- One or more headless coding agents:
  - `opencode` (recommended)
  - `cursor-agent`
  - `aider` (as hermes fallback)
  - or any CLI that accepts a prompt and exits

---

## Quick Setup (One-Time)

```bash
cd /home/user/Altron

# 1. Install MCP server dependencies
cd orchestrator-mcp
npm install

# 2. Make sure worktrees exist (already created)
git worktree list

# 3. (Optional) Test the MCP server directly
node orchestrator-mcp/index.js
# (it should print startup message to stderr and wait)

# 4. Register with Claude Code (if not already)
# Claude Code will automatically pick up .mcp.json in project root
```

**Restart Claude Code** after the first setup so it loads the new MCP server.

---

## How to Use (The Orchestration Loop)

### 1. Start a new Claude Code session on the Altron project

Claude will automatically load:
- `CLAUDE.md` (orchestrator rules)
- The MCP tools via `.mcp.json`

### 2. Tell Claude:

> "You are the orchestrator. Read the current tasks and start working on them."

Or be more specific:

> "List all tasks, then dispatch T-001 using opencode"

### 3. Claude will:

1. Call `list_tasks()`
2. Call `dispatch_task(...)`
3. Periodically call `check_status(...)`
4. When done: `get_full_diff(...)` + `run_tests(...)`
5. Update status to `needs_review`
6. Present you with a summary + diff for approval

### 4. Human Review & Merge

When Claude says a task is ready:

```bash
# Example merge flow (Claude will tell you the exact commands)
git checkout main
git merge task/opencode-1 --no-ff
git branch -d task/opencode-1
git worktree remove ../work-opencode
```

---

## MCP Tools Reference (Available to Claude)

| Tool                | Description |
|---------------------|-----------|
| `list_tasks`        | Read entire `tasks.yaml` board |
| `get_task`          | Get one task by ID |
| `dispatch_task`     | Launch a worker agent in a worktree |
| `check_status`      | Get log tail + git diff --stat |
| `get_full_diff`     | Full unified diff of worker changes |
| `run_tests`         | Run tests inside the worktree |
| `update_task_status`| Change status + add notes |
| `create_worktree`   | Create new isolated worktree + branch |

---

## Architecture

```
Claude Code (Orchestrator)
        │
        ▼
   MCP Tools (orchestrator-mcp/index.js)
        │
        ├─→ opencode run "..."   (in ../work-opencode)
        ├─→ cursor-agent -p "..." (in ../work-cursor)
        └─→ hermes ...           (in ../work-hermes)
        │
   Each worker only touches its own branch/worktree
        │
   Claude inspects via:
        - .agent-log.txt
        - git diff
        - test output
```

---

## Adding a New Worker Tool

Edit `orchestrator-mcp/index.js`:

```js
const TOOL_CMDS = {
  opencode: (prompt, cwd) => ({ cmd: "opencode", args: ["run", prompt] }),
  cursor:   (prompt, cwd) => ({ cmd: "cursor-agent", args: ["-p", prompt, "--output-format", "json"] }),
  mynewagent: (prompt, cwd) => ({ cmd: "my-agent", args: ["--headless", prompt] }),
  // ...
};
```

Then update `CLAUDE.md` to mention the new tool.

---

## Background / Unattended Mode (Advanced)

For a true daemon that keeps orchestrating without you:

See `scripts/orchestrator-daemon.py` (Python example that uses the Anthropic API + MCP tools via subprocess).

Or use existing tools:
- **Claude Squad** (`smtg-ai/claude-squad`)
- **Vibe Kanban**

---

## Guardrails (Built-in)

- Workers are **never** given write access to `main`
- Every diff must be **reviewed** by Claude + human before merge
- `tasks.yaml` is the **only** source of truth
- Concurrency is limited (see `tasks.yaml` → `max_concurrent`)
- All logs and diffs are inspectable

---

## Files You Should Never Edit Manually (Let Claude do it)

- `tasks.yaml` (except when adding new high-level tasks)
- Any file inside `../work-*` directories

---

## Troubleshooting

**MCP server not appearing in Claude?**
- Restart Claude Code completely
- Check `claude mcp list` (or `/mcp` command inside Claude)
- Look at stderr of the server process

**Agent never finishes?**
- Check the log: `cat ../work-opencode/.agent-log.txt`
- Make sure the CLI tool actually exits when done

**Merge conflicts?**
- Claude should have flagged it as `conflict` status

---

**Version**: 1.0.0  
**Created**: 2026-07-20  
**Project**: Altron  
**Pattern**: Orchestrator → Worker (MCP + Git Worktrees)
