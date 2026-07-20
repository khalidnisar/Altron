/**
 * Glue layer between the main MCP server and tmux-manager
 * Also merges tmux data with the existing workspaces.yaml + notifications.
 */

import tmuxManager from './tmux-manager.js';
import fs from 'fs-extra';
import path from 'path';
import yaml from 'js-yaml';

// Project root = cwd (Claude Code launches MCP servers at the project root).
const REPO_ROOT = process.env.ORCHESTRATOR_ROOT
  ? path.resolve(process.env.ORCHESTRATOR_ROOT)
  : process.cwd();

const WORKSPACES_FILE = path.join(REPO_ROOT, 'workspaces.yaml');

export function getEnhancedWorkspaces() {
  // Start with the STAR-style workspaces.yaml
  let base = { workspaces: [], metadata: {} };
  try {
    if (fs.existsSync(WORKSPACES_FILE)) {
      const content = fs.readFileSync(WORKSPACES_FILE, 'utf8');
      // reuse the parser from star-integration if possible, else simple
      base = parseSimpleWorkspaces(content);
    }
  } catch {}

  // Merge with live tmux data
  const tmuxData = tmuxManager.listTmuxWorkspaces();
  if (tmuxData.available && tmuxData.workspaces.length > 0) {
    base.tmux = {
      available: true,
      session: tmuxData.session,
      windows: tmuxData.workspaces,
    };

    // Enrich each workspace with tmux info if we can match
    base.workspaces = base.workspaces.map(ws => {
      const match = tmuxData.workspaces.find(t =>
        t.task_id === ws.task_id || t.name.includes(ws.task_id || '')
      );
      if (match) {
        return {
          ...ws,
          tmux: {
            window: match.name,
            window_id: match.window_id,
            title: match.title,
            workdir: match.workdir,
          }
        };
      }
      return ws;
    });
  } else {
    base.tmux = { available: false, reason: 'tmux not installed or no active session' };
  }

  return base;
}

function parseSimpleWorkspaces(content) {
  const doc = yaml.load(content) || {};
  return {
    workspaces: Array.isArray(doc.workspaces) ? doc.workspaces : [],
    metadata: doc.metadata || {},
  };
}

export function launchInTmux(taskId, worker, prompt, workdir) {
  if (!tmuxManager.tmuxAvailable()) {
    return { success: false, error: 'tmux not available' };
  }
  return tmuxManager.launchAgentInTmux(taskId, worker, prompt, workdir);
}

export default {
  getEnhancedWorkspaces,
  launchInTmux,
  ...tmuxManager,
};