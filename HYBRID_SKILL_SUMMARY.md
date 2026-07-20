# Claude Hybrid Orchestrator Skill — Summary

## What the Skill Is

A **Claude Code skill** that turns Claude into a **smart hybrid project manager** for multi-agent coding.

Instead of Claude doing 100% of the work or delegating 100%, it follows a deliberate **30/70 split**:

- **Claude does 30-40%** — the hard, complex, architectural, or high-risk parts.
- **Sub-agents do 60-70%** — long, repetitive, or relatively easy implementation work.

## Core Philosophy

> "I plan → I keep the difficult parts → I delegate the long easy parts → I rescue when agents fail."

## How It Works (Step by Step)

1. **Planning Phase** (mandatory)
   - Claude calls `list_tasks()`
   - For every task, Claude **must** call `plan_task_split()` first
   - In the plan it explicitly states:
     - What **Claude** will do (the hard 30-40%)
     - What the **agent** will do (the long/easy part)

2. **Distribution**
   - Easy / long / repetitive tasks → dispatched to `opencode`, `cursor`, or `hermes`
   - Hard / complex tasks → Claude claims them with `claim_task_for_claude()`

3. **Monitoring**
   - Claude polls agents using `check_status()`
   - Agents work in completely isolated git worktrees

4. **Failure Handling (Critical)**
   - After every agent failure, Claude calls `increment_agent_retry(task_id)`
   - Maximum **3 retries** per agent per task
   - On the 3rd failure or when stuck → Claude calls `escalate_task()`
   - Once escalated:
     - `owner` becomes `"claude"`
     - `escalated: true`
     - Claude finishes the task **itself**

5. **Review & Merge**
   - Same review flow as before (`get_full_diff` + tests)
   - Human must still approve merges

## Key New Tools (MCP)

| Tool                     | Purpose                                      | Who Calls It |
|--------------------------|----------------------------------------------|--------------|
| `plan_task_split`        | Define Claude's hard part vs agent's easy part | Claude (first) |
| `claim_task_for_claude`  | Claude takes ownership of difficult work     | Claude |
| `dispatch_task`          | Send easy/long work to sub-agents            | Claude |
| `increment_agent_retry`  | Track failures (auto-escalates at 3)         | Claude |
| `escalate_task`          | Force Claude to finish a stuck task          | Claude |
| `check_status` / `get_full_diff` | Monitor & review                        | Claude |

## Task Board Fields (tasks.yaml)

```yaml
difficulty: easy | medium | hard
retry_count: 0-3
escalated: true/false
owner: "opencode" | "cursor" | "hermes" | "claude"
claude_responsibility: "..."
agent_responsibility: "..."
```

## Guardrails

- Claude **must** plan every task
- Sub-agents get **max 3 retries**
- One agent = one active task
- Claude cannot ignore stuck agents — escalation is mandatory
- Human approval still required for all merges

## Files

- `CLAUDE.md` — Strict hybrid instructions
- `tasks.yaml` — Enhanced task board
- `orchestrator-mcp/index.js` — MCP server with hybrid tools
- `.mcp.json` — Registration
- `SKILL_CLAUDE_ORCHESTRATOR.md` — Overview

**Version**: 2.0.0 (Hybrid Model)
