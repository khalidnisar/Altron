# Claude Orchestrator Skill

**Orchestrating Multiple Coding Agents with Claude as the "Manager"**

A self-contained Claude Code skill implementing the **Hybrid Orchestrator → Worker**
pattern: Claude plans every task, keeps the difficult ~30-40% for itself,
dispatches the long-but-easy ~60-70% to headless coding agents in isolated git
worktrees, monitors progress, and escalates (takes over) after 3 failed retries.

```
skills/claude-orchestrator/
├── SKILL.md                       ← skill entry point (Claude loads this)
├── README.md                      ← this file (for humans)
├── references/
│   ├── mcp-tools.md               ← full MCP tool reference + tasks.yaml schema
│   └── example-usage.md           ← worked end-to-end session
└── assets/
    └── orchestrator-mcp/          ← the MCP server (Node 18+, 25+ tools)
```

## Install as a global skill

```bash
# Copy the whole folder into your Claude Code skills directory:
#   Linux/macOS:  ~/.claude/skills/claude-orchestrator
#   Windows:      %USERPROFILE%\.claude\skills\claude-orchestrator
cd ~/.claude/skills/claude-orchestrator/assets/orchestrator-mcp
npm install
```

## Wire it into a project

Add to the project's `.mcp.json` (create if missing):

```json
{
  "mcpServers": {
    "claude-orchestrator": {
      "command": "node",
      "args": ["<absolute-or-relative-path>/orchestrator-mcp/index.js"]
    }
  }
}
```

The server reads `tasks.yaml`, `star.json`, and `workspaces.yaml` from its
**working directory** (Claude Code launches MCP servers at the project root).
Running it manually from elsewhere? Set `ORCHESTRATOR_ROOT=/path/to/project`.

Then create the task board and worktrees:

```bash
# starter board — full schema in references/mcp-tools.md
$EDITOR tasks.yaml
git worktree add ../work-opencode -b task/opencode-1
```

Restart Claude Code and say:

> "You are the orchestrator. Read the current tasks and start working on them."

## Prerequisites

- Claude Code (or Claude Desktop with MCP support)
- Node.js 18+ and git
- One or more headless agent CLIs on PATH: `opencode`, `cursor-agent`,
  `aider`, or any CLI that accepts a prompt and exits. No agent installed?
  Use the built-in `echo` tool for dry runs.
- Optional: `tmux` (Linux/macOS) for multiplexed agent windows; `playwright`
  for the scriptable browser tools.

Works on Windows: the server auto-detects the platform (gradlew.bat, cmd
shims, no tmux → graceful fallback to detached-process mode).

## Guardrails (built in)

- Workers never touch `main` — each works on its own branch in its own worktree
- Every diff is reviewed by Claude + human before merge; Claude only outputs
  merge commands, never merges
- `tasks.yaml` is the single source of truth; `max_concurrent` limits parallelism
- 3-retry ceiling per agent per task, then automatic escalation to Claude
- All logs (`.agent-log.txt`), PIDs, and diffs are inspectable

## Troubleshooting

**MCP server not appearing?** Restart Claude Code fully; check `/mcp`; run
`node assets/orchestrator-mcp/index.js` from the project root and read stderr.

**Agent never finishes?** `cat ../work-<agent>/.agent-log.txt`; make sure the
CLI actually exits when done.

**Browser tools error?** `npm install playwright && npx playwright install chromium`
inside `assets/orchestrator-mcp/`.

## Changelog

**2.2.0** (2026-07-20)
- Proper `SKILL.md` with frontmatter — installable as a real Claude Code skill
- Self-contained layout: MCP server moved into `assets/orchestrator-mcp/`
- Portable: project root resolved from cwd/`ORCHESTRATOR_ROOT` (no more
  hardcoded `/home/user`); Windows support (spawn shims, gradlew.bat, tmpdir)
- Real YAML parsing (`js-yaml`): hybrid fields (`retry_count`, `owner`,
  `difficulty`, …) now actually read — fixes retry/escalation never triggering
- Fixed `send_notification` crash (ESM `require`, wrong export name) and
  workspace updates matching the wrong entry
- `plan_task_split` now persists `difficulty` + responsibilities to tasks.yaml
- Task fields missing from a block are inserted instead of silently dropped
- `update_task_status` accepts `escalated`; `run_tests` detects project type
  (gradlew / npm / cargo / pytest) and reports pass/fail
- tmux commands use `execFileSync` (quoting-safe); prompts shell-escaped
- Playwright is lazy-loaded with a clear install hint instead of crashing
- Hooks no longer append raw lines to `workspaces.yaml` (YAML corruption)

**2.1.0** — STAR-style workspaces, notifications, browser, tmux deep emulation
**2.0.0** — Hybrid 30/70 model, retries, escalation
**1.0.0** — Initial orchestrator → worker pattern

---

**Pattern**: Hybrid Orchestrator → Worker (MCP + Git Worktrees)
**Author**: Khalid Nisar
