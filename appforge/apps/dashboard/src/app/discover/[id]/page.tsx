import Link from 'next/link';
import { notFound } from 'next/navigation';

import { AnalyzeButton, CloneButton } from '@/components/actions-client';
import { ScorePill, SectionTitle, SeverityPill, fmtCount, fmtMoney } from '@/components/ui';
import { api } from '@/lib/api';

export const dynamic = 'force-dynamic';

const SCORE_LABELS: Record<string, string> = {
  revenue_potential: 'Revenue potential (25)',
  growth_velocity: 'Growth velocity (20)',
  improvement_opportunity: 'Improvement opportunity (25)',
  market_competition: 'Market competition (15)',
  technical_feasibility: 'Technical feasibility (15)',
};

export default async function AppDetailPage({ params }: { params: { id: string } }) {
  let app;
  try {
    app = await api.app(Number(params.id));
  } catch {
    notFound();
  }

  const analysis = app.analysis;
  const review = analysis?.review_analysis;
  const technical = analysis?.technical_assessment;
  const competitive = analysis?.competitive_analysis;
  const breakdown = app.clone_score_breakdown?.breakdown ?? {};

  return (
    <div className="space-y-8">
      <div>
        <Link href="/discover" className="text-sm text-muted hover:text-ink">
          &larr; Back to discover
        </Link>
        <div className="mt-3 flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">{app.name}</h1>
            <p className="mt-1 text-sm text-muted">
              {app.developer} · {app.category} · {app.package_name}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <div className="text-right">
              <div className="label">Clone score</div>
              <div className="mt-1"><ScorePill score={app.clone_potential_score} /></div>
            </div>
            <AnalyzeButton appId={app.id} />
            <CloneButton appId={app.id} disabled={app.status === 'cloning'} />
          </div>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <div className="card">
          <div className="label">Monthly revenue</div>
          <div className="stat mt-2">{fmtMoney(app.last_month_revenue)}</div>
        </div>
        <div className="card">
          <div className="label">Total installs</div>
          <div className="stat mt-2">{fmtCount(app.total_downloads)}</div>
        </div>
        <div className="card">
          <div className="label">Rating</div>
          <div className="stat mt-2">{app.rating?.toFixed(1) ?? '—'}</div>
          <div className="mt-1 text-xs text-muted">{fmtCount(app.total_reviews)} reviews</div>
        </div>
        <div className="card">
          <div className="label">Monetization</div>
          <div className="mt-2 text-lg font-medium">
            {app.monetization_model?.replace(/_/g, ' ') ?? '—'}
          </div>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="card lg:col-span-2">
          <SectionTitle>Problem solved</SectionTitle>
          <p className="text-sm leading-relaxed text-muted">
            {app.problem_solved ?? app.description ?? 'No description captured.'}
          </p>
          {app.key_features && app.key_features.length > 0 && (
            <>
              <h3 className="mt-6 text-sm font-semibold">Key features</h3>
              <ul className="mt-2 flex flex-wrap gap-2">
                {app.key_features.map((f) => (
                  <li key={f} className="pill bg-panel2 text-muted">{f}</li>
                ))}
              </ul>
            </>
          )}
        </div>

        <div className="card">
          <SectionTitle>Score breakdown</SectionTitle>
          <dl className="space-y-3">
            {Object.entries(breakdown).map(([key, value]) => (
              <div key={key}>
                <div className="flex justify-between text-xs">
                  <dt className="text-muted">{SCORE_LABELS[key] ?? key}</dt>
                  <dd className="font-medium">{value}</dd>
                </div>
              </div>
            ))}
          </dl>
          {analysis?.recommendation && (
            <div className="mt-5 rounded-lg border border-edge bg-panel2 p-3">
              <div className="label">Recommendation</div>
              <div className="mt-1 font-semibold">{analysis.recommendation}</div>
              <p className="mt-1 text-xs text-muted">{analysis.recommendation_reason}</p>
            </div>
          )}
        </div>
      </div>

      {review && (
        <div className="grid gap-6 lg:grid-cols-2">
          <div className="card">
            <SectionTitle>What users love</SectionTitle>
            <ul className="space-y-3">
              {(review.what_users_love ?? []).map((item: any) => (
                <li key={item.theme} className="border-l-2 border-ok pl-3">
                  <div className="flex justify-between text-sm">
                    <span className="font-medium">{item.theme}</span>
                    <span className="text-muted">{item.frequency}</span>
                  </div>
                  <p className="mt-1 text-xs italic text-muted">&ldquo;{item.example}&rdquo;</p>
                </li>
              ))}
            </ul>
            <p className="mt-4 text-xs text-muted">
              {review.sentiment_breakdown?.positive} positive of{' '}
              {review.total_reviews_analyzed} reviews analyzed
            </p>
          </div>

          <div className="card">
            <SectionTitle>Issues we would fix</SectionTitle>
            <ul className="space-y-4">
              {(review.identified_issues ?? []).slice(0, 6).map((issue: any) => (
                <li key={issue.issue} className="border-l-2 border-bad pl-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-medium">{issue.issue}</span>
                    <SeverityPill severity={issue.severity} />
                    <span className="text-xs text-muted">{issue.frequency} reports</span>
                  </div>
                  <p className="mt-1 text-xs text-muted">
                    <span className="text-ink">Cause:</span> {issue.root_cause_hypothesis}
                  </p>
                  <p className="mt-1 text-xs text-ok">
                    <span className="text-ink">Fix:</span> {issue.suggested_fix}
                  </p>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {review?.feature_requests?.length > 0 && (
        <div className="card">
          <SectionTitle>Most requested missing features</SectionTitle>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {review.feature_requests.map((f: any) => (
              <div key={f.feature} className="rounded-lg border border-edge bg-panel2 p-3">
                <div className="flex justify-between text-sm font-medium">
                  <span>{f.feature}</span>
                  <span className="text-muted">{f.frequency}</span>
                </div>
                <p className="mt-1 text-xs text-muted">{f.description}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        {technical && (
          <div className="card">
            <SectionTitle>Technical assessment</SectionTitle>
            <dl className="space-y-2 text-sm">
              <div className="flex justify-between">
                <dt className="text-muted">Complexity</dt>
                <dd className="font-medium">{technical.estimated_complexity}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-muted">Estimated build</dt>
                <dd className="font-medium">{technical.development_time_estimate}</dd>
              </div>
            </dl>
            {technical.potential_blockers?.length > 0 && (
              <>
                <h3 className="mt-4 text-sm font-semibold">Blockers</h3>
                <ul className="mt-2 space-y-1">
                  {technical.potential_blockers.map((b: string) => (
                    <li key={b} className="text-xs text-warn">· {b}</li>
                  ))}
                </ul>
              </>
            )}
            {technical.recommended_mvp_scope?.length > 0 && (
              <>
                <h3 className="mt-4 text-sm font-semibold">Recommended MVP scope</h3>
                <ul className="mt-2 flex flex-wrap gap-2">
                  {technical.recommended_mvp_scope.map((s: string) => (
                    <li key={s} className="pill bg-panel2 text-muted">{s}</li>
                  ))}
                </ul>
              </>
            )}
          </div>
        )}

        {competitive && (
          <div className="card">
            <SectionTitle>Market gaps</SectionTitle>
            <ul className="space-y-2">
              {(competitive.market_gaps ?? []).map((gap: string) => (
                <li key={gap} className="text-sm text-muted">· {gap}</li>
              ))}
            </ul>
            {competitive.direct_competitors?.length > 0 && (
              <>
                <h3 className="mt-4 text-sm font-semibold">Direct competitors</h3>
                <ul className="mt-2 space-y-2">
                  {competitive.direct_competitors.map((c: any) => (
                    <li key={c.name} className="flex justify-between text-sm">
                      <span>{c.name}</span>
                      <span className="text-muted">
                        {fmtCount(c.downloads)} · {c.rating?.toFixed?.(1) ?? '—'}★
                      </span>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </div>
        )}
      </div>

      {analysis?.clone_name_ideas && analysis.clone_name_ideas.length > 0 && (
        <div className="card">
          <SectionTitle>Suggested clone names</SectionTitle>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {analysis.clone_name_ideas.map((n) => (
              <div key={n.name} className="rounded-lg border border-edge bg-panel2 p-3">
                <div className="font-medium">{n.name}</div>
                <div className="mt-1 text-xs text-brand">{n.tagline}</div>
                <p className="mt-2 text-xs text-muted">{n.rationale}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
