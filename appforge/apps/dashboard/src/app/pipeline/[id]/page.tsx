import Link from 'next/link';
import { notFound } from 'next/navigation';

import { ApprovalControls } from '@/components/actions-client';
import {
  Progress, SectionTitle, SeverityPill, StagePill, fmtMoney,
} from '@/components/ui';
import { api, safe } from '@/lib/api';

export const dynamic = 'force-dynamic';

export default async function ProjectDetailPage({ params }: { params: { id: string } }) {
  const id = Number(params.id);
  let project;
  try {
    project = await api.project(id);
  } catch {
    notFound();
  }

  const pipeline = await safe(api.projectPipeline(id), null);
  const tests = project.test_results;
  const design = project.design_assets;
  const money = project.monetization_config;
  const listing = project.store_listing;
  const atGate = ['awaiting_approval', 'simulation'].includes(project.pipeline_stage);

  return (
    <div className="space-y-8">
      <div>
        <Link href="/pipeline" className="text-sm text-muted hover:text-ink">
          &larr; Back to pipeline
        </Link>
        <div className="mt-3 flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">{project.clone_name}</h1>
            <p className="mt-1 text-sm text-muted">{project.tagline}</p>
            <p className="mt-1 text-xs text-muted">{project.clone_package_name}</p>
          </div>
          <div className="flex items-center gap-3">
            <StagePill stage={project.pipeline_stage} />
            {project.play_store_url && (
              <a href={project.play_store_url} target="_blank" rel="noreferrer"
                 className="btn-ghost">Play Store</a>
            )}
          </div>
        </div>
        <div className="mt-4"><Progress value={project.progress} /></div>
      </div>

      {pipeline && (
        <div className="card">
          <SectionTitle>Stages</SectionTitle>
          <ol className="flex flex-wrap gap-2">
            {pipeline.stages.map((s) => (
              <li key={s.stage}
                  className={`pill ${
                    s.state === 'complete' ? 'bg-ok/15 text-ok'
                      : s.state === 'active' ? 'bg-brand/15 text-brand'
                        : 'bg-panel2 text-muted'
                  }`}>
                {s.stage.replace(/_/g, ' ')}
                {s.has_gate && (
                  <span
                    className={`ml-1 ${s.approved ? 'text-ok' : 'text-warn'}`}
                    title={s.approved ? 'Human gate: approved' : 'Human gate: awaiting decision'}
                  >
                    {s.approved ? '✓' : '●'}
                  </span>
                )}
              </li>
            ))}
          </ol>
          <p className="mt-3 text-xs text-muted">
            ● marks a human gate. Both gates must be approved independently; an
            approval at one gate never satisfies the other.
          </p>
        </div>
      )}

      {atGate && (
        <div className="rounded-xl border border-warn/40 bg-warn/5 p-5">
          <SectionTitle>
            {project.pipeline_stage === 'simulation'
              ? 'Human approval: test then publish'
              : 'Human approval: begin design and build'}
          </SectionTitle>
          <div className="grid gap-4 lg:grid-cols-2">
            <div>
              <p className="text-sm text-muted">
                {project.pipeline_stage === 'simulation'
                  ? 'All automated gates passed. Try the build in the simulator before approving it for Play Store submission.'
                  : 'The Analysis Agent recommends this clone. Approving queues the Design Agent.'}
              </p>
              {project.simulator_url && (
                <Link href={`/simulator?project=${project.id}`} className="btn-ghost mt-4">
                  Open in simulator
                </Link>
              )}
            </div>
            <ApprovalControls projectId={project.id} />
          </div>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        {project.patched_issues && project.patched_issues.length > 0 && (
          <div className="card">
            <SectionTitle>Patched issues</SectionTitle>
            <ul className="space-y-3">
              {project.patched_issues.map((p: any, i: number) => (
                <li key={i} className="border-l-2 border-ok pl-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-medium">{p.original}</span>
                    <SeverityPill severity={p.severity ?? 'medium'} />
                    <span className={`pill ${
                      p.status === 'implemented' ? 'bg-ok/15 text-ok' : 'bg-panel2 text-muted'
                    }`}>{p.status}</span>
                  </div>
                  <p className="mt-1 text-xs text-muted">{p.fix}</p>
                  {p.file && <code className="mt-1 block text-[11px] text-brand">{p.file}</code>}
                </li>
              ))}
            </ul>
          </div>
        )}

        {tests && (
          <div className="card">
            <SectionTitle>Test results</SectionTitle>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div className="rounded-lg bg-panel2 p-3">
                <div className="label">Unit</div>
                <div className="mt-1 font-medium">
                  {tests.unit?.passed}/{tests.unit?.total}
                </div>
              </div>
              <div className="rounded-lg bg-panel2 p-3">
                <div className="label">E2E</div>
                <div className="mt-1 font-medium">
                  {tests.e2e?.passed}/{tests.e2e?.total}
                </div>
              </div>
              <div className="rounded-lg bg-panel2 p-3">
                <div className="label">Coverage</div>
                <div className="mt-1 font-medium">{tests.coverage}%</div>
              </div>
              <div className="rounded-lg bg-panel2 p-3">
                <div className="label">Cold start</div>
                <div className="mt-1 font-medium">
                  {tests.performance?.cold_start_seconds}s
                </div>
              </div>
            </div>
            <ul className="mt-4 space-y-1.5">
              {(tests.criteria?.must_pass ?? []).map((c: any) => (
                <li key={c.criteria} className="flex items-center justify-between text-xs">
                  <span className="text-muted">{c.criteria}</span>
                  <span className={c.passed ? 'text-ok' : 'text-bad'}>
                    {c.passed ? '✓' : '✗'} {c.actual}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        {design?.palette && (
          <div className="card">
            <SectionTitle>Brand</SectionTitle>
            <div className="flex gap-2">
              {['primary', 'secondary', 'accent'].map((k) => (
                <div key={k} className="flex-1">
                  <div className="h-12 rounded-lg border border-edge"
                       style={{ background: design.palette[k] }} />
                  <div className="mt-1 text-[10px] text-muted">{design.palette[k]}</div>
                </div>
              ))}
            </div>
            {design.accessibility && (
              <p className="mt-4 text-xs text-muted">
                WCAG {design.accessibility.wcag_target} contrast{' '}
                <span className={design.accessibility.passes ? 'text-ok' : 'text-bad'}>
                  {design.accessibility.body_contrast_ratio}:1
                </span>
              </p>
            )}
          </div>
        )}

        {money && (
          <div className="card">
            <SectionTitle>Monetization</SectionTitle>
            <dl className="space-y-2 text-sm">
              <div className="flex justify-between">
                <dt className="text-muted">Model</dt>
                <dd className="font-medium">{money.model?.replace(/_/g, ' ')}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-muted">Price</dt>
                <dd className="font-medium">${money.headline_price}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-muted">Value score</dt>
                <dd className="font-medium">{money.value_score}/100</dd>
              </div>
              {project.ltv != null && (
                <div className="flex justify-between">
                  <dt className="text-muted">Est. LTV</dt>
                  <dd className="font-medium">${project.ltv}</dd>
                </div>
              )}
            </dl>
          </div>
        )}

        {listing && (
          <div className="card">
            <SectionTitle>Store listing</SectionTitle>
            <div className="space-y-2 text-sm">
              <div>
                <div className="label">Title ({listing.character_counts?.title}/30)</div>
                <div className="mt-1 font-medium">{listing.title}</div>
              </div>
              <div>
                <div className="label">Short ({listing.character_counts?.short}/80)</div>
                <p className="mt-1 text-muted">{listing.short_description}</p>
              </div>
              <div>
                <div className="label">Category</div>
                <div className="mt-1 text-muted">{listing.category}</div>
              </div>
            </div>
          </div>
        )}
      </div>

      {project.remediation_history && project.remediation_history.length > 0 && (
        <div className="card border-warn/30">
          <SectionTitle>Fix attempts</SectionTitle>
          <p className="mb-3 text-sm text-muted">
            Automated remediation triggered by failed tests, a crash spike, or a
            reviewer rejection.
          </p>
          <ol className="space-y-3">
            {project.remediation_history.map((r) => (
              <li key={r.attempt} className="border-l-2 border-warn pl-3">
                <div className="flex items-center gap-2 text-sm">
                  <span className="font-medium">Attempt {r.attempt}</span>
                  <span className="pill bg-panel2 text-muted">{r.source}</span>
                  <span className="text-xs text-muted">
                    {r.requested_at?.slice(0, 19).replace('T', ' ')}
                  </span>
                </div>
                <ul className="mt-1 space-y-0.5">
                  {r.reasons.map((reason) => (
                    <li key={reason} className="text-xs text-muted">· {reason}</li>
                  ))}
                </ul>
              </li>
            ))}
          </ol>
        </div>
      )}

      {project.build_logs && project.build_logs.length > 0 && (
        <div className="card">
          <SectionTitle>Build log</SectionTitle>
          <ol className="space-y-1.5 font-mono text-xs">
            {project.build_logs.map((log, i) => (
              <li key={i} className="flex gap-3">
                <span className="text-muted">{log.timestamp?.slice(11, 19)}</span>
                <span className={log.status === 'success' ? 'text-ok' : 'text-bad'}>
                  [{log.stage}]
                </span>
                <span className="text-muted">{log.message}</span>
              </li>
            ))}
          </ol>
        </div>
      )}

      {project.repository_url && (
        <div className="card">
          <SectionTitle>Generated source</SectionTitle>
          <p className="text-sm text-muted">
            Flutter project generated from the feature specification. No code was copied
            from the source app.
          </p>
          <code className="mt-2 block break-all text-xs text-brand">
            {project.repository_url}
          </code>
        </div>
      )}
    </div>
  );
}
