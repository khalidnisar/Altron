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
import { fileURLToPath } from 'url';
import { execSync } from 'child_process';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const REPO_ROOT = path.resolve(__dirname, '..');

const WORKSPACES_FILE = path.join(REPO_ROOT, 'workspaces.yaml');
const NOTIFS_FILE = path.join(REPO_ROOT, '.star-notifications.json');
const STAR_CONFIG = path.join(REPO_ROOT, 'star.json');

// --- Workspaces (star sidebar equivalent) ---
export function getWorkspaces() {
  try {
    if (fs.existsSync(WORKSPACES_FILE)) {
      // Very lightweight parser
      const content = fs.readFileSync(WORKSPACES_FILE, 'utf8');
      return parseWorkspacesYaml(content);
    }
  } catch {}
  return { workspaces: [], metadata: {} };
}

function parseWorkspacesYaml(yaml) {
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
      if (m) {
        let k = m[1], v = m[2].replace(/^["']|["']$/g, '');
        if (k === 'listening_ports') {
          current[k] = v.split(',').map(x => x.trim()).filter(Boolean);
        } else {
          current[k] = v;
        }
      }
    }
  }
  if (current) workspaces.push(current);
  return { workspaces, metadata: { last_updated: new Date().toISOString() } };
}

export function updateWorkspace(workspaceId, updates) {
  // Simple string-based update (good enough for our use)
  let content = fs.readFileSync(WORKSPACES_FILE, 'utf8');
  const lines = content.split('\n');
  let inWs = false;
  const newLines = lines.map(line => {
    const t = line.trim();
    if (t.startsWith('- id:')) {
      inWs = t.includes(workspaceId);
    }
    if (inWs) {
      for (const [k, v] of Object.entries(updates)) {
        if (t.startsWith(`${k}:`)) {
          const indent = line.match(/^(\s*)/)[1] || '  ';
          if (Array.isArray(v)) {
            return `${indent}${k}: ${v.join(', ')}`;
          }
          return `${indent}${k}: ${v}`;
        }
      }
    }
    return line;
  });
  fs.writeFileSync(WORKSPACES_FILE, newLines.join('\n'));
  return true;
}

// --- Notifications ---
export function sendNotification({ taskId, message, type = 'info', workdir = null }) {
  const { addNotification } = require('./star-notify.js'); // reuse
  // Since it's ESM, we do dynamic import in real use. For simplicity here:
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
