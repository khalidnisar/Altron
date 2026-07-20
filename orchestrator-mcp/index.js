#!/usr/bin/env node
/**
 * Altron Hybrid Orchestrator MCP Server (v2)
 * 
 * HYBRID MODEL:
 * - Claude plans the work first.
 * - Claude distributes LONG but EASY tasks to sub-agents.
 * - Claude does the difficult / complex parts itself (~30-40%).
 * - Sub-agents work on ONE task at a time.
 * - If agent fails 3 times or gets stuck → Claude ESCALATES and finishes the task itself.
 *
 * Pattern: Hybrid Orchestrator (Claude + Workers)
 *
 * Tools:
 *   - list_tasks, get_task
 *   - plan_task_split
 *   - dispatch_task
 *   - check_status
 *   - get_full_diff, run_tests
 *   - update_task_status
 *   - escalate_task
 *   - claim_task_for_claude
 *   - create_worktree
 */

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { spawn, execSync } from "child_process";
import fs from "fs-extra";
import path from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// ============================================================
// CONFIGURATION - Customize for your environment
// ============================================================

const REPO_ROOT = path.resolve(__dirname, ".."); // Altron root
const TASKS_FILE = path.join(REPO_ROOT, "tasks.yaml");
const WORKTREES_BASE = "/home/user"; // where work-* dirs live

// Map of tool names → CLI command builder
// Each must be headless / non-interactive
const TOOL_CMDS = {
  opencode: (prompt, cwd) => ({
    cmd: "opencode",
    args: ["run", prompt],
    // Adjust if your opencode CLI differs
  }),
  cursor: (prompt, cwd) => ({
    cmd: "cursor-agent",
    args: ["-p", prompt, "--output-format", "json"],
    // Cursor CLI example from the spec
  }),
  // Add more as confirmed:
  // zcode: (prompt, cwd) => ({ cmd: "zcode", args: ["--headless", prompt] }),
  hermes: (prompt, cwd) => ({
    cmd: "hermes",
    args: ["--headless", "--prompt", prompt],
    // Or replace with actual harness e.g. "aider" + model flag
  }),
  // Generic fallback (useful for testing)
  echo: (prompt, cwd) => ({
    cmd: "echo",
    args: [`[ECHO AGENT] Would run: ${prompt}`],
  }),
};

// Default max runtime for spawned agents (ms)
const DEFAULT_TIMEOUT_MS = 1000 * 60 * 15; // 15 minutes

// ============================================================
// UTILITY FUNCTIONS
// ============================================================

function resolveWorkdir(workdir) {
  if (!workdir) return REPO_ROOT;
  // Support relative paths like "../work-opencode"
  return path.resolve(REPO_ROOT, workdir);
}

function getLogPath(cwd) {
  return path.join(cwd, ".agent-log.txt");
}

function updateTasksFile(updater) {
  let content = fs.readFileSync(TASKS_FILE, "utf8");
  // Simple YAML manipulation. For production use a proper YAML lib.
  // For this skill we keep it readable + simple.
  // We will do string-based updates for now (robust enough for the board).
  const updated = updater(content);
  fs.writeFileSync(TASKS_FILE, updated, "utf8");
  return true;
}

function parseTasksYaml(yamlContent) {
  // Very lightweight parser for our specific format.
  // Returns array of task objects.
  const tasks = [];
  const lines = yamlContent.split("\n");
  let current = null;
  let inTask = false;

  for (let line of lines) {
    const trimmed = line.trim();
    if (trimmed.startsWith("- id:")) {
      if (current) tasks.push(current);
      current = {};
      inTask = true;
      const idMatch = trimmed.match(/id:\s*([^\s]+)/);
      if (idMatch) current.id = idMatch[1];
    } else if (inTask && current) {
      const keyMatch = trimmed.match(/^(\w+):\s*(.+)$/);
      if (keyMatch) {
        let key = keyMatch[1];
        let val = keyMatch[2].replace(/^["']|["']$/g, "");
        // Handle simple lists for active_agents etc at bottom
        if (key === "assigned_to" || key === "status" || key === "workdir" || key === "branch" || key === "title" || key === "priority" || key === "notes") {
          current[key] = val;
        }
      }
    }
  }
  if (current) tasks.push(current);
  return tasks;
}

function getCurrentTasks() {
  const content = fs.readFileSync(TASKS_FILE, "utf8");
  return parseTasksYaml(content);
}

function updateTaskStatusInYaml(taskId, newStatus, extraNotes = "") {
  let content = fs.readFileSync(TASKS_FILE, "utf8");
  const lines = content.split("\n");
  let inTask = false;
  let updated = false;

  const newLines = lines.map((line) => {
    const trimmed = line.trim();
    
    if (trimmed.startsWith("- id:")) {
      const idMatch = trimmed.match(/id:\s*([T0-9-]+)/);
      if (idMatch && idMatch[1] === taskId) {
        inTask = true;
      } else {
        inTask = false;
      }
    }
    
    if (inTask && trimmed.startsWith("status:")) {
      const indent = line.match(/^(\s*)/)[1] || "  ";
      updated = true;
      return `${indent}status: ${newStatus}`;
    }
    
    if (inTask && extraNotes && trimmed.startsWith("notes:")) {
      const indent = line.match(/^(\s*)/)[1] || "  ";
      const oldNote = trimmed.replace("notes:", "").trim();
      const combined = oldNote ? `${oldNote} | ${extraNotes}` : extraNotes;
      return `${indent}notes: "${combined}"`;
    }
    
    return line;
  });

  if (updated) {
    fs.writeFileSync(TASKS_FILE, newLines.join("\n"), "utf8");
  }
  return updated;
}

// Hybrid-specific: update multiple fields (retry_count, escalated, owner, difficulty)
function updateHybridTaskFields(taskId, updates = {}) {
  let content = fs.readFileSync(TASKS_FILE, "utf8");
  const lines = content.split("\n");
  let inTask = false;
  let updated = false;

  const newLines = lines.map((line) => {
    const trimmed = line.trim();
    
    if (trimmed.startsWith("- id:")) {
      const idMatch = trimmed.match(/id:\s*([T0-9-]+)/);
      if (idMatch && idMatch[1] === taskId) {
        inTask = true;
      } else {
        inTask = false;
      }
    }
    
    if (!inTask) return line;

    // Update specific hybrid fields
    if (updates.status && trimmed.startsWith("status:")) {
      const indent = line.match(/^(\s*)/)[1] || "  ";
      updated = true;
      return `${indent}status: ${updates.status}`;
    }
    if (updates.retry_count !== undefined && trimmed.startsWith("retry_count:")) {
      const indent = line.match(/^(\s*)/)[1] || "  ";
      updated = true;
      return `${indent}retry_count: ${updates.retry_count}`;
    }
    if (updates.escalated !== undefined && trimmed.startsWith("escalated:")) {
      const indent = line.match(/^(\s*)/)[1] || "  ";
      updated = true;
      return `${indent}escalated: ${updates.escalated}`;
    }
    if (updates.owner && trimmed.startsWith("owner:")) {
      const indent = line.match(/^(\s*)/)[1] || "  ";
      updated = true;
      return `${indent}owner: "${updates.owner}"`;
    }
    if (updates.notes && trimmed.startsWith("notes:")) {
      const indent = line.match(/^(\s*)/)[1] || "  ";
      const old = trimmed.replace("notes:", "").trim().replace(/^["']|["']$/g, "");
      const combined = old ? `${old} | ${updates.notes}` : updates.notes;
      updated = true;
      return `${indent}notes: "${combined}"`;
    }
    
    return line;
  });

  if (updated) {
    fs.writeFileSync(TASKS_FILE, newLines.join("\n"), "utf8");
  }
  return updated;
}

// ============================================================
// CORE ORCHESTRATOR FUNCTIONS (exposed as MCP tools)
// ============================================================

/**
 * Dispatch a task to a worker agent.
 * Starts the agent in detached mode and logs output.
 */
export function dispatchTask(toolName, prompt, workdir, taskId = null) {
  const cwd = resolveWorkdir(workdir);
  const logPath = getLogPath(cwd);

  if (!fs.existsSync(cwd)) {
    throw new Error(`Workdir does not exist: ${cwd}. Create with git worktree first.`);
  }

  const toolDef = TOOL_CMDS[toolName];
  if (!toolDef) {
    throw new Error(`Unknown tool: ${toolName}. Available: ${Object.keys(TOOL_CMDS).join(", ")}`);
  }

  const { cmd, args } = toolDef(prompt, cwd);

  // Clear previous log for this run
  fs.ensureFileSync(logPath);
  fs.writeFileSync(logPath, `=== DISPATCHED ${new Date().toISOString()} ===\nTool: ${toolName}\nPrompt: ${prompt}\nCWD: ${cwd}\n\n`);

  const out = fs.openSync(logPath, "a");
  const err = fs.openSync(logPath, "a");

  const child = spawn(cmd, args, {
    cwd,
    stdio: ["ignore", out, err],
    detached: true,
    env: { ...process.env },
  });

  child.unref();

  // Write PID for later inspection
  fs.writeFileSync(path.join(cwd, ".agent-pid"), String(child.pid));

  // Update task status if taskId supplied
  if (taskId) {
    try {
      updateTaskStatusInYaml(taskId, "running", `Dispatched to ${toolName} at ${new Date().toISOString()}`);
    } catch (e) {
      console.error("Failed to update task status:", e);
    }
  }

  // === STAR-style: auto notify on dispatch ===
  try {
    const notifMsg = `Dispatched to ${toolName}`;
    // We can call send_notification later via tool, but for now append to log
    fs.appendFileSync(logPath, `\n[star] ${notifMsg}\n`);
  } catch {}

  return {
    success: true,
    pid: child.pid,
    tool: toolName,
    workdir: cwd,
    logPath,
    message: `Agent ${toolName} started (PID ${child.pid}). Use check_status to monitor.`,
  };
}

/**
 * Check status of a worker: last log lines + git diff stat
 */
export function checkStatus(workdir) {
  const cwd = resolveWorkdir(workdir);
  const logPath = getLogPath(cwd);

  let log = "";
  let diffStat = "";
  let pid = null;

  try {
    if (fs.existsSync(logPath)) {
      const fullLog = fs.readFileSync(logPath, "utf8");
      log = fullLog.split("\n").slice(-50).join("\n"); // last 50 lines
    }
  } catch (e) {
    log = `Error reading log: ${e.message}`;
  }

  try {
    diffStat = execSync(`git -C "${cwd}" diff --stat`, { encoding: "utf8" }).trim();
  } catch (e) {
    diffStat = `Error getting diff: ${e.message}`;
  }

  try {
    if (fs.existsSync(path.join(cwd, ".agent-pid"))) {
      pid = parseInt(fs.readFileSync(path.join(cwd, ".agent-pid"), "utf8").trim());
    }
  } catch {}

  // Check if process is still alive (basic)
  let running = false;
  if (pid) {
    try {
      process.kill(pid, 0); // signal 0 = check existence
      running = true;
    } catch {
      running = false;
    }
  }

  return {
    workdir: cwd,
    pid,
    running,
    log_tail: log,
    diff_stat: diffStat || "No changes yet",
    timestamp: new Date().toISOString(),
  };
}

/**
 * Get full git diff from a workdir
 */
export function getFullDiff(workdir) {
  const cwd = resolveWorkdir(workdir);
  try {
    const diff = execSync(`git -C "${cwd}" diff`, { encoding: "utf8", maxBuffer: 5 * 1024 * 1024 });
    return { workdir: cwd, diff, size: diff.length };
  } catch (e) {
    return { workdir: cwd, diff: "", error: e.message };
  }
}

/**
 * Run tests in the workdir (project-specific)
 */
export function runTests(workdir) {
  const cwd = resolveWorkdir(workdir);
  try {
    // Altron is Gradle + Kotlin (Android). Adjust as needed.
    // Common patterns:
    const commands = [
      "cd " + cwd + " && ./gradlew test --quiet 2>&1 || true",
      "cd " + cwd + " && npm test 2>&1 || true",
    ];

    let output = "";
    for (const cmd of commands) {
      try {
        output += execSync(cmd, { encoding: "utf8", timeout: 120000 });
      } catch (e) {
        output += (e.stdout || "") + (e.stderr || "");
      }
    }
    return { workdir: cwd, output: output.trim() || "No test output" };
  } catch (e) {
    return { workdir: cwd, error: e.message, output: "" };
  }
}

/**
 * Update a task's status and notes
 */
export function updateTaskStatus(taskId, status, notes = "") {
  // Hybrid model supports "escalated"
  const validStatuses = ["pending", "running", "needs_review", "done", "failed", "conflict", "escalated"];
  if (!validStatuses.includes(status)) {
    throw new Error(`Invalid status: ${status}`);
  }

  const success = updateTaskStatusInYaml(taskId, status, notes);
  return {
    success,
    taskId,
    status,
    notes,
  };
}

/**
 * List all tasks (parsed)
 */
export function listTasks() {
  const tasks = getCurrentTasks();
  return {
    total: tasks.length,
    tasks,
    tasks_file: TASKS_FILE,
  };
}

/**
 * Get a specific task
 */
export function getTask(taskId) {
  const tasks = getCurrentTasks();
  const task = tasks.find(t => t.id === taskId);
  return task || { error: "Task not found", taskId };
}

/**
 * NEW: Plan how to split a task (Hybrid model)
 * Claude calls this to decide:
 * - Which parts go to agent (long/easy)
 * - Which parts Claude keeps (30-40% hard)
 */
export function planTaskSplit(taskId, plan) {
  // plan = { claude_responsibility: "...", agent_responsibility: "...", difficulty: "easy|medium|hard" }
  const success = updateHybridTaskFields(taskId, {
    notes: `PLAN: Claude=${plan.claude_responsibility || 'N/A'} | Agent=${plan.agent_responsibility || 'N/A'}`,
  });

  // Also update difficulty if provided
  if (plan.difficulty) {
    // Simple append to notes for now (we can improve parser later)
  }

  return {
    success,
    taskId,
    plan,
    message: "Task split planned. Use this to guide dispatch or direct work."
  };
}

/**
 * NEW: Escalate a task to Claude when agent is stuck (after 3 retries or explicit)
 */
export function escalateTask(taskId, reason = "Agent stuck or max retries reached") {
  const updated = updateHybridTaskFields(taskId, {
    status: "escalated",
    escalated: true,
    owner: "claude",
    retry_count: 3, // force
    notes: `ESCALATED by Claude: ${reason}`
  });

  return {
    success: updated,
    taskId,
    status: "escalated",
    owner: "claude",
    message: "Task escalated. Claude will now complete this work directly in the main checkout or via direct edits.",
    reason
  };
}

/**
 * NEW: Claude claims a task to work on it itself (the hard 30-40%)
 */
export function claimTaskForClaude(taskId, responsibility = "") {
  const updated = updateHybridTaskFields(taskId, {
    owner: "claude",
    status: "running",
    escalated: true,
    notes: responsibility ? `Claimed by Claude: ${responsibility}` : "Claimed by Claude for direct work"
  });

  return {
    success: updated,
    taskId,
    owner: "claude",
    message: "Claude has claimed this task. You may now edit files directly in the main repo or a dedicated worktree."
  };
}

/**
 * Helper: Increment retry count for a task
 */
export function incrementRetry(taskId) {
  // This is a bit hacky without full YAML lib — we read + patch
  const tasks = getCurrentTasks();
  const task = tasks.find(t => t.id === taskId);
  if (!task) return false;

  const newCount = (task.retry_count || 0) + 1;
  const shouldEscalate = newCount >= 3;

  updateHybridTaskFields(taskId, {
    retry_count: newCount,
    notes: `Retry #${newCount}`
  });

  if (shouldEscalate) {
    updateHybridTaskFields(taskId, {
      status: "escalated",
      escalated: true,
      owner: "claude",
      notes: "AUTO-ESCALATED after 3 retries"
    });
  }

  return { retry_count: newCount, auto_escalated: shouldEscalate };
}

// ============================================================
// MCP SERVER SETUP
// ============================================================

const server = new McpServer({
  name: "altron-orchestrator",
  version: "1.0.0",
});

// --- Tool: dispatch_task ---
server.tool(
  "dispatch_task",
  "Start a headless coding agent on an isolated worktree. " +
  "Claude (orchestrator) should call this for every pending task instead of editing code itself. " +
  "Supports two modes: normal (detached process) or **deep tmux** (recommended for full STAR experience). " +
  "Set use_tmux=true for a real multiplexed tmux window with splits, capture, focus, etc.",
  {
    tool: z.enum(["opencode", "cursor", "hermes", "echo"]).describe("Which worker agent CLI to use"),
    prompt: z.string().min(10).describe("The full task description / prompt to give the agent"),
    workdir: z.string().describe("Relative or absolute path to the agent's git worktree (e.g. '../work-opencode')"),
    task_id: z.string().optional().describe("Optional task ID from tasks.yaml to auto-update status"),
    use_tmux: z.boolean().default(false).describe("Launch inside a dedicated tmux window (Deep STAR emulation)"),
  },
  async ({ tool, prompt, workdir, task_id, use_tmux }) => {
    try {
      if (use_tmux) {
        const tmux = await getTmux();
        const tmuxResult = tmux.launchInTmux(task_id || "unknown", tool, prompt, workdir);
        return {
          content: [{ type: "text", text: JSON.stringify({ mode: "tmux", ...tmuxResult }, null, 2) }],
        };
      } else {
        const result = dispatchTask(tool, prompt, workdir, task_id);
        return {
          content: [{ type: "text", text: JSON.stringify({ mode: "process", ...result }, null, 2) }],
        };
      }
    } catch (error) {
      return {
        content: [{ type: "text", text: `ERROR: ${error.message}` }],
        isError: true,
      };
    }
  }
);

// --- Tool: check_status ---
server.tool(
  "check_status",
  "Poll a worker's progress. Returns tail of its .agent-log.txt + git diff --stat. " +
  "Use periodically after dispatch_task.",
  {
    workdir: z.string().describe("Path to the worker's worktree (same as used in dispatch)"),
  },
  async ({ workdir }) => {
    try {
      const status = checkStatus(workdir);
      return {
        content: [{ type: "text", text: JSON.stringify(status, null, 2) }],
      };
    } catch (error) {
      return {
        content: [{ type: "text", text: `ERROR: ${error.message}` }],
        isError: true,
      };
    }
  }
);

// --- Tool: get_full_diff ---
server.tool(
  "get_full_diff",
  "Retrieve the complete unified git diff from a worker's worktree. " +
  "Call this after check_status reports the agent is done or before review/merge.",
  {
    workdir: z.string(),
  },
  async ({ workdir }) => {
    try {
      const result = getFullDiff(workdir);
      return {
        content: [{ type: "text", text: result.diff || JSON.stringify(result, null, 2) }],
      };
    } catch (error) {
      return {
        content: [{ type: "text", text: `ERROR: ${error.message}` }],
        isError: true,
      };
    }
  }
);

// --- Tool: run_tests ---
server.tool(
  "run_tests",
  "Execute the project's test suite inside a worker's worktree. " +
  "Useful to validate a worker's changes before approving.",
  {
    workdir: z.string(),
  },
  async ({ workdir }) => {
    try {
      const result = runTests(workdir);
      return {
        content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
      };
    } catch (error) {
      return {
        content: [{ type: "text", text: `ERROR: ${error.message}` }],
        isError: true,
      };
    }
  }
);

// --- Tool: update_task_status ---
server.tool(
  "update_task_status",
  "Update the status of a task in tasks.yaml. " +
  "Valid statuses: pending, running, needs_review, done, failed, conflict. " +
  "Always call this after every significant state change.",
  {
    task_id: z.string(),
    status: z.enum(["pending", "running", "needs_review", "done", "failed", "conflict"]),
    notes: z.string().optional(),
  },
  async ({ task_id, status, notes }) => {
    try {
      const result = updateTaskStatus(task_id, status, notes || "");
      return {
        content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
      };
    } catch (error) {
      return {
        content: [{ type: "text", text: `ERROR: ${error.message}` }],
        isError: true,
      };
    }
  }
);

// --- Tool: list_tasks ---
server.tool(
  "list_tasks",
  "Read the current tasks.yaml board and return all tasks with status. " +
  "Call at the beginning of every orchestration session.",
  {},
  async () => {
    try {
      const result = listTasks();
      return {
        content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
      };
    } catch (error) {
      return {
        content: [{ type: "text", text: `ERROR: ${error.message}` }],
        isError: true,
      };
    }
  }
);

// --- Tool: get_task ---
server.tool(
  "get_task",
  "Fetch a single task by ID from tasks.yaml",
  {
    task_id: z.string(),
  },
  async ({ task_id }) => {
    try {
      const task = getTask(task_id);
      return {
        content: [{ type: "text", text: JSON.stringify(task, null, 2) }],
      };
    } catch (error) {
      return {
        content: [{ type: "text", text: `ERROR: ${error.message}` }],
        isError: true,
      };
    }
  }
);

// --- Tool: create_worktree (convenience) ---
server.tool(
  "create_worktree",
  "Create a new git worktree + branch for a worker if it doesn't exist yet. " +
  "Useful for initializing new tasks.",
  {
    branch_name: z.string().describe("e.g. task/opencode-3"),
    worktree_path: z.string().describe("e.g. ../work-opencode-3"),
  },
  async ({ branch_name, worktree_path }) => {
    try {
      const fullPath = resolveWorkdir(worktree_path);
      if (fs.existsSync(fullPath)) {
        return {
          content: [{ type: "text", text: JSON.stringify({ message: "Worktree already exists", path: fullPath }) }],
        };
      }

      execSync(`git worktree add "${fullPath}" -b "${branch_name}"`, {
        cwd: REPO_ROOT,
        encoding: "utf8",
      });

      return {
        content: [{ type: "text", text: JSON.stringify({ success: true, path: fullPath, branch: branch_name }) }],
      };
    } catch (error) {
      return {
        content: [{ type: "text", text: `ERROR creating worktree: ${error.message}` }],
        isError: true,
      };
    }
  }
);

// ============================================================
// NEW HYBRID MODEL TOOLS
// ============================================================

// --- Tool: plan_task_split ---
server.tool(
  "plan_task_split",
  "Claude uses this FIRST to plan a task. " +
  "Decide which parts are LONG/EASY (give to agent) and which are DIFFICULT (Claude keeps ~30-40%). " +
  "Always call this before dispatching or claiming work.",
  {
    task_id: z.string(),
    claude_responsibility: z.string().describe("What difficult/complex parts Claude will do (30-40%)"),
    agent_responsibility: z.string().describe("What long but easier parts the sub-agent will do"),
    difficulty: z.enum(["easy", "medium", "hard"]).optional(),
  },
  async ({ task_id, claude_responsibility, agent_responsibility, difficulty }) => {
    try {
      const result = planTaskSplit(task_id, {
        claude_responsibility,
        agent_responsibility,
        difficulty,
      });
      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    } catch (error) {
      return { content: [{ type: "text", text: `ERROR: ${error.message}` }], isError: true };
    }
  }
);

// --- Tool: escalate_task ---
server.tool(
  "escalate_task",
  "Call this when a sub-agent is stuck, or after 3 failed retries (auto-incremented). " +
  "Claude will take over and complete the task itself.",
  {
    task_id: z.string(),
    reason: z.string().optional().describe("Why escalation happened (e.g. 'agent stuck after 3 attempts')"),
  },
  async ({ task_id, reason }) => {
    try {
      const result = escalateTask(task_id, reason || "Agent stuck or max retries reached");
      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    } catch (error) {
      return { content: [{ type: "text", text: `ERROR: ${error.message}` }], isError: true };
    }
  }
);

// --- Tool: claim_task_for_claude ---
server.tool(
  "claim_task_for_claude",
  "Claude uses this to take direct ownership of the difficult 30-40% of a task. " +
  "After claiming, Claude can edit files directly.",
  {
    task_id: z.string(),
    responsibility: z.string().optional().describe("Description of the hard part Claude will now implement"),
  },
  async ({ task_id, responsibility }) => {
    try {
      const result = claimTaskForClaude(task_id, responsibility);
      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    } catch (error) {
      return { content: [{ type: "text", text: `ERROR: ${error.message}` }], isError: true };
    }
  }
);

// --- Tool: increment_agent_retry (internal helper exposed) ---
server.tool(
  "increment_agent_retry",
  "Call after each failed attempt by a sub-agent. Automatically escalates at 3 retries.",
  {
    task_id: z.string(),
  },
  async ({ task_id }) => {
    try {
      const result = incrementRetry(task_id);
      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    } catch (error) {
      return { content: [{ type: "text", text: `ERROR: ${error.message}` }], isError: true };
    }
  }
);

// ============================================================
// star-STYLE FEATURES (integrated)
// ============================================================

// Lazy load star modules
let starMod = null;
async function getStar() {
  if (!starMod) {
    starMod = await import("./star-integration.js");
  }
  return starMod;
}

// --- Tool: list_workspaces (star sidebar) ---
server.tool(
  "list_workspaces",
  "STAR-style: Returns rich workspace metadata (like the vertical sidebar in STAR). " +
  "Shows git branch, ports, last notification, owner for every agent workspace.",
  {},
  async () => {
    try {
      const star = await getStar();
      const data = star.getWorkspaces();
      return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
    } catch (error) {
      return { content: [{ type: "text", text: `ERROR: ${error.message}` }], isError: true };
    }
  }
);

// --- Tool: send_notification (star notify) ---
server.tool(
  "send_notification",
  "STAR-style notification system. Use this to simulate the blue rings + notification panel. " +
  "Agents and hooks should call this when they need attention.",
  {
    task_id: z.string(),
    message: z.string(),
    type: z.enum(["waiting", "done", "error", "info", "stuck"]).default("info"),
    workdir: z.string().optional(),
  },
  async ({ task_id, message, type, workdir }) => {
    try {
      const star = await getStar();
      const notif = star.sendStarNotification({ taskId: task_id, message, type, workdir });
      // Also update workspace
      if (workdir) {
        star.updateWorkspace(`ws-${task_id.toLowerCase().replace('-','')}`, {
          last_notification: message,
          notification_count: 1
        });
      }
      return { content: [{ type: "text", text: JSON.stringify({ success: true, notification: notif }, null, 2) }] };
    } catch (error) {
      return { content: [{ type: "text", text: `ERROR: ${error.message}` }], isError: true };
    }
  }
);

// --- Tool: get_notifications ---
server.tool(
  "get_notifications",
  "STAR-style: Returns all notifications (like the notification panel).",
  {},
  async () => {
    try {
      const star = await getStar();
      const data = star.getNotifications();
      return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
    } catch (error) {
      return { content: [{ type: "text", text: `ERROR: ${error.message}` }], isError: true };
    }
  }
);

// --- Tool: launch_browser / navigate_browser / browser_click etc. ---
server.tool(
  "launch_browser",
  "STAR-style scriptable browser (Playwright). Launch a browser pane that agents can control.",
  {
    headless: z.boolean().default(false),
  },
  async ({ headless }) => {
    try {
      const star = await getStar();
      const browser = await star.getBrowserTools();
      const res = await browser.launchBrowser({ headless });
      return { content: [{ type: "text", text: JSON.stringify(res, null, 2) }] };
    } catch (error) {
      return { content: [{ type: "text", text: `ERROR: ${error.message}` }], isError: true };
    }
  }
);

server.tool(
  "navigate_browser",
  "Navigate the STAR-style browser to a URL (great for dev servers or docs).",
  {
    url: z.string(),
  },
  async ({ url }) => {
    try {
      const star = await getStar();
      const browser = await star.getBrowserTools();
      const res = await browser.navigate(url);
      return { content: [{ type: "text", text: JSON.stringify(res, null, 2) }] };
    } catch (error) {
      return { content: [{ type: "text", text: `ERROR: ${error.message}` }], isError: true };
    }
  }
);

server.tool(
  "browser_click",
  "Click an element in the scriptable browser.",
  {
    selector: z.string(),
  },
  async ({ selector }) => {
    try {
      const star = await getStar();
      const browser = await star.getBrowserTools();
      const res = await browser.click(selector);
      return { content: [{ type: "text", text: JSON.stringify(res, null, 2) }] };
    } catch (error) {
      return { content: [{ type: "text", text: `ERROR: ${error.message}` }], isError: true };
    }
  }
);

server.tool(
  "get_browser_state",
  "Get current state of the star browser (URL, title).",
  {},
  async () => {
    try {
      const star = await getStar();
      const browser = await star.getBrowserTools();
      const res = await browser.getCurrentState();
      return { content: [{ type: "text", text: JSON.stringify(res, null, 2) }] };
    } catch (error) {
      return { content: [{ type: "text", text: `ERROR: ${error.message}` }], isError: true };
    }
  }
);

// --- Tool: run_custom_command (star style) ---
server.tool(
  "run_custom_command",
  "Run project-specific custom commands defined in star.json (like star command palette).",
  {
    name: z.string().describe("Name from star.json custom_commands"),
  },
  async ({ name }) => {
    try {
      const star = await getStar();
      const res = star.runCustomCommand(name);
      return { content: [{ type: "text", text: JSON.stringify(res, null, 2) }] };
    } catch (error) {
      return { content: [{ type: "text", text: `ERROR: ${error.message}` }], isError: true };
    }
  }
);

// ============================================================
// DEEP TMUX MULTIPLEXING (STAR-style workspace management)
// ============================================================

let tmuxMod = null;
async function getTmux() {
  if (!tmuxMod) {
    tmuxMod = await import("./tmux-integration.js");
  }
  return tmuxMod;
}

// --- Tool: tmux_get_status ---
server.tool(
  "tmux_get_status",
  "STAR deep emulation: Check if tmux is available and show active sessions/windows.",
  {},
  async () => {
    try {
      const tmux = await getTmux();
      const status = tmux.getTmuxStatus();
      return { content: [{ type: "text", text: JSON.stringify(status, null, 2) }] };
    } catch (error) {
      return { content: [{ type: "text", text: `ERROR: ${error.message}` }], isError: true };
    }
  }
);

// --- Tool: tmux_list_workspaces ---
server.tool(
  "tmux_list_workspaces",
  "STAR deep emulation: List all tmux windows (workspaces) with rich metadata. " +
  "Merges with workspaces.yaml for a complete STAR-style sidebar view.",
  {},
  async () => {
    try {
      const tmux = await getTmux();
      const data = tmux.getEnhancedWorkspaces();
      return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
    } catch (error) {
      return { content: [{ type: "text", text: `ERROR: ${error.message}` }], isError: true };
    }
  }
);

// --- Tool: tmux_create_workspace ---
server.tool(
  "tmux_create_workspace",
  "STAR deep emulation: Create a dedicated tmux window (surface) for a task/worker. " +
  "Gives Claude full visibility and control like native STAR tabs.",
  {
    task_id: z.string(),
    worker: z.string(),
    workdir: z.string(),
    session: z.string().optional(),
  },
  async ({ task_id, worker, workdir, session }) => {
    try {
      const tmux = await getTmux();
      const result = tmux.createWorkspace(task_id, worker, workdir, session);
      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    } catch (error) {
      return { content: [{ type: "text", text: `ERROR: ${error.message}` }], isError: true };
    }
  }
);

// --- Tool: tmux_launch_agent ---
server.tool(
  "tmux_launch_agent",
  "Launch a coding agent **inside** a tmux pane (Deep STAR emulation). " +
  "This is the most powerful mode — the agent runs in a real multiplexed terminal window.",
  {
    task_id: z.string(),
    worker: z.enum(["opencode", "cursor", "hermes", "echo"]),
    prompt: z.string(),
    workdir: z.string(),
    session: z.string().optional(),
  },
  async ({ task_id, worker, prompt, workdir, session }) => {
    try {
      const tmux = await getTmux();
      const result = tmux.launchInTmux(task_id, worker, prompt, workdir);
      // Also update the normal dispatch log for compatibility
      try {
        const logPath = path.join(path.resolve(REPO_ROOT, workdir), ".agent-log.txt");
        fs.appendFileSync(logPath, `\n[tmux] Agent launched in tmux: ${result.window || 'unknown'}\n`);
      } catch {}
      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    } catch (error) {
      return { content: [{ type: "text", text: `ERROR: ${error.message}` }], isError: true };
    }
  }
);

// --- Tool: tmux_send ---
server.tool(
  "tmux_send",
  "Send keystrokes / commands to a running tmux workspace window.",
  {
    task_id: z.string(),
    worker: z.string(),
    command: z.string(),
    session: z.string().optional(),
  },
  async ({ task_id, worker, command, session }) => {
    try {
      const tmux = await getTmux();
      const result = tmux.sendToWorkspace(task_id, worker, command, session);
      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    } catch (error) {
      return { content: [{ type: "text", text: `ERROR: ${error.message}` }], isError: true };
    }
  }
);

// --- Tool: tmux_capture ---
server.tool(
  "tmux_capture",
  "Capture the last N lines from a tmux workspace (like reading the terminal output).",
  {
    task_id: z.string(),
    worker: z.string(),
    lines: z.number().default(80),
    session: z.string().optional(),
  },
  async ({ task_id, worker, lines, session }) => {
    try {
      const tmux = await getTmux();
      const result = tmux.captureWorkspace(task_id, worker, lines, session);
      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    } catch (error) {
      return { content: [{ type: "text", text: `ERROR: ${error.message}` }], isError: true };
    }
  }
);

// --- Tool: tmux_split ---
server.tool(
  "tmux_split",
  "Split a tmux workspace horizontally or vertically (STAR-style multi-pane).",
  {
    task_id: z.string(),
    worker: z.string(),
    direction: z.enum(["horizontal", "vertical"]).default("horizontal"),
    session: z.string().optional(),
  },
  async ({ task_id, worker, direction, session }) => {
    try {
      const tmux = await getTmux();
      const result = tmux.splitWorkspace(task_id, worker, direction, session);
      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    } catch (error) {
      return { content: [{ type: "text", text: `ERROR: ${error.message}` }], isError: true };
    }
  }
);

// --- Tool: tmux_focus ---
server.tool(
  "tmux_focus",
  "Focus/switch to a specific tmux workspace window (like clicking a tab in STAR).",
  {
    task_id: z.string(),
    worker: z.string(),
    session: z.string().optional(),
  },
  async ({ task_id, worker, session }) => {
    try {
      const tmux = await getTmux();
      const result = tmux.focusWorkspace(task_id, worker, session);
      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    } catch (error) {
      return { content: [{ type: "text", text: `ERROR: ${error.message}` }], isError: true };
    }
  }
);

// Start the server
async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  // Log to stderr only (stdout is reserved for MCP protocol)
  console.error("🚀 Altron Orchestrator MCP server started");
  console.error(`   Repo root: ${REPO_ROOT}`);
  console.error(`   Tasks file: ${TASKS_FILE}`);
  console.error(`   Ready to accept tool calls from Claude.`);
}

main().catch((err) => {
  console.error("Fatal MCP server error:", err);
  process.exit(1);
});