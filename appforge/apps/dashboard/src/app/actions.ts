'use server';

import { revalidatePath } from 'next/cache';

import { OPERATOR_TOKEN } from '@/lib/api';

const BASE =
  process.env.APPFORGE_API_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  'http://api:8000';

async function post(path: string, body?: unknown) {
  const res = await fetch(`${BASE}/api${path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(OPERATOR_TOKEN ? { 'X-Operator-Token': OPERATOR_TOKEN } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
    cache: 'no-store',
  });
  if (!res.ok) {
    throw new Error(`${res.status}: ${(await res.text()).slice(0, 200)}`);
  }
  return res.json().catch(() => ({}));
}

export async function approveProject(projectId: number, feedback: string) {
  await post(`/projects/${projectId}/approve`, { approved_by: 'operator', feedback });
  revalidatePath('/pipeline');
  revalidatePath(`/pipeline/${projectId}`);
  revalidatePath('/simulator');
  revalidatePath('/');
}

export async function rejectProject(projectId: number, feedback: string) {
  await post(`/projects/${projectId}/reject`, {
    rejected_by: 'operator',
    feedback: feedback || 'Rejected without notes',
  });
  revalidatePath('/pipeline');
  revalidatePath(`/pipeline/${projectId}`);
  revalidatePath('/simulator');
}

export async function runPipeline(limit = 25) {
  const result = await post(`/pipeline/run?limit=${limit}`);
  revalidatePath('/');
  revalidatePath('/pipeline');
  revalidatePath('/discover');
  revalidatePath('/revenue');
  return result;
}

export async function seedPlatform() {
  const result = await post('/seed?run_pipeline=true');
  revalidatePath('/');
  revalidatePath('/discover');
  revalidatePath('/pipeline');
  revalidatePath('/revenue');
  return result;
}

export async function triggerDiscovery() {
  await post('/pipeline/trigger', {
    agent: 'discovery', task_type: 'scan_all_niches', priority: 100,
  });
  revalidatePath('/discover');
}

export async function startClone(appId: number) {
  await post(`/apps/${appId}/clone`, {});
  revalidatePath('/pipeline');
  revalidatePath(`/discover/${appId}`);
}

export async function analyzeApp(appId: number) {
  await post(`/apps/${appId}/analyze`);
  revalidatePath(`/discover/${appId}`);
}
