import { AppSplitChart, RevenueChart, StreamChart } from '@/components/charts';
import { EmptyState, SectionTitle, StatCard, fmtMoney } from '@/components/ui';
import { api, safe, type Revenue } from '@/lib/api';

export const dynamic = 'force-dynamic';

const EMPTY: Revenue = {
  window_days: 30,
  totals: { revenue: 0, ad_revenue: 0, iap_revenue: 0, subscription_revenue: 0 },
  daily: [], per_app: [],
};

export default async function RevenuePage() {
  const revenue = await safe(api.revenue(30), EMPTY);

  if (revenue.daily.length === 0) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold tracking-tight">Revenue</h1>
        <EmptyState
          title="No revenue recorded"
          hint="Revenue is tracked once an app reaches the live stage and the Growth Agent starts monitoring it."
          action={{ href: '/pipeline', label: 'View pipeline' }}
        />
      </div>
    );
  }

  const { totals } = revenue;
  const pie = revenue.per_app
    .filter((a) => a.total_revenue > 0)
    .slice(0, 6)
    .map((a) => ({ name: a.name, value: a.total_revenue }));

  const best = revenue.per_app[0];

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Revenue</h1>
          <p className="mt-1 text-sm text-muted">Last {revenue.window_days} days</p>
        </div>
        <a className="btn-ghost" href="/api/revenue/export">Export CSV</a>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Total" value={fmtMoney(totals.revenue)} tone="ok" />
        <StatCard label="Ads" value={fmtMoney(totals.ad_revenue)}
                  sub={pct(totals.ad_revenue, totals.revenue)} />
        <StatCard label="In-app purchases" value={fmtMoney(totals.iap_revenue)}
                  sub={pct(totals.iap_revenue, totals.revenue)} />
        <StatCard label="Subscriptions" value={fmtMoney(totals.subscription_revenue)}
                  sub={pct(totals.subscription_revenue, totals.revenue)} />
      </div>

      <div>
        <SectionTitle>Daily revenue</SectionTitle>
        <div className="card"><RevenueChart data={revenue.daily} /></div>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <div>
          <SectionTitle>By stream</SectionTitle>
          <div className="card"><StreamChart data={revenue.daily} /></div>
        </div>
        <div>
          <SectionTitle>By app</SectionTitle>
          <div className="card">
            {pie.length > 0 ? (
              <AppSplitChart data={pie} />
            ) : (
              <p className="py-16 text-center text-sm text-muted">No per-app revenue yet.</p>
            )}
          </div>
        </div>
      </div>

      <div>
        <SectionTitle
          right={best ? <span className="text-sm text-muted">
            Top: {best.name} at {fmtMoney(best.monthly_revenue)}/mo
          </span> : undefined}
        >
          Portfolio
        </SectionTitle>
        <div className="card overflow-x-auto p-0">
          <table className="w-full">
            <caption className="sr-only">Revenue by application</caption>
            <thead className="border-b border-edge">
              <tr>
                <th scope="col" className="th">App</th>
                <th scope="col" className="th text-right">This month</th>
                <th scope="col" className="th text-right">All time</th>
                <th scope="col" className="th text-right">Share</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-edge">
              {revenue.per_app.map((a) => (
                <tr key={a.project_id}>
                  <td className="td font-medium">{a.name}</td>
                  <td className="td text-right">{fmtMoney(a.monthly_revenue)}</td>
                  <td className="td text-right text-muted">{fmtMoney(a.total_revenue)}</td>
                  <td className="td text-right text-muted">
                    {pct(a.total_revenue, revenue.per_app.reduce((s, x) => s + x.total_revenue, 0))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function pct(part: number, whole: number): string {
  if (!whole) return '0%';
  return `${((part / whole) * 100).toFixed(1)}%`;
}
