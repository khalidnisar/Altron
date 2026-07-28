import Link from 'next/link';

import { DiscoverButton, RunPipelineButton } from '@/components/actions-client';
import { EmptyState, ScorePill, SectionTitle, fmtCount, fmtMoney } from '@/components/ui';
import { api, safe, type Niche, type ViralApp } from '@/lib/api';

export const dynamic = 'force-dynamic';

type SearchParams = {
  niche?: string; min_revenue?: string; min_clone_score?: string;
  sort_by?: string; search?: string; page?: string;
};

export default async function DiscoverPage({ searchParams }: { searchParams: SearchParams }) {
  const params = new URLSearchParams();
  params.set('limit', '30');
  params.set('page', searchParams.page ?? '1');
  params.set('sort_by', searchParams.sort_by ?? 'clone_score');
  if (searchParams.niche) params.set('niche', searchParams.niche);
  if (searchParams.min_revenue) params.set('min_revenue', searchParams.min_revenue);
  if (searchParams.min_clone_score) params.set('min_clone_score', searchParams.min_clone_score);
  if (searchParams.search) params.set('search', searchParams.search);

  const [niches, result] = await Promise.all([
    safe(api.niches(), [] as Niche[]),
    safe(api.apps(`?${params.toString()}`), { items: [] as ViralApp[], total: 0, page: 1, limit: 30 }),
  ]);

  const page = Number(searchParams.page ?? '1');
  const pages = Math.max(1, Math.ceil(result.total / 30));

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Discover</h1>
          <p className="mt-1 text-sm text-muted">
            {result.total} viral apps found across {niches.length} niches
          </p>
        </div>
        <div className="flex gap-2">
          <DiscoverButton />
          <RunPipelineButton limit={40} />
        </div>
      </div>

      <form className="card grid gap-3 md:grid-cols-5" method="get">
        <div>
          <label className="label" htmlFor="search">Search</label>
          <input id="search" name="search" defaultValue={searchParams.search}
                 className="input mt-1" placeholder="App name" />
        </div>
        <div>
          <label className="label" htmlFor="niche">Niche</label>
          <select id="niche" name="niche" defaultValue={searchParams.niche ?? ''}
                  className="input mt-1">
            <option value="">All niches</option>
            {niches.map((n) => (
              <option key={n.slug} value={n.slug}>{n.name}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="label" htmlFor="min_revenue">Min revenue</label>
          <select id="min_revenue" name="min_revenue"
                  defaultValue={searchParams.min_revenue ?? ''} className="input mt-1">
            <option value="">Any</option>
            <option value="10000">$10K+</option>
            <option value="100000">$100K+</option>
            <option value="500000">$500K+</option>
            <option value="1000000">$1M+</option>
          </select>
        </div>
        <div>
          <label className="label" htmlFor="min_clone_score">Min clone score</label>
          <select id="min_clone_score" name="min_clone_score"
                  defaultValue={searchParams.min_clone_score ?? ''} className="input mt-1">
            <option value="">Any</option>
            <option value="50">50+</option>
            <option value="70">70+ (auto-queued)</option>
            <option value="85">85+</option>
          </select>
        </div>
        <div className="flex items-end gap-2">
          <select name="sort_by" defaultValue={searchParams.sort_by ?? 'clone_score'}
                  className="input" aria-label="Sort by">
            <option value="clone_score">Clone score</option>
            <option value="revenue">Revenue</option>
            <option value="downloads">Downloads</option>
            <option value="trend_score">Trend</option>
            <option value="rating">Rating</option>
          </select>
          <button className="btn-primary" type="submit">Apply</button>
        </div>
      </form>

      {result.items.length === 0 ? (
        <EmptyState
          title="No apps match these filters"
          hint="Run a discovery scan, or relax the filters above."
        />
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {result.items.map((app) => (
              <Link key={app.id} href={`/discover/${app.id}`}
                    className="card transition-colors hover:border-brand/50">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="truncate font-medium">{app.name}</div>
                    <div className="truncate text-xs text-muted">{app.developer}</div>
                  </div>
                  <ScorePill score={app.clone_potential_score} />
                </div>

                <p className="mt-3 line-clamp-2 text-sm text-muted">
                  {app.problem_solved ?? app.description}
                </p>

                <dl className="mt-4 grid grid-cols-3 gap-2 border-t border-edge pt-3 text-center">
                  <div>
                    <dt className="text-[10px] uppercase text-muted">Revenue</dt>
                    <dd className="text-sm font-medium">{fmtMoney(app.last_month_revenue)}</dd>
                  </div>
                  <div>
                    <dt className="text-[10px] uppercase text-muted">Installs</dt>
                    <dd className="text-sm font-medium">{fmtCount(app.total_downloads)}</dd>
                  </div>
                  <div>
                    <dt className="text-[10px] uppercase text-muted">Rating</dt>
                    <dd className="text-sm font-medium">{app.rating?.toFixed(1) ?? '—'}</dd>
                  </div>
                </dl>
              </Link>
            ))}
          </div>

          {pages > 1 && (
            <nav className="flex items-center justify-center gap-2" aria-label="Pagination">
              {page > 1 && (
                <Link className="btn-ghost"
                      href={`/discover?${new URLSearchParams({ ...searchParams, page: String(page - 1) })}`}>
                  Previous
                </Link>
              )}
              <span className="text-sm text-muted">Page {page} of {pages}</span>
              {page < pages && (
                <Link className="btn-ghost"
                      href={`/discover?${new URLSearchParams({ ...searchParams, page: String(page + 1) })}`}>
                  Next
                </Link>
              )}
            </nav>
          )}
        </>
      )}
    </div>
  );
}
