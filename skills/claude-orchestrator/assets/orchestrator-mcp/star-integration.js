/**
 * STAR Integration Layer for Altron Hybrid Orchestrator
 * 
 * Provides STAR-inspired features portably:
 * - Workspaces (rich metadata sidebar)
 * - Notifications (rings + panel)
 * - Scriptable browser (Playwright)
 * - Hooks + notify
 * - Custom commands
 */

import fs from 'fs-extra';
import path from 'path';
import yaml from 'js-yaml';
import { execSync } from 'child_process';

// Project root = cwd (Claude Code launches MCP servers at the project root).
const REPO_ROOT = process.env.ORCHESTRATOR_ROOT
  ? path.resolve(process.env.ORCHESTRATOR_ROOT)
  : process.cwd();

const WORKSPACES_FILE = path.join(REPO_ROOT, 'workspaces.yaml');
const NOTIFS_FILE = path.join(REPO_ROOT, '.star-notifications.json');
const STAR_CONFIG = path.join(REPO_ROOT, 'star.json');

// --- Workspaces (star sidebar equivalent) ---
export function getWorkspaces() {
  try {
    if (fs.existsSync(WORKSPACES_FILE)) {
      const doc = yaml.load(fs.readFileSync(WORKSPACES_FILE, 'utf8')) || {};
      return {
        workspaces: Array.isArray(doc.workspaces) ? doc.workspaces : [],
        metadata: doc.metadata || {},
      };
    }
  } catch {}
  return { workspaces: [], metadata: {} };
}

export function updateWorkspace(workspaceId, updates) {
  // Line-based update (preserves comments). Workspace id matched exactly.
  if (!fs.existsSync(WORKSPACES_FILE)) return false;
  let content = fs.readFileSync(WORKSPACES_FILE, 'utf8');
  const lines = content.split('\n');
  let inWs = false;
  let updated = false;
  const newLines = lines.map(line => {
    const t = line.trim();
    if (t.startsWith('- id:')) {
      const m = t.match(/id:\s*(\S+)/);
      inWs = !!m && m[1] === workspaceId;
    }
    if (inWs) {
      for (const [k, v] of Object.entries(updates)) {
        if (t.startsWith(`${k}:`)) {
          const indent = line.match(/^(\s*)/)[1] || '  ';
          updated = true;
          if (Array.isArray(v)) {
            return `${indent}${k}: [${v.join(', ')}]`;
          }
          return `${indent}${k}: ${JSON.stringify(v)}`;
        }
      }
    }
    return line;
  });
  if (updated) fs.writeFileSync(WORKSPACES_FILE, newLines.join('\n'));
  return updated;
}

// Find the workspace belonging to a task and update it.
export function updateWorkspaceByTask(taskId, updates) {
  const ws = getWorkspaces().workspaces.find(w => w.task_id === taskId);
  if (!ws) return false;
  return updateWorkspace(ws.id, updates);
}

// --- Notifications ---
export function sendNotification({ taskId, message, type = 'info', workdir = null }) {
  const data = loadNotifs();
  const notif = {
    id: `n-${Date.now()}`,
    timestamp: new Date().toISOString(),
    taskId,
    workdir,
    message,
    type,
    read: false
  };
  data.notifications = data.notifications || [];
  data.notifications.unshift(notif);
  if (data.notifications.length > 50) data.notifications = data.notifications.slice(0, 50);
  data.unread = data.notifications.filter(n => !n.read).length;
  fs.writeFileSync(NOTIFS_FILE, JSON.stringify(data, null, 2));
  return notif;
}

function loadNotifs() {
  try { return JSON.parse(fs.readFileSync(NOTIFS_FILE, 'utf8')); } catch { return { notifications: [], unread: 0 }; }
}

export function getNotifications() {
  return loadNotifs();
}

export function markNotificationRead(id) {
  const data = loadNotifs();
  const n = data.notifications.find(x => x.id === id);
  if (n) n.read = true;
  data.unread = data.notifications.filter(x => !x.read).length;
  fs.writeFileSync(NOTIFS_FILE, JSON.stringify(data, null, 2));
  return true;
}

// --- Browser helpers (re-export from star-browser) ---
export async function getBrowserTools() {
  const browserMod = await import('./star-browser.js');
  return browserMod;
}

// --- Custom commands (from star.json) ---
export function getCustomCommands() {
  try {
    if (fs.existsSync(STAR_CONFIG)) {
      const cfg = JSON.parse(fs.readFileSync(STAR_CONFIG, 'utf8'));
      return cfg.custom_commands || {};
    }
  } catch {}
  return {};
}

export function runCustomCommand(name) {
  const cmds = getCustomCommands();
  const cmd = cmds[name];
  if (!cmd) throw new Error(`Unknown custom command: ${name}`);
  const output = execSync(cmd, { encoding: 'utf8', cwd: REPO_ROOT });
  return { command: cmd, output };
}
