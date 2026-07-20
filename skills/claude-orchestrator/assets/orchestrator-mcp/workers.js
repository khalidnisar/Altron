/**
 * Worker agent registry — single source of truth for every CLI the
 * orchestrator can dispatch to.
 *
 * Built-ins cover the CLIs verified on this stack. Extend WITHOUT code
 * changes via star.json:
 *
 *   "agents": {
 *     "commands": {
 *       "myagent": { "cmd": "my-agent", "args": ["--headless", "{PROMPT}"] }
 *     }
 *   }
 *
 * "{PROMPT}" in any arg is replaced with the task prompt.
 */

import fs from 'fs-extra';
import path from 'path';

const REPO_ROOT = process.env.ORCHESTRATOR_ROOT
  ? path.resolve(process.env.ORCHESTRATOR_ROOT)
  : process.cwd();
const STAR_CONFIG = path.join(REPO_ROOT, 'star.json');

// Each builder: (prompt) => { cmd, args } — headless, non-interactive, exits when done.
const BUILTIN_WORKERS = {
  // opencode (sst) — `opencode run <message>`
  opencode: (prompt) => ({ cmd: 'opencode', args: ['run', prompt] }),
  // OpenAI Codex CLI — non-interactive exec, writes confined to the worktree
  codex: (prompt) => ({ cmd: 'codex', args: ['exec', '-s', 'workspace-write', '--skip-git-repo-check', prompt] }),
  // autoclaw — headless (-n) with auto-confirmed tool use (-y)
  autoclaw: (prompt) => ({ cmd: 'autoclaw', args: ['-n', '-y', 'chat', prompt] }),
  // ZCode Agent — no official npm CLI as of 2026-07; expects `zcode` on PATH.
  // Adjust via star.json agents.commands.zcode if your install differs.
  zcode: (prompt) => ({ cmd: 'zcode', args: ['--headless', prompt] }),
  // Cursor CLI
  cursor: (prompt) => ({ cmd: 'cursor-agent', args: ['-p', prompt, '--output-format', 'json'] }),
  // hermes harness (or swap for aider via star.json)
  hermes: (prompt) => ({ cmd: 'hermes', args: ['--headless', '--prompt', prompt] }),
  // Dry-run tool for testing the loop without a real agent
  echo: (prompt) => ({ cmd: 'echo', args: [`[ECHO AGENT] Would run: ${prompt}`] }),
};

function loadCustomWorkers() {
  try {
    if (!fs.existsSync(STAR_CONFIG)) return {};
    const cfg = JSON.parse(fs.readFileSync(STAR_CONFIG, 'utf8'));
    const commands = (cfg.agents && cfg.agents.commands) || {};
    const custom = {};
    for (const [name, def] of Object.entries(commands)) {
      if (name.startsWith('_')) continue; // _comment / _example entries are docs, not workers
      if (!def || typeof def.cmd !== 'string' || !Array.isArray(def.args)) continue;
      custom[name] = (prompt) => ({
        cmd: def.cmd,
        args: def.args.map((a) => String(a).replaceAll('{PROMPT}', prompt)),
      });
    }
    return custom;
  } catch {
    return {};
  }
}

// star.json entries override built-ins of the same name.
export function getWorkers() {
  return { ...BUILTIN_WORKERS, ...loadCustomWorkers() };
}

export function listWorkerNames() {
  return Object.keys(getWorkers());
}

export function buildCommand(toolName, prompt) {
  const workers = getWorkers();
  const builder = workers[toolName];
  if (!builder) {
    throw new Error(`Unknown worker: ${toolName}. Available: ${Object.keys(workers).join(', ')}`);
  }
  return builder(prompt);
}

// POSIX single-quote escaping — for sending a full command line into tmux.
function shq(str) {
  return `'${String(str).replace(/'/g, `'\\''`)}'`;
}

export function buildShellCommand(toolName, prompt) {
  const { cmd, args } = buildCommand(toolName, prompt);
  return [cmd, ...args.map(shq)].join(' ');
}
