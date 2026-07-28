import { RunPipelineButton, SeedButton } from '@/components/actions-client';
import { SectionTitle } from '@/components/ui';
import { api, safe, type AgentStatus } from '@/lib/api';

export const dynamic = 'force-dynamic';

const PROVIDER_KEYS = [
  { env: 'APPFORGE_OPENAI_API_KEY', label: 'OpenAI', purpose: 'Naming, listing copy, analysis summaries' },
  { env: 'APPFORGE_ANTHROPIC_API_KEY', label: 'Anthropic', purpose: 'Alternative LLM provider' },
  { env: 'APPFORGE_SENSORTOWER_API_KEY', label: 'Sensor Tower', purpose: 'Revenue and download estimates' },
  { env: 'APPFORGE_BROWSERSTACK_USER', label: 'BrowserStack', purpose: 'Real-device tests and live simulator' },
  { env: 'APPFORGE_GENYMOTION_API_KEY', label: 'Genymotion', purpose: 'Cloud Android emulator' },
  { env: 'APPFORGE_PLAY_CONSOLE_SERVICE_ACCOUNT_JSON', label: 'Play Console', purpose: 'Automated store submission' },
  { env: 'APPFORGE_ADMOB_APP_ID', label: 'AdMob', purpose: 'Ad mediation revenue' },
  { env: 'APPFORGE_REVENUECAT_API_KEY', label: 'RevenueCat', purpose: 'Subscription management' },
  { env: 'APPFORGE_SENTRY_DSN', label: 'Sentry', purpose: 'Crash reporting for published apps' },
];

export default async function SettingsPage() {
  const [health, agents] = await Promise.all([
    safe(api.health(), { status: 'unreachable', offline_mode: true }),
    safe(api.agents(), { agents: [] } as AgentStatus),
  ]);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
        <p className="mt-1 text-sm text-muted">Platform status, agents, and integrations</p>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <div className="card">
          <div className="label">API</div>
          <div className={`stat mt-2 ${health.status === 'ok' ? 'text-ok' : 'text-bad'}`}>
            {health.status}
          </div>
        </div>
        <div className="card">
          <div className="label">Mode</div>
          <div className="stat mt-2">{health.offline_mode ? 'Offline' : 'Live'}</div>
          <p className="mt-1 text-xs text-muted">
            {health.offline_mode
              ? 'Deterministic providers, no external API calls'
              : 'Connected to external providers'}
          </p>
        </div>
        <div className="card">
          <div className="label">Agents</div>
          <div className="stat mt-2">{agents.agents.length}</div>
        </div>
      </div>

      <div className="card">
        <SectionTitle>Get started</SectionTitle>
        <p className="mb-4 text-sm text-muted">
          Seeding registers all 20 niches, runs discovery and analysis, then walks a few
          projects through design, build, test, publish, and monetization so every page
          has real data.
        </p>
        <div className="flex flex-wrap gap-3">
          <SeedButton />
          <RunPipelineButton limit={50} />
        </div>
      </div>

      <div>
        <SectionTitle>Agent status</SectionTitle>
        <div className="card overflow-x-auto p-0">
          <table className="w-full">
            <caption className="sr-only">Task counts per agent</caption>
            <thead className="border-b border-edge">
              <tr>
                <th scope="col" className="th">Agent</th>
                <th scope="col" className="th text-right">Pending</th>
                <th scope="col" className="th text-right">Completed</th>
                <th scope="col" className="th text-right">Failed</th>
                <th scope="col" className="th text-right">Health</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-edge">
              {agents.agents.map((a) => (
                <tr key={a.agent}>
                  <td className="td font-medium capitalize">{a.agent}</td>
                  <td className="td text-right text-muted">{a.pending}</td>
                  <td className="td text-right text-muted">{a.completed}</td>
                  <td className={`td text-right ${a.failed > 0 ? 'text-bad' : 'text-muted'}`}>
                    {a.failed}
                  </td>
                  <td className="td text-right">
                    <span className={a.healthy ? 'text-ok' : 'text-bad'}>
                      {a.healthy ? '● healthy' : '● errors'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div>
        <SectionTitle>Integrations</SectionTitle>
        <p className="mb-4 text-sm text-muted">
          Set these as environment variables in <code className="text-brand">.env</code>.
          Any provider left blank falls back to a deterministic offline stub, so the
          platform stays fully runnable without paid keys.
        </p>
        <div className="card overflow-x-auto p-0">
          <table className="w-full">
            <caption className="sr-only">Provider configuration</caption>
            <thead className="border-b border-edge">
              <tr>
                <th scope="col" className="th">Provider</th>
                <th scope="col" className="th">Environment variable</th>
                <th scope="col" className="th">Used for</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-edge">
              {PROVIDER_KEYS.map((k) => (
                <tr key={k.env}>
                  <td className="td font-medium">{k.label}</td>
                  <td className="td"><code className="text-xs text-brand">{k.env}</code></td>
                  <td className="td text-muted">{k.purpose}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card border-warn/30">
        <SectionTitle>Legal guardrails</SectionTitle>
        <ul className="space-y-2 text-sm text-muted">
          <li>· All app code is generated from feature specifications. No source is copied.</li>
          <li>· Every clone receives an original name, logo, and color palette.</li>
          <li>· Generated apps request a minimal permission set and ship a data-safety declaration.</li>
          <li>· Apps from major technology companies are excluded from discovery.</li>
          <li>· Human approval is required before any Play Store submission.</li>
        </ul>
      </div>
    </div>
  );
}
