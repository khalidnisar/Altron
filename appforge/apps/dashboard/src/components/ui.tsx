import Link from 'next/link';

export function StatCard({
  label, value, sub, tone = 'default',
}: {
  label: string; value: string | number; sub?: string;
  tone?: 'default' | 'ok' | 'warn' | 'bad';
}) {
  const toneClass = {
    default: 'text-ink', ok: 'text-ok', warn: 'text-warn', bad: 'text-bad',
  }[tone];
  return (
    <div className="card">
      <div className="label">{label}</div>
      <div className={`stat mt-2 ${toneClass}`}>{value}</div>
      {sub && <div className="mt-1 text-xs text-muted">{sub}</div>}
    </div>
  );
}

export function ScorePill({ score }: { score: number | null | undefined }) {
  if (score == null) return <span className="pill bg-panel2 text-muted">—</span>;
  const tone =
    score >= 80 ? 'bg-ok/15 text-ok'
      : score >= 70 ? 'bg-brand/15 text-brand'
        : score >= 50 ? 'bg-warn/15 text-warn'
          : 'bg-panel2 text-muted';
  return <span className={`pill ${tone}`}>{score}</span>;
}

const SEVERITY_TONE: Record<string, string> = {
  critical: 'bg-bad/15 text-bad',
  high: 'bg-bad/15 text-bad',
  medium: 'bg-warn/15 text-warn',
  low: 'bg-panel2 text-muted',
};

export function SeverityPill({ severity }: { severity: string }) {
  return (
    <span className={`pill ${SEVERITY_TONE[severity] ?? 'bg-panel2 text-muted'}`}>
      {severity}
    </span>
  );
}

const STAGE_TONE: Record<string, string> = {
  live: 'bg-ok/15 text-ok',
  awaiting_approval: 'bg-warn/15 text-warn',
  simulation: 'bg-warn/15 text-warn',
  rejected: 'bg-bad/15 text-bad',
  sunset: 'bg-bad/15 text-bad',
};

export function StagePill({ stage }: { stage: string }) {
  return (
    <span className={`pill ${STAGE_TONE[stage] ?? 'bg-brand/15 text-brand'}`}>
      {stage.replace(/_/g, ' ')}
    </span>
  );
}

export function Progress({ value }: { value: number }) {
  const clamped = Math.max(0, Math.min(100, value));
  return (
    <div
      className="h-1.5 w-full overflow-hidden rounded-full bg-panel2"
      role="progressbar"
      aria-valuenow={clamped}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div className="h-full rounded-full bg-brand transition-all" style={{ width: `${clamped}%` }} />
    </div>
  );
}

export function EmptyState({ title, hint, action }: {
  title: string; hint?: string; action?: { href: string; label: string };
}) {
  return (
    <div className="card flex flex-col items-center justify-center py-14 text-center">
      <div className="text-base font-medium">{title}</div>
      {hint && <p className="mt-2 max-w-md text-sm text-muted">{hint}</p>}
      {action && (
        <Link href={action.href} className="btn-primary mt-5">{action.label}</Link>
      )}
    </div>
  );
}

export function SectionTitle({ children, right }: {
  children: React.ReactNode; right?: React.ReactNode;
}) {
  return (
    <div className="mb-4 flex items-center justify-between">
      <h2 className="text-lg font-semibold tracking-tight">{children}</h2>
      {right}
    </div>
  );
}

export function fmtMoney(n: number | null | undefined): string {
  const v = n ?? 0;
  if (Math.abs(v) >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`;
  if (Math.abs(v) >= 1_000) return `$${(v / 1_000).toFixed(1)}K`;
  return `$${v.toFixed(2)}`;
}

export function fmtCount(n: number | null | undefined): string {
  const v = n ?? 0;
  if (v >= 1_000_000_000) return `${(v / 1_000_000_000).toFixed(1)}B`;
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `${(v / 1_000).toFixed(1)}K`;
  return String(v);
}
