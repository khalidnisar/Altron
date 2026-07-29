/**
 * Server-side API client.
 *
 * Browser requests go to the API through the Next.js rewrite/proxy, while
 * server components talk to the API container directly over the compose network.
 */

const BASE =
  process.env.APPFORGE_API_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  'http://api:8000';

export const OPERATOR_TOKEN = process.env.APPFORGE_OPERATOR_TOKEN ?? '';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}/api${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(OPERATOR_TOKEN ? { 'X-Operator-Token': OPERATOR_TOKEN } : {}),
      ...(init?.headers ?? {}),
    },
    cache: 'no-store',
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`API ${res.status} on ${path}: ${detail.slice(0, 300)}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

/** Returns a fallback instead of throwing, so one dead panel cannot blank the page. */
export async function safe<T>(p: Promise<T>, fallback: T): Promise<T> {
  try {
    return await p;
  } catch (err) {
    console.error('[appforge] api error:', err);
    return fallback;
  }
}

// ---------------------------------------------------------------- types

export type Niche = {
  id: number; name: string; slug: string; category: string;
  icon?: string | null; app_count: number; saturation: number;
};

export type ViralApp = {
  id: number; name: string; package_name?: string | null;
  developer?: string | null; rating?: number | null;
  total_downloads?: number | null; last_month_downloads?: number | null;
  last_month_revenue?: number | null; total_reviews?: number | null;
  category?: string | null; description?: string | null;
  problem_solved?: string | null; key_features?: string[] | null;
  monetization_model?: string | null; trend_score?: number | null;
  clone_potential_score?: number | null;
  clone_score_breakdown?: { breakdown: Record<string, number>; complexity: string } | null;
  status: string;
};

export type ViralAppDetail = ViralApp & {
  positive_reviews?: { theme: string; frequency: number; example: string }[] | null;
  negative_reviews?: { issue: string; quote: string; severity: string }[] | null;
  identified_issues?: {
    issue: string; type: string; severity: string; frequency: number;
    user_quotes: string[]; root_cause_hypothesis: string; suggested_fix: string;
  }[] | null;
  improvement_suggestions?: string[] | null;
  rating_distribution?: Record<string, number> | null;
  analysis?: {
    functional_analysis?: any; review_analysis?: any;
    competitive_analysis?: any; technical_assessment?: any;
    recommendation?: string; recommendation_reason?: string;
    must_fix_issues?: string[]; must_add_features?: string[];
    clone_name_ideas?: { name: string; tagline: string; rationale: string }[];
    reviews_analyzed?: number;
  } | null;
};

export type Project = {
  id: number; source_app_id?: number | null; clone_name: string;
  clone_package_name?: string | null; tagline?: string | null;
  status: string; pipeline_stage: string; progress: number;
  blocked_reason?: string | null; ai_recommended_price?: number | null;
  monthly_revenue: number; total_revenue: number;
  repository_url?: string | null; simulator_url?: string | null;
  play_store_url?: string | null; approved_at?: string | null;
  created_at?: string | null;
  source_app_name?: string | null;
  approvals?: Record<string, { by: string; at: string; feedback?: string }> | null;
};

export type ProjectDetail = Project & {
  description?: string | null;
  design_assets?: any; patched_issues?: any[] | null;
  new_features?: string[] | null; tech_stack?: any;
  build_logs?: { timestamp: string; stage: string; message: string; status: string }[] | null;
  remediation_history?: { attempt: number; requested_at: string; reasons: string[]; source: string }[] | null;
  test_results?: any; store_listing?: any; monetization_config?: any;
  rollout_status?: any; version_history?: any[] | null; ltv?: number | null;
  source_app?: ViralApp | null;
};

export type PipelineStatus = {
  apps_discovered: number;
  apps_by_status: Record<string, number>;
  projects_by_stage: Record<string, number>;
  tasks_by_status: Record<string, number>;
  live_apps: number; awaiting_approval: number;
  total_revenue: number; monthly_revenue: number;
};

export type Revenue = {
  window_days: number;
  totals: { revenue: number; ad_revenue: number; iap_revenue: number; subscription_revenue: number };
  daily: { date: string; revenue: number; ad_revenue: number; iap_revenue: number; subscription_revenue: number; downloads: number }[];
  per_app: { project_id: number; name: string; monthly_revenue: number; total_revenue: number }[];
};

export type AgentStatus = {
  agents: { agent: string; healthy: boolean; pending: number; running: number; completed: number; failed: number }[];
};

// ---------------------------------------------------------------- calls

export const api = {
  health: () => request<{ status: string; offline_mode: boolean }>('/health'),
  niches: () => request<Niche[]>('/niches'),
  apps: (qs = '') =>
    request<{ items: ViralApp[]; total: number; page: number; limit: number }>(`/apps${qs}`),
  app: (id: number) => request<ViralAppDetail>(`/apps/${id}`),
  projects: (qs = '') => request<Project[]>(`/projects${qs}`),
  project: (id: number) => request<ProjectDetail>(`/projects/${id}`),
  projectPipeline: (id: number) =>
    request<{ current_stage: string; progress: number; awaiting_approval: boolean;
      approvals: Record<string, { by: string; at: string }>;
      stages: { stage: string; state: string; has_gate: boolean; approved: boolean }[] }>(
      `/projects/${id}/pipeline`),
  pipelineStatus: () => request<PipelineStatus>('/pipeline/status'),
  agents: () => request<AgentStatus>('/agents/status'),
  revenue: (days = 30) => request<Revenue>(`/revenue?days=${days}`),
};
