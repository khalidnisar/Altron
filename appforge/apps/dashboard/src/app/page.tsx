import Link from 'next/link';

import { RevenueChart } from '@/components/charts';
import { EmptyState, Progress, SectionTitle, StagePill, StatCard, fmtMoney } from '@/components/ui';
import { api, safe, type PipelineStatus, type Project, type Revenue } from '@/lib/api';

export const dynamic = 'force-dynamic';

const EMPTY_STATUS: PipelineStatus = {
  apps_discovered: 0, apps_by_status: {}, projects_by_stage: {}, tasks_by_status: {},
  live_apps: 0, awaiting_approval: 0, total_revenue: 0, monthly_revenue: 0,
};

const EMPTY_REVENUE: Revenue = {
  window_days: 30, totals: { revenue: 0, ad_revenue: 0, iap_revenue: 0, subscription_revenue: 0 },
  daily: [], per_app: [],
};

export default async function DashboardPage() {
  const [status, revenue, projects] = await Promise.all([
    safe(api.pipelineStatus(), EMPTY_STATUS),
    safe(api.revenue(30), EMPTY_REVENUE),
    safe(api.projects('?sort_by=revenue'), [] as Project[]),
  ]);

  const building = Object.entries(status.projects_by_stage)
    .filter(([stage]) => !['live', 'rejected', 'sunset'].includes(stage))
    .reduce((sum, [, count]) => sum + count, 0);

  const topApps = projects.filter((p) => p.total_revenue > 0).slice(0, 5);
  const needsReview = projects.filter(
    (p) => p.pipeline_stage === 'awaiting_approval' || p.pipeline_stage === 'simulation',
  );

  if (status.apps_discovered === 0) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
        <EmptyState
          title="No data yet"
          hint="Seed the platform to run discovery across all 20 niches, then walk projects through the pipeline."
          action={{ href: '/settings', label: 'Go to settings' }}
        />
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
        {needsReview.length > 0 && (
          <Link href="/pipeline" className="pill bg-warn/15 text-warn">
            {needsReview.length} awaiting approval
          </Link>
        )}
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Total revenue" value={fmtMoney(status.total_revenue)} sub="All time" />
        <StatCard label="This month" value={fmtMoney(status.monthly_revenue)}
                  sub="Across portfolio" tone="ok" />
        <StatCard label="Live apps" value={status.live_apps} sub="Published to Play" />
        <StatCard label="In pipeline" value={building} sub={`${status.apps_discovered} apps discovered`} />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <SectionTitle>Revenue, last 30 days</SectionTitle>
          <div className="card">
            {revenue.daily.length > 0 ? (
              <RevenueChart data={revenue.daily} />
            ) : (
              <p className="py-16 text-center text-sm text-muted">
                No revenue recorded yet. Revenue appears once an app goes live.
              </p>
            )}
          </div>
        </div>

        <div>
          <SectionTitle>Pipeline</SectionTitle>
          <div className="card space-y-3">
            {Object.entries(status.projects_by_stage).length === 0 && (
              <p className="text-sm text-muted">No projects yet.</p>
            )}
            {Object.entries(status.projects_by_stage)
              .sort((a, b) => b[1] - a[1])
              .map(([stage, count]) => (
                <div key={stage} className="flex items-center justify-between gap-3">
                  <StagePill stage={stage} />
                  <span className="text-sm font-medium">{count}</span>
                </div>
              ))}
          </div>
        </div>
      </div>

      <div>
        <SectionTitle right={<Link href="/revenue" className="text-sm text-brand">View all</Link>}>
          Top revenue apps
        </SectionTitle>
        {topApps.length === 0 ? (
          <div className="card text-sm text-muted">
            No apps are generating revenue yet.
          </div>
        ) : (
          <div className="card divide-y divide-edge p-0">
            {topApps.map((p) => (
              <Link key={p.id} href={`/pipeline/${p.id}`}
                    className="flex items-center gap-4 p-4 transition-colors hover:bg-panel2">
                <div className="min-w-0 flex-1">
                  <div className="truncate font-medium">{p.clone_name}</div>
                  <div className="mt-1.5"><Progress value={p.progress} /></div>
                </div>
                <div className="text-right">
                  <div className="font-semibold">{fmtMoney(p.monthly_revenue)}</div>
                  <div className="text-xs text-muted">per month</div>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
