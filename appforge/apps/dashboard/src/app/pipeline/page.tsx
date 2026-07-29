import Link from 'next/link';

import { RunPipelineButton } from '@/components/actions-client';
import { EmptyState, Progress, SectionTitle, fmtMoney } from '@/components/ui';
import { api, safe, type Project } from '@/lib/api';

export const dynamic = 'force-dynamic';

/** Kanban columns mirroring the blueprint pipeline stages. */
const COLUMNS: { stage: string; label: string; gate?: boolean }[] = [
  { stage: 'awaiting_approval', label: 'Awaiting approval', gate: true },
  { stage: 'design', label: 'Designing' },
  { stage: 'development', label: 'Building' },
  { stage: 'testing', label: 'Testing' },
  { stage: 'simulation', label: 'Simulation', gate: true },
  { stage: 'publishing', label: 'Publishing' },
  { stage: 'monetization', label: 'Monetizing' },
  { stage: 'live', label: 'Live' },
];

export default async function PipelinePage() {
  const projects = await safe(api.projects(), [] as Project[]);

  if (projects.length === 0) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold tracking-tight">Pipeline</h1>
        <EmptyState
          title="No clone projects yet"
          hint="Projects are created when the Analysis Agent recommends a discovered app."
          action={{ href: '/discover', label: 'Browse discovered apps' }}
        />
      </div>
    );
  }

  const byStage = (stage: string) => projects.filter((p) => p.pipeline_stage === stage);
  const gated = projects.filter(
    (p) => ['awaiting_approval', 'simulation'].includes(p.pipeline_stage),
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Pipeline</h1>
          <p className="mt-1 text-sm text-muted">
            {projects.length} projects · {gated.length} need your decision
          </p>
        </div>
        <RunPipelineButton limit={40} />
      </div>

      {gated.length > 0 && (
        <div className="rounded-xl border border-warn/30 bg-warn/5 p-4">
          <SectionTitle>Waiting on you</SectionTitle>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {gated.map((p) => (
              <Link key={p.id} href={`/pipeline/${p.id}`}
                    className="rounded-lg border border-edge bg-panel p-3 hover:border-warn/50">
                <div className="font-medium">{p.clone_name}</div>
                {p.source_app_name && (
                  <div className="text-[11px] text-muted">from {p.source_app_name}</div>
                )}
                <div className="mt-1 text-xs text-muted">
                  {p.pipeline_stage === 'simulation'
                    ? 'Test in simulator, then approve for publishing'
                    : 'Approve to begin design and build'}
                </div>
              </Link>
            ))}
          </div>
        </div>
      )}

      <div className="grid gap-4 overflow-x-auto md:grid-cols-2 xl:grid-cols-4">
        {COLUMNS.map((col) => {
          const items = byStage(col.stage);
          return (
            <section key={col.stage} className="min-w-[220px]">
              <div className="mb-2 flex items-center justify-between px-1">
                <h2 className="text-sm font-semibold">
                  {col.label}
                  {col.gate && <span className="ml-1 text-warn" title="Human gate">●</span>}
                </h2>
                <span className="text-xs text-muted">{items.length}</span>
              </div>
              <div className="space-y-2">
                {items.length === 0 && (
                  <div className="rounded-lg border border-dashed border-edge p-4
                                  text-center text-xs text-muted">
                    Empty
                  </div>
                )}
                {items.map((p) => (
                  <Link key={p.id} href={`/pipeline/${p.id}`}
                        className="block rounded-lg border border-edge bg-panel p-3
                                   transition-colors hover:border-brand/50">
                    <div className="truncate text-sm font-medium">{p.clone_name}</div>
                    {p.source_app_name && (
                      <div className="mt-0.5 truncate text-[11px] text-muted">
                        from {p.source_app_name}
                      </div>
                    )}
                    <div className="mt-1 truncate text-xs text-muted">{p.tagline}</div>
                    <div className="mt-2"><Progress value={p.progress} /></div>
                    <div className="mt-2 flex justify-between text-xs text-muted">
                      <span>{p.progress}%</span>
                      {p.monthly_revenue > 0 && <span>{fmtMoney(p.monthly_revenue)}/mo</span>}
                    </div>
                    {p.blocked_reason && (
                      <p className="mt-2 line-clamp-2 text-xs text-bad">{p.blocked_reason}</p>
                    )}
                  </Link>
                ))}
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}
