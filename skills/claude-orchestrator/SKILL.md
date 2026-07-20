---
name: claude-orchestrator
description: This skill should be used when the user wants Claude to orchestrate multiple headless coding agents (opencode, cursor-agent, aider, etc.) on a project — acting as engineering manager, splitting work 30/70, dispatching tasks to worker agents in git worktrees, monitoring progress, and escalating failures. Triggers include "orchestrate", "dispatch tasks to agents", "run the task board", "multi-agent coding", "be the orchestrator", or any request to coordinate parallel coding agents via tasks.yaml.
---

# Claude Orchestrator (Hybrid 30/70 Multi-Agent Manager)

Coordinate multiple headless coding agents on one project, with Claude as the
engineering manager. Follow the **hybrid 30/70 model**: plan every task, keep
the difficult ~30-40% (architecture, security, complex logic) for direct work,
delegate the long-but-easy ~60-70% to worker agents, and take over any task
after repeated agent failure.

## Requirements

- The project must contain a `tasks.yaml` board and register the bundled MCP
  server (`assets/orchestrator-mcp/`) via `.mcp.json`. If missing, run the
  bootstrap in **Setup** below.
- Node.js 18+, git. At least one headless agent CLI on PATH. Built-in workers:
  `opencode`, `codex`, `autoclaw`, `zcode`, `cursor`, `hermes`, plus `echo` for
  dry runs. Call `list_workers()` to see which are actually installed; add or
  override workers in `star.json` → `agents.commands` (no code changes needed).
- tmux tools and browser tools are optional extras (tmux on Linux/macOS only;
  browser needs `playwright` installed). All core tools work without them.

## Setup (once per project)

If the project has no `.mcp.json` entry for `claude-orchestrator`:

1. `npm install` inside `assets/orchestrator-mcp/` (of this skill, or of the
   project's copy).
2. Add to the project's `.mcp.json`, pointing at the server (path may be the
   globally installed skill copy):
   ```json
   {
     "mcpServers": {
       "claude-orchestrator": {
         "command": "node",
         "args": ["<path-to>/orchestrator-mcp/index.js"]
       }
     }
   }
   ```
   The server resolves `tasks.yaml` from its working directory (the project
   root). Override with the `ORCHESTRATOR_ROOT` env var when needed.
3. Create `tasks.yaml` (copy the schema from an existing board or
   `references/mcp-tools.md`), and worktrees:
   `git worktree add ../work-opencode -b task/opencode-1`.
4. Restart Claude Code so the MCP server loads.

## Core rules (never break)

1. **Plan first.** Start every session with `list_tasks()`, `list_workspaces()`,
   `get_notifications()`. Call `plan_task_split()` before dispatching or
   claiming any task.
2. **Split by difficulty.** Long/easy → `dispatch_task()` to a worker. Hard /
   security / architecture → `claim_task_for_claude()` and do it directly.
3. **One agent, one task.** Never give a worker two active tasks.
4. **Retry ceiling.** After each failed agent attempt call
   `increment_agent_retry(task_id)`. At 3 retries (auto or via
   `escalate_task()`), ownership moves to Claude — finish the task directly.
   **Model limits are handled below retries**: when a worker dies on a
   quota/rate-limit error, the server auto-redispatches on the next model in
   its chain (free models last). `check_status` reports `limit_hit: true` when
   this happened — do NOT count an auto-fallback as an agent retry.
5. **Review before merge.** Always `get_full_diff()` + `run_tests()` before
   marking `needs_review`. Never merge without human approval; provide merge
   commands instead.
6. **Keep the board truthful.** `update_task_status()` after every state
   change; tasks.yaml is the single source of truth.

## Workflow

```
0. list_workers() → know which agent CLIs are installed (dispatch only to those)
1. list_tasks() → pick pending tasks by priority
2. plan_task_split(task_id, claude_responsibility, agent_responsibility, difficulty)
3. easy/long → dispatch_task(tool, prompt, workdir, task_id)
   hard      → claim_task_for_claude(task_id, responsibility) → edit directly
4. Poll dispatched work: check_status(workdir) — log tail + diff stat + PID liveness
   Stuck/failed → increment_agent_retry(task_id) → (auto-)escalate_task at 3
5. Agent done → get_full_diff(workdir) + run_tests(workdir) → review
   Good → update_task_status(task_id, "needs_review") and present diff summary
   Bad  → increment_agent_retry and re-dispatch with corrective prompt
6. Human approves → output merge commands (git merge --no-ff, worktree remove)
```

Use `send_notification()` when dispatching, when an agent is waiting on input,
and on escalation — the notification panel is how the user tracks the swarm.

## Tool selection notes

- `dispatch_task` with `use_tmux: true` runs the agent inside a real tmux
  window (inspect via `tmux_capture`, `tmux_send`, `tmux_focus`). Only on
  systems with tmux; otherwise it falls back with an error — use normal mode.
- Browser tools (`launch_browser`, `navigate_browser`, `browser_click`,
  `get_browser_state`) drive a Playwright browser for verifying dev servers.
  They require `playwright` to be installed and report a clear error if not.
- `run_custom_command` executes commands defined in the project's `star.json`
  `custom_commands` map.

Full tool reference with parameters and the tasks.yaml schema:
`references/mcp-tools.md`. Worked end-to-end session example:
`references/example-usage.md`.

## Guardrails

- Workers never get write access to `main`; each works on its own branch in
  its own worktree.
- Respect `max_concurrent` from `tasks_metadata` when dispatching in parallel.
- Never edit files inside `../work-*` directories directly — inspect via the
  tools; direct edits belong only to tasks Claude has claimed.
