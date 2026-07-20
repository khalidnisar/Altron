#!/usr/bin/env node
/**
 * star-notify (STAR style)
 * 
 * Sends notifications that the orchestrator can pick up.
 * Used by agent hooks, custom scripts, or directly by Claude.
 * 
 * Usage:
 *   node star-notify.js --task T-001 --message "Waiting for input on auth flow" --type waiting
 *   node star-notify.js --task T-007 --message "Deep link implemented" --type done
 */

import fs from 'fs-extra';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const REPO_ROOT = path.resolve(__dirname, '..');
const NOTIFICATIONS_FILE = path.join(REPO_ROOT, '.star-notifications.json');
const WORKSPACES_FILE = path.join(REPO_ROOT, 'workspaces.yaml');

function loadNotifications() {
  try {
    if (fs.existsSync(NOTIFICATIONS_FILE)) {
      return JSON.parse(fs.readFileSync(NOTIFICATIONS_FILE, 'utf8'));
    }
  } catch {}
  return { notifications: [], unread: 0 };
}

function saveNotifications(data) {
  fs.writeFileSync(NOTIFICATIONS_FILE, JSON.stringify(data, null, 2));
}

function addNotification({ taskId, message, type = 'info', workdir = null }) {
  const data = loadNotifications();
  const notif = {
    id: `n-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    timestamp: new Date().toISOString(),
    taskId,
    workdir,
    message,
    type,                    // waiting | done | error | info | stuck
    read: false
  };
  
  data.notifications.unshift(notif);
  if (data.notifications.length > 50) data.notifications = data.notifications.slice(0, 50);
  
  data.unread = data.notifications.filter(n => !n.read).length;
  
  saveNotifications(data);
  
  // Also append to the agent's log if workdir exists
  if (workdir) {
    try {
      const logPath = path.join(path.resolve(REPO_ROOT, workdir), '.agent-log.txt');
      if (fs.existsSync(logPath)) {
        fs.appendFileSync(logPath, `\n[star-notify ${notif.timestamp}] ${type.toUpperCase()}: ${message}\n`);
      }
    } catch {}
  }
  
  return notif;
}

function main() {
  const args = process.argv.slice(2);
  const opts = {};
  
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--task') opts.taskId = args[++i];
    if (args[i] === '--message') opts.message = args[++i];
    if (args[i] === '--type') opts.type = args[++i];
    if (args[i] === '--workdir') opts.workdir = args[++i];
  }
  
  if (!opts.message) {
    console.error('Usage: star-notify --message "text" [--task T-001] [--type waiting|done|error|info] [--workdir ../work-xxx]');
    process.exit(1);
  }
  
  const notif = addNotification(opts);
  console.log(JSON.stringify({ success: true, notification: notif }, null, 2));
}

main();