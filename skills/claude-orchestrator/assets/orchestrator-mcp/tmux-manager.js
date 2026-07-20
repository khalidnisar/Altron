/**
 * STAR-style Tmux Workspace Manager for Altron Hybrid Orchestrator
 *
 * Provides deep tmux-based multiplexing:
 * - One tmux session = orchestrator "project"
 * - One window per agent workspace (like star surfaces)
 * - Splits, focus, capture, send commands
 * - Automatic pane titles with task metadata
 *
 * When tmux is not available, falls back to simple process tracking.
 */

import { execSync, execFileSync } from 'child_process';
import fs from 'fs-extra';
import path from 'path';

// Project root = cwd (Claude Code launches MCP servers at the project root).
const REPO_ROOT = process.env.ORCHESTRATOR_ROOT
  ? path.resolve(process.env.ORCHESTRATOR_ROOT)
  : process.cwd();

const TMUX_SESSION = process.env.ORCHESTRATOR_TMUX_SESSION || process.env.ALTRON_TMUX_SESSION || 'claude-orchestrator';
const TMUX_BIN = 'tmux';

let tmuxChecked = null;
function tmuxAvailable() {
  if (tmuxChecked !== null) return tmuxChecked;
  try {
    execSync(`${TMUX_BIN} -V`, { stdio: 'ignore' });
    tmuxChecked = true;
  } catch {
    tmuxChecked = false;
  }
  return tmuxChecked;
}

function runTmux(args, options = {}) {
  if (!tmuxAvailable()) {
    throw new Error('tmux is not installed on this system');
  }
  // execFileSync: args passed as an array — no shell re-parsing, so titles,
  // banners, and prompts containing spaces or quotes survive intact.
  return execFileSync(TMUX_BIN, args, {
    encoding: 'utf8',
    ...options,
  }).trim();
}

// POSIX single-quote escaping for commands sent into tmux panes.
function shq(str) {
  return `'${String(str).replace(/'/g, `'\\''`)}'`;
}

function safeSessionName(name) {
  return name.replace(/[^a-zA-Z0-9_-]/g, '_').slice(0, 32);
}

/**
 * Ensure the main orchestrator tmux session exists
 */
export function ensureSession(session = TMUX_SESSION) {
  if (!tmuxAvailable()) return { available: false };

  const s = safeSessionName(session);
  try {
    runTmux(['has-session', '-t', s]);
    return { available: true, session: s, created: false };
  } catch {
    runTmux(['new-session', '-d', '-s', s, '-n', 'orchestrator', '-c', REPO_ROOT]);
    runTmux(['set-option', '-t', s, 'status-left', '[Altron Orchestrator] ']);
    runTmux(['set-option', '-t', s, 'status-right', '#{?pane_in_mode,[COPY],} #{?window_zoomed_flag,[ZOOM],} ']);
    return { available: true, session: s, created: true };
  }
}

/**
 * Create a new workspace window for an agent task
 */
export function createWorkspace(taskId, worker, workdir, session = TMUX_SESSION) {
  const s = safeSessionName(session);
  ensureSession(s);

  const windowName = `${taskId}-${worker}`.replace(/[^a-zA-Z0-9_-]/g, '_').slice(0, 20);
  const fullWorkdir = path.resolve(REPO_ROOT, workdir);

  // Create window
  let windowId;
  try {
    windowId = runTmux([
      'new-window',
      '-t', `${s}:`,
      '-n', windowName,
      '-c', fullWorkdir,
      '-P', '-F', '#{window_id}'
    ]);
  } catch (e) {
    // Window may already exist — reuse it
    windowId = runTmux(['list-windows', '-t', s, '-F', '#{window_id}:#{window_name}'])
      .split('\n')
      .find(line => line.includes(windowName))
      ?.split(':')[0];
  }

  // Set pane title with rich metadata
  const title = `【${taskId}】 ${worker} | ${workdir}`;
  runTmux(['select-window', '-t', `${s}:${windowName}`]);
  runTmux(['select-pane', '-t', `${s}:${windowName}`, '-T', title]);

  // Send welcome banner
  const banner = [
    `echo '══════════════════════════════════════'`,
    `echo '  Altron star Workspace'`,
    `echo '  Task: ${taskId}'`,
    `echo '  Agent: ${worker}'`,
    `echo '  Dir : ${fullWorkdir}'`,
    `echo '  Branch: $(git branch --show-current 2>/dev/null || echo "unknown")'`,
    `echo '══════════════════════════════════════'`,
    `echo ''`,
  ].join(' && ');

  runTmux(['send-keys', '-t', `${s}:${windowName}`, banner, 'C-m']);

  return {
    session: s,
    window: windowName,
    window_id: windowId,
    workdir: fullWorkdir,
    title,
  };
}

/**
 * Send a command / prompt to a specific workspace window
 */
export function sendToWorkspace(taskId, worker, command, session = TMUX_SESSION) {
  const s = safeSessionName(session);
  const windowName = `${taskId}-${worker}`.replace(/[^a-zA-Z0-9_-]/g, '_').slice(0, 20);

  try {
    runTmux(['send-keys', '-t', `${s}:${windowName}`, command, 'C-m']);
    return { success: true, sent_to: `${s}:${windowName}` };
  } catch (e) {
    return { success: false, error: e.message };
  }
}

/**
 * Capture output from a workspace pane (great for logs)
 */
export function captureWorkspace(taskId, worker, lines = 100, session = TMUX_SESSION) {
  const s = safeSessionName(session);
  const windowName = `${taskId}-${worker}`.replace(/[^a-zA-Z0-9_-]/g, '_').slice(0, 20);

  try {
    const output = runTmux([
      'capture-pane',
      '-t', `${s}:${windowName}`,
      '-p', '-S', `-${lines}`
    ]);
    return { success: true, output, lines: output.split('\n').length };
  } catch (e) {
    return { success: false, error: e.message };
  }
}

/**
 * Split current workspace horizontally or vertically
 */
export function splitWorkspace(taskId, worker, direction = 'horizontal', session = TMUX_SESSION) {
  const s = safeSessionName(session);
  const windowName = `${taskId}-${worker}`.replace(/[^a-zA-Z0-9_-]/g, '_').slice(0, 20);
  const flag = direction === 'vertical' ? '-v' : '-h';

  try {
    const paneId = runTmux([
      'split-window',
      '-t', `${s}:${windowName}`,
      flag,
      '-c', path.resolve(REPO_ROOT, `../work-${worker}`),
      '-P', '-F', '#{pane_id}'
    ]);
    return { success: true, pane_id: paneId };
  } catch (e) {
    return { success: false, error: e.message };
  }
}

/**
 * List all active workspaces (STAR-style sidebar data)
 */
export function listTmuxWorkspaces(session = TMUX_SESSION) {
  if (!tmuxAvailable()) {
    return { available: false, workspaces: [] };
  }

  const s = safeSessionName(session);
  try {
    ensureSession(s);
    const raw = runTmux([
      'list-windows',
      '-t', s,
      '-F', '#{window_id}:#{window_name}:#{pane_title}:#{pane_current_path}'
    ]);

    const workspaces = raw.split('\n').filter(Boolean).map(line => {
      const [wid, name, title, path] = line.split(':');
      const match = name.match(/^(T-\d+)-(.+)$/);
      return {
        window_id: wid,
        name,
        task_id: match ? match[1] : null,
        worker: match ? match[2] : name,
        title: title || '',
        workdir: path || '',
        session: s,
      };
    });

    return { available: true, session: s, workspaces };
  } catch (e) {
    return { available: false, error: e.message, workspaces: [] };
  }
}

/**
 * Focus / switch to a workspace
 */
export function focusWorkspace(taskId, worker, session = TMUX_SESSION) {
  const s = safeSessionName(session);
  const windowName = `${taskId}-${worker}`.replace(/[^a-zA-Z0-9_-]/g, '_').slice(0, 20);

  try {
    runTmux(['select-window', '-t', `${s}:${windowName}`]);
    return { success: true, focused: `${s}:${windowName}` };
  } catch (e) {
    return { success: false, error: e.message };
  }
}

/**
 * Kill a workspace window
 */
export function killWorkspace(taskId, worker, session = TMUX_SESSION) {
  const s = safeSessionName(session);
  const windowName = `${taskId}-${worker}`.replace(/[^a-zA-Z0-9_-]/g, '_').slice(0, 20);

  try {
    runTmux(['kill-window', '-t', `${s}:${windowName}`]);
    return { success: true };
  } catch (e) {
    return { success: false, error: e.message };
  }
}

/**
 * Get tmux status (for Claude to display)
 */
export function getTmuxStatus(session = TMUX_SESSION) {
  if (!tmuxAvailable()) {
    return { available: false, message: 'tmux not installed' };
  }

  const s = safeSessionName(session);
  try {
    ensureSession(s);
    const windows = runTmux(['list-windows', '-t', s, '-F', '#{window_name}']);
    const sessions = runTmux(['list-sessions', '-F', '#{session_name}']);
    return {
      available: true,
      session: s,
      windows: windows.split('\n'),
      all_sessions: sessions.split('\n'),
    };
  } catch (e) {
    return { available: false, error: e.message };
  }
}

/**
 * Launch an agent inside a tmux pane (deep integration)
 */
export function launchAgentInTmux(taskId, worker, prompt, workdir, session = TMUX_SESSION) {
  const ws = createWorkspace(taskId, worker, workdir, session);

  // Build the actual command the agent would run (prompt safely quoted)
  let agentCmd = '';
  if (worker === 'opencode') agentCmd = `opencode run ${shq(prompt)}`;
  else if (worker === 'cursor') agentCmd = `cursor-agent -p ${shq(prompt)} --output-format json`;
  else if (worker === 'hermes') agentCmd = `hermes --headless --prompt ${shq(prompt)}`;
  else agentCmd = `echo ${shq(`[AGENT] ${worker} would run: ${prompt}`)}`;

  // Send the command into the pane
  sendToWorkspace(taskId, worker, agentCmd, session);

  // Also write to the .agent-log.txt for the existing orchestrator
  const logPath = path.join(path.resolve(REPO_ROOT, workdir), '.agent-log.txt');
  fs.appendFileSync(logPath, `\n[tmux] Launched inside tmux window: ${ws.window}\nCommand: ${agentCmd}\n`);

  return {
    ...ws,
    command_sent: agentCmd,
    tmux_mode: true,
  };
}

export default {
  tmuxAvailable,
  ensureSession,
  createWorkspace,
  sendToWorkspace,
  captureWorkspace,
  splitWorkspace,
  listTmuxWorkspaces,
  focusWorkspace,
  killWorkspace,
  getTmuxStatus,
  launchAgentInTmux,
};