# STAR Deep Tmux Emulation in Altron Orchestrator

## What "Deep Emulation" Means

We implemented **STAR-style workspace management** using real `tmux` as the underlying terminal multiplexer.

This gives Claude (and you) the closest experience to native star without needing the macOS GUI app:

- Dedicated tmux **windows** (like star tabs/surfaces) per agent workspace
- **Splits** (horizontal/vertical) inside workspaces
- **Capture** terminal output directly
- **Send** commands / keystrokes to specific panes
- **Focus** any workspace instantly
- Rich metadata visible via `tmux_list_workspaces`
- Full integration with the existing hybrid orchestrator + notifications

## New MCP Tools (Deep Tmux)

| Tool                    | star Equivalent                  | What it does |
|-------------------------|----------------------------------|--------------|
| `tmux_get_status`       | Session list                     | Is tmux running? What windows exist? |
| `tmux_list_workspaces`  | Sidebar                          | Full merged view (workspaces.yaml + live tmux) |
| `tmux_create_workspace` | New tab / surface                | Creates a named tmux window for a task |
| `tmux_launch_agent`     | Launch agent in pane             | Spawns agent **inside** the tmux window |
| `tmux_send`             | Type into terminal               | Send arbitrary commands to a workspace |
| `tmux_capture`          | Read terminal output             | Grab last N lines (like `check_status` but richer) |
| `tmux_split`            | Split pane                       | Horizontal or vertical split |
| `tmux_focus`            | Click tab                        | Bring a workspace to foreground |

Also:
- `dispatch_task(..., use_tmux: true)` — launches directly in tmux

## Recommended Workflow (with tmux)

```text
1. tmux_get_status()
2. tmux_list_workspaces()           # best "sidebar" view
3. plan_task_split(...)
4. dispatch_task(..., use_tmux: true)
5. tmux_capture(...)                # monitor progress
6. tmux_focus(...) when you want to "look" at a workspace
7. tmux_split(...) if you need side-by-side (e.g. tests + logs)
```

## Fallback Behavior

If `tmux` is not installed on the host:
- All tmux tools gracefully report `available: false`
- `dispatch_task` falls back to normal detached process mode
- The rest of the orchestrator (hybrid + notifications + browser) continues to work

## Starting the Full star-like Experience

```bash
# From Altron root
./scripts/star/tmux/start-orchestrator-tmux.sh
tmux attach -t altron-orchestrator
```

Inside the tmux session you get:
- Main orchestrator pane
- Live status watcher
- Notification tail

Then let Claude use the `tmux_*` tools to create real workspaces.

## Files Added for Deep Tmux

```
scripts/star/tmux/
  create-workspace.sh
  start-orchestrator-tmux.sh

orchestrator-mcp/
  tmux-manager.js          # core tmux logic
  tmux-integration.js      # glue + workspace merging

# Tools added to orchestrator-mcp/index.js
```

This is the deepest portable emulation of star's terminal multiplexing we can achieve in a headless/Linux environment.

**Version**: 2.1.0 (Hybrid + star + Deep Tmux)
