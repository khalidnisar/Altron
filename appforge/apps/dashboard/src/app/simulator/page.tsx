import Link from 'next/link';

import { ApprovalControls } from '@/components/actions-client';
import { EmptyState, SectionTitle, StagePill } from '@/components/ui';
import { api, safe, type Project } from '@/lib/api';

export const dynamic = 'force-dynamic';

export default async function SimulatorPage({
  searchParams,
}: {
  searchParams: { project?: string };
}) {
  const projects = await safe(api.projects(), [] as Project[]);
  const testable = projects.filter((p) => p.simulator_url);

  const selectedId = searchParams.project ? Number(searchParams.project) : testable[0]?.id;
  const selected = selectedId ? await safe(api.project(selectedId), null) : null;

  if (testable.length === 0) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold tracking-tight">Simulator</h1>
        <EmptyState
          title="No builds ready to test"
          hint="A build becomes testable once the Testing Agent passes all automated gates."
          action={{ href: '/pipeline', label: 'View pipeline' }}
        />
      </div>
    );
  }

  const tests = selected?.test_results;
  const isLocal = selected?.simulator_url?.startsWith('/simulator/local');

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Simulator</h1>
          <p className="mt-1 text-sm text-muted">
            Test the real build before approving it for the Play Store
          </p>
        </div>
        <form method="get" className="flex items-end gap-2">
          <div>
            <label className="label" htmlFor="project">Build</label>
            <select id="project" name="project" defaultValue={String(selectedId)}
                    className="input mt-1">
              {testable.map((p) => (
                <option key={p.id} value={p.id}>{p.clone_name}</option>
              ))}
            </select>
          </div>
          <button className="btn-ghost" type="submit">Load</button>
        </form>
      </div>

      {selected && (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,380px)_1fr]">
          <div className="card">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="font-semibold">{selected.clone_name}</h2>
              <StagePill stage={selected.pipeline_stage} />
            </div>

            {/* Device frame */}
            <div className="mx-auto w-full max-w-[300px]">
              <div className="rounded-[2rem] border-4 border-edge bg-black p-2 shadow-2xl">
                <div className="relative aspect-[9/19.5] overflow-hidden rounded-[1.5rem]
                                bg-panel2">
                  {isLocal ? (
                    <div className="flex h-full flex-col items-center justify-center gap-3 p-6
                                    text-center">
                      <div
                        className="flex h-16 w-16 items-center justify-center rounded-2xl
                                   text-2xl font-bold text-white"
                        style={{ background: selected.design_assets?.palette?.primary ?? '#5C7CFA' }}
                      >
                        {selected.clone_name[0]}
                      </div>
                      <div className="text-sm font-medium">{selected.clone_name}</div>
                      <div className="text-xs text-muted">{selected.tagline}</div>
                      <p className="mt-4 text-[11px] leading-relaxed text-muted">
                        Live device streaming requires BrowserStack or Genymotion
                        credentials. Add them in Settings to stream the real APK here.
                      </p>
                    </div>
                  ) : (
                    <iframe
                      src={selected.simulator_url ?? ''}
                      title={`${selected.clone_name} simulator`}
                      className="h-full w-full border-0"
                      allow="autoplay; fullscreen"
                    />
                  )}
                </div>
              </div>
            </div>
          </div>

          <div className="space-y-6">
            {tests && (
              <div className="card">
                <SectionTitle>Automated results</SectionTitle>
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                  <Metric label="Unit" value={`${tests.unit?.passed}/${tests.unit?.total}`} ok />
                  <Metric label="Integration"
                          value={`${tests.integration?.passed}/${tests.integration?.total}`} ok />
                  <Metric label="E2E" value={`${tests.e2e?.passed}/${tests.e2e?.total}`} ok />
                  <Metric label="Crash-free"
                          value={`${tests.performance?.crash_free_rate}%`} ok />
                  <Metric label="Cold start"
                          value={`${tests.performance?.cold_start_seconds}s`}
                          ok={tests.performance?.cold_start_seconds < 3} />
                  <Metric label="Peak memory"
                          value={`${tests.performance?.peak_memory_mb}MB`}
                          ok={tests.performance?.peak_memory_mb < 300} />
                  <Metric label="Coverage" value={`${tests.coverage}%`}
                          ok={tests.coverage > 80} />
                  <Metric label="APK size"
                          value={`${tests.performance?.apk_size_mb}MB`} ok />
                </div>
                <p className="mt-4 text-xs text-muted">
                  Verified on {tests.devices?.length ?? 0} device configurations across{' '}
                  {tests.conditions_tested?.length ?? 0} conditions.
                </p>
              </div>
            )}

            {selected.patched_issues && selected.patched_issues.length > 0 && (
              <div className="card">
                <SectionTitle>Fixes to verify</SectionTitle>
                <ul className="space-y-2">
                  {selected.patched_issues.map((p: any, i: number) => (
                    <li key={i} className="flex items-start gap-2 text-sm">
                      <span className="text-ok">✓</span>
                      <div>
                        <div className="font-medium">{p.original}</div>
                        <div className="text-xs text-muted">{p.fix}</div>
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {selected.pipeline_stage === 'simulation' ? (
              <div className="card border-warn/40">
                <SectionTitle>Your decision</SectionTitle>
                <ApprovalControls projectId={selected.id} />
              </div>
            ) : (
              <div className="card">
                <p className="text-sm text-muted">
                  This build is at the{' '}
                  <span className="text-ink">{selected.pipeline_stage.replace(/_/g, ' ')}</span>{' '}
                  stage, so no approval is required here.{' '}
                  <Link href={`/pipeline/${selected.id}`} className="text-brand">
                    View project
                  </Link>
                </p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function Metric({ label, value, ok }: { label: string; value: string; ok?: boolean }) {
  return (
    <div className="rounded-lg bg-panel2 p-3">
      <div className="label">{label}</div>
      <div className={`mt-1 font-medium ${ok ? 'text-ok' : 'text-ink'}`}>{value}</div>
    </div>
  );
}
