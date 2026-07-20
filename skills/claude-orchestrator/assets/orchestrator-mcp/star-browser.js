#!/usr/bin/env node
/**
 * STAR-style Scriptable Browser Controller
 * Uses Playwright (headless or headed)
 *
 * Exposes functions used by the MCP server.
 */

import os from 'os';
import path from 'path';

let browser = null;
let context = null;
let page = null;
let currentUrl = null;

// Playwright is an optional dependency — load lazily with a clear error
// instead of crashing every browser tool at import time.
async function getChromium() {
  try {
    const { chromium } = await import('playwright');
    return chromium;
  } catch {
    throw new Error(
      "Playwright is not installed. Run 'npm install playwright && npx playwright install chromium' in the orchestrator-mcp directory to enable browser tools."
    );
  }
}

export async function launchBrowser(options = {}) {
  const { headless = false, width = 1280, height = 800 } = options;

  if (!browser) {
    const chromium = await getChromium();
    browser = await chromium.launch({ headless });
    context = await browser.newContext({
      viewport: { width, height },
    });
    page = await context.newPage();
  }
  return { success: true, headless };
}

export async function navigate(url) {
  if (!page) await launchBrowser();
  await page.goto(url, { waitUntil: 'domcontentloaded' });
  currentUrl = url;
  return { url: page.url(), title: await page.title() };
}

export async function getCurrentState() {
  if (!page) return { active: false };
  return {
    active: true,
    url: page.url(),
    title: await page.title(),
    currentUrl
  };
}

export async function click(selector) {
  if (!page) throw new Error('Browser not launched');
  await page.click(selector);
  return { action: 'click', selector };
}

export async function fill(selector, value) {
  if (!page) throw new Error('Browser not launched');
  await page.fill(selector, value);
  return { action: 'fill', selector };
}

export async function evaluate(script) {
  if (!page) throw new Error('Browser not launched');
  const result = await page.evaluate(script);
  return { result };
}

export async function screenshot(outPath = path.join(os.tmpdir(), 'star-browser.png')) {
  if (!page) throw new Error('Browser not launched');
  await page.screenshot({ path: outPath, fullPage: true });
  return { path: outPath };
}

export async function closeBrowser() {
  if (browser) {
    await browser.close();
    browser = context = page = null;
    currentUrl = null;
  }
  return { closed: true };
}

// Convenience: open a dev server port
export async function openDevServer(port = 3000, urlPath = '/') {
  const url = `http://localhost:${port}${urlPath}`;
  return navigate(url);
}