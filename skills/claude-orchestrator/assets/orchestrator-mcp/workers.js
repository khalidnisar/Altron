/**
 * Worker agent registry — single source of truth for every CLI the
 * orchestrator can dispatch to.
 *
 * Built-ins cover the CLIs verified on this stack. Extend WITHOUT code
 * changes via star.json:
 *
 *   "agents": {
 *     "commands": {
 *       "myagent": {
 *         "cmd": "my-agent",
 *         "args": ["--headless", "{PROMPT}"],
 *         "env": { "OPENAI_BASE_URL": "https://...", "OPENAI_API_KEY": "${SOME_KEY}" }
 *       }
 *     }
 *   }
 *
 * "{PROMPT}" in any arg is replaced with the task prompt.
 * "${VAR}" in any env value is resolved from the parent process environment at
 * dispatch time — key VALUES never live in config files.
 *
 * MODEL FALLBACK: a def may carry "models": [...] and use "{MODEL}" in args.
 * Entries are either a model-id string or { "model": "...", "env": {...} }
 * (per-model env override — e.g. a different base URL + key for a fallback
 * provider). When a dispatched worker exits with a quota / rate-limit error,
 * the orchestrator automatically re-dispatches with the next model in the
 * chain. Put free models at the end so limits degrade to free, not to failure.
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

// Model chain entries: "model-id" or { model, env }. Invalid entries dropped.
function normalizeModels(models) {
  if (!Array.isArray(models)) return [];
  return models
    .map((m) => {
      if (typeof m === 'string' && m.trim()) return { model: m.trim(), env: undefined };
      if (m && typeof m === 'object' && typeof m.model === 'string') return { model: m.model, env: m.env };
      return null;
    })
    .filter(Boolean);
}

// "${VAR}" values are looked up in process.env at call time; literal values
// pass through. Missing env vars resolve to "" (the worker will surface the
// auth error itself, which is more debuggable than a spawn crash).
function resolveEnvRefs(envDef) {
  if (!envDef || typeof envDef !== 'object') return undefined;
  const out = {};
  for (const [k, v] of Object.entries(envDef)) {
    const m = String(v).match(/^\$\{([A-Z0-9_]+)\}$/i);
    out[k] = m ? (process.env[m[1]] || '') : String(v);
  }
  return out;
}

function loadCustomWorkers() {
  try {
    if (!fs.existsSync(STAR_CONFIG)) return {};
    const cfg = JSON.parse(fs.readFileSync(STAR_CONFIG, 'utf8'));
    const commands = (cfg.agents && cfg.agents.commands) || {};
    const custom = {};
    for (const [name, def] of Object.entries(commands)) {
      if (name.startsWith('_')) continue; // _comment / _example entries are docs, not workers
      if (!def || typeof def.cmd !== 'string' || !Array.isArray(def.args)) continue;
      const chain = normalizeModels(def.models);
      custom[name] = (prompt, modelIndex = 0) => {
        const entry = chain.length ? chain[Math.min(modelIndex, chain.length - 1)] : null;
        return {
          cmd: def.cmd,
          args: def.args.map((a) =>
            String(a)
              .replaceAll('{PROMPT}', prompt)
              .replaceAll('{MODEL}', entry ? entry.model : '')
          ),
          env: { ...(resolveEnvRefs(def.env) || {}), ...(entry ? resolveEnvRefs(entry.env) || {} : {}) },
          model: entry ? entry.model : undefined,
          modelIndex,
          modelCount: chain.length || 1,
        };
      };
      custom[name].modelCount = chain.length || 1;
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

export function buildCommand(toolName, prompt, modelIndex = 0) {
  const workers = getWorkers();
  const builder = workers[toolName];
  if (!builder) {
    throw new Error(`Unknown worker: ${toolName}. Available: ${Object.keys(workers).join(', ')}`);
  }
  return builder(prompt, modelIndex);
}

// Number of models in a worker's fallback chain (1 when no chain configured).
export function modelCount(toolName) {
  const builder = getWorkers()[toolName];
  return (builder && builder.modelCount) || 1;
}

// POSIX single-quote escaping — for sending a full command line into tmux.
function shq(str) {
  return `'${String(str).replace(/'/g, `'\\''`)}'`;
}

/**
 * Windows: npm installs CLIs as .cmd shims, which require cmd.exe — and
 * cmd.exe mangles embedded quotes and treats newlines as command separators.
 * Resolve the shim's real target (an .exe or a node script) so it can be
 * spawned WITHOUT a shell, with proper argv quoting. Returns null when the
 * command isn't an npm shim (caller falls back to shell execution).
 */
export function resolveExecutable(cmd) {
  if (process.platform !== 'win32') return null;
  for (const dir of (process.env.PATH || '').split(path.delimiter)) {
    if (!dir) continue;
    const shim = path.join(dir, `${cmd}.cmd`);
    try {
      if (!fs.existsSync(shim)) continue;
      const matches = fs.readFileSync(shim, 'utf8').match(/"%dp0%\\([^"]+)"/g);
      if (!matches || !matches.length) return null;
      // Last %dp0% reference is the target (earlier ones probe for local node)
      const rel = matches[matches.length - 1].slice('"%dp0%\\'.length, -1);
      const target = path.join(dir, rel);
      if (!fs.existsSync(target)) return null;
      return target.toLowerCase().endsWith('.exe')
        ? { file: target, prefixArgs: [] }
        : { file: process.execPath, prefixArgs: [target] };
    } catch {
      return null;
    }
  }
  return null;
}

export function buildShellCommand(toolName, prompt) {
  const { cmd, args, env } = buildCommand(toolName, prompt);
  const envPrefix = env && Object.keys(env).length
    ? 'env ' + Object.entries(env).map(([k, v]) => `${k}=${shq(v)}`).join(' ') + ' '
    : '';
  return envPrefix + [cmd, ...args.map(shq)].join(' ');
}
