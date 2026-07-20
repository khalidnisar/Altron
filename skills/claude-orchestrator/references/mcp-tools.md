# MCP Tool Reference — claude-orchestrator (v2.2)

All tools are exposed by `assets/orchestrator-mcp/index.js` (server name
`claude-orchestrator`). The server resolves project files (`tasks.yaml`,
`star.json`, `workspaces.yaml`) from its working directory; override with the
`ORCHESTRATOR_ROOT` environment variable.

## Task board

| Tool | Parameters | Purpose |
|------|-----------|---------|
| `list_tasks` | — | Read the whole tasks.yaml board. Call at every session start. |
| `get_task` | `task_id` | One task by ID. |
| `update_task_status` | `task_id`, `status`, `notes?` | Statuses: `pending`, `running`, `needs_review`, `done`, `failed`, `conflict`, `escalated`. |

## Hybrid model

| Tool | Parameters | Purpose |
|------|-----------|---------|
| `plan_task_split` | `task_id`, `claude_responsibility`, `agent_responsibility`, `difficulty?` | Persist the 30/70 split onto the task (fields + notes). Call before any dispatch/claim. |
| `claim_task_for_claude` | `task_id`, `responsibility?` | Claude takes direct ownership (sets `owner: claude`, `status: running`). |
| `increment_agent_retry` | `task_id` | Bump `retry_count`; auto-escalates at `max_retries_per_agent` (default 3). |
| `escalate_task` | `task_id`, `reason?` | Force escalation: `status: escalated`, `owner: claude`. |

## Dispatch & monitoring

| Tool | Parameters | Purpose |
|------|-----------|---------|
| `dispatch_task` | `tool` (`opencode`\|`cursor`\|`hermes`\|`echo`), `prompt`, `workdir`, `task_id?`, `use_tmux?` | Launch a headless worker in its worktree. Logs to `.agent-log.txt`, PID to `.agent-pid`. `use_tmux: true` runs it in a tmux window instead. |
| `check_status` | `workdir` | Log tail (50 lines) + `git diff --stat` + PID liveness. |
| `get_full_diff` | `workdir` | Full unified diff of the worker's changes. |
| `run_tests` | `workdir` | Auto-detects gradlew / npm test / cargo / pytest; returns `passed` + output. |
| `create_worktree` | `branch_name`, `worktree_path` | `git worktree add <path> -b <branch>`. |

## STAR-style workspace & notifications

| Tool | Parameters | Purpose |
|------|-----------|---------|
| `list_workspaces` | — | Sidebar view from `workspaces.yaml` (branch, ports, notifications, owner). |
| `send_notification` | `task_id`, `message`, `type` (`waiting`\|`done`\|`error`\|`info`\|`stuck`), `workdir?` | Append to `.star-notifications.json` (capped at 50) and update the matching workspace. |
| `get_notifications` | — | Full notification panel with unread count. |
| `run_custom_command` | `name` | Run a command from `star.json` → `custom_commands`. |

## Browser (optional — requires `playwright`)

| Tool | Parameters | Purpose |
|------|-----------|---------|
| `launch_browser` | `headless?` | Start a Playwright Chromium instance. |
| `navigate_browser` | `url` | Go to URL (dev servers, docs). |
| `browser_click` | `selector` | Click an element. |
| `get_browser_state` | — | Current URL + title. |

## tmux (optional — Linux/macOS with tmux installed)

| Tool | Parameters | Purpose |
|------|-----------|---------|
| `tmux_get_status` | — | tmux availability + sessions/windows. |
| `tmux_list_workspaces` | — | tmux windows merged with workspaces.yaml. |
| `tmux_create_workspace` | `task_id`, `worker`, `workdir`, `session?` | Dedicated window per task. |
| `tmux_launch_agent` | `task_id`, `worker`, `prompt`, `workdir`, `session?` | Run the agent inside a tmux pane. |
| `tmux_send` | `task_id`, `worker`, `command`, `session?` | Send keystrokes to a window. |
| `tmux_capture` | `task_id`, `worker`, `lines?`, `session?` | Read terminal output. |
| `tmux_split` | `task_id`, `worker`, `direction?`, `session?` | Split a window. |
| `tmux_focus` | `task_id`, `worker`, `session?` | Switch to a window. |

## tasks.yaml schema

```yaml
tasks:
  - id: T-001
    title: "Short imperative description"
    assigned_to: opencode          # worker name from dispatch tools
    workdir: ../work-opencode      # relative to project root
    branch: task/opencode-1
    status: pending                # pending|running|needs_review|done|failed|conflict|escalated
    priority: high                 # high|medium|low
    difficulty: medium             # easy|medium|hard
    retry_count: 0                 # managed by increment_agent_retry
    escalated: false               # true once Claude takes over
    owner: "opencode"              # opencode|cursor|hermes|claude
    claude_responsibility: ""      # set by plan_task_split
    agent_responsibility: ""       # set by plan_task_split
    notes: ""

tasks_metadata:
  last_updated: "YYYY-MM-DD"
  active_agents: [opencode, cursor, hermes]
  max_concurrent: 3
  max_retries_per_agent: 3
  main_branch: "main"
```

## Adding a new worker CLI

Edit `TOOL_CMDS` in `assets/orchestrator-mcp/index.js`:

```js
const TOOL_CMDS = {
  mynewagent: (prompt, cwd) => ({ cmd: "my-agent", args: ["--headless", prompt] }),
};
```

Also extend the `tool`/`worker` enums in the `dispatch_task` and
`tmux_launch_agent` tool schemas.
