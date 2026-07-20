/**
 * Glue layer between the main MCP server and tmux-manager
 * Also merges tmux data with the existing workspaces.yaml + notifications.
 */

import tmuxManager from './tmux-manager.js';
import fs from 'fs-extra';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const REPO_ROOT = path.resolve(__dirname, '..');

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

function parseSimpleWorkspaces(yaml) {
  const workspaces = [];
  const lines = yaml.split('\n');
  let current = null;
  for (const line of lines) {
    const t = line.trim();
    if (t.startsWith('- id:')) {
      if (current) workspaces.push(current);
      current = {};
      const m = t.match(/id:\s*(\S+)/);
      if (m) current.id = m[1];
    } else if (current) {
      const m = t.match(/^(\w+):\s*(.+)$/);
      if (m) current[m[1]] = m[2].replace(/^["']|["']$/g, '');
    }
  }
  if (current) workspaces.push(current);
  return { workspaces, metadata: {} };
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