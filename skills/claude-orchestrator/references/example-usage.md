# Example Usage Walkthrough

## Initial Session (First Time)

1. Open Claude Code on the project folder (the one containing `tasks.yaml` and `.mcp.json`).
2. Claude should detect `CLAUDE.md` and the MCP server via `.mcp.json`.
3. Send this message:

```
You are the Lead Orchestrator. 
Please:
1. Call list_tasks() to read the current board.
2. Tell me what tasks are pending.
3. Dispatch the highest priority one using the appropriate tool.
```

Claude will:
- Use the `list_tasks` tool
- Decide between `opencode` / `cursor` / etc.
- Call `dispatch_task`
- Update status to `running`

## Monitoring a Running Task

After dispatch, you can say:

```
Check on the running task. Use check_status on the appropriate workdir.
```

Claude will poll and report progress from the agent's log + git diff.

## Reviewing a Completed Task

When the agent appears finished:

```
The worker seems done. Please:
- get_full_diff
- run_tests
- Review the changes
- Update the task status if appropriate
```

Claude will present you with:
- Full diff
- Test results
- Recommendation (needs_review / failed)

## Approving & Merging (Human Step)

Claude will **never** merge automatically.

When it says "Ready for review", you decide.

Typical commands Claude will recommend:

```bash
# From the main Altron checkout
git checkout main
git merge task/opencode-1 --no-ff -m "feat: add error handling (T-001)"
git branch -d task/opencode-1
git worktree remove ../work-opencode
```

## Adding New Tasks

You can either:
1. Edit `tasks.yaml` manually (add new `- id: T-XXX` entry)
2. Or ask Claude:

> "Add a new task: 'Improve notification permission handling'. Assign to opencode. Priority high."

Claude will update `tasks.yaml` via the `update_task_status` tool (or you can do it yourself).

## Parallel Work (Multiple Agents)

Claude can dispatch multiple tasks at once (up to `max_concurrent`).

Example prompt:

```
Dispatch T-001 to opencode and T-002 to cursor at the same time.
```

Then poll both workdirs.

## Using the "echo" Tool for Testing

Great for dry-runs:

```
dispatch_task({
  tool: "echo",
  prompt: "Pretend to implement X",
  workdir: "../work-opencode",
  task_id: "T-001"
})
```

It will just echo the prompt into the log without running a real agent.

## Full End-to-End Example Session

**User:** Start orchestrating.

**Claude actions (via tools):**

1. `list_tasks()` → sees T-001 pending (high)
2. `dispatch_task("opencode", "...", "../work-opencode", "T-001")`
3. `update_task_status("T-001", "running")`

**User waits a few minutes**

**User:** Check progress on all tasks.

**Claude:**
- `check_status("../work-opencode")` → sees diff + log tail showing progress
- Reports summary

**User:** Keep going until done.

**Claude (later):**
- `check_status(...)` → "process seems finished"
- `get_full_diff("../work-opencode")`
- `run_tests("../work-opencode")`
- Reviews → "Looks correct"
- `update_task_status("T-001", "needs_review")`

**User reviews the diff in chat**

**User:** Looks good. Please give me the merge commands.

**Claude outputs:**
```bash
git checkout main
git merge task/opencode-1
...
```

---

This pattern turns Claude from "the coder" into "the engineering manager".
