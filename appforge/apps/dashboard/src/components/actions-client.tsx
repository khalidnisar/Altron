'use client';

import { useRouter } from 'next/navigation';
import { useState, useTransition } from 'react';

import {
  analyzeApp, approveProject, rejectProject, runPipeline, seedPlatform,
  startClone, triggerDiscovery,
} from '@/app/actions';

function useAction() {
  const [pending, start] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();

  const run = (fn: () => Promise<unknown>) => {
    setError(null);
    start(async () => {
      try {
        await fn();
        router.refresh();
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Action failed');
      }
    });
  };
  return { pending, error, run };
}

function ErrorNote({ error }: { error: string | null }) {
  if (!error) return null;
  return <p role="alert" className="mt-2 text-xs text-bad">{error}</p>;
}

export function RunPipelineButton({ limit = 25 }: { limit?: number }) {
  const { pending, error, run } = useAction();
  return (
    <div>
      <button className="btn-ghost" disabled={pending}
              onClick={() => run(() => runPipeline(limit))}>
        {pending ? 'Running…' : 'Run queued tasks'}
      </button>
      <ErrorNote error={error} />
    </div>
  );
}

export function SeedButton() {
  const { pending, error, run } = useAction();
  return (
    <div>
      <button className="btn-primary" disabled={pending}
              onClick={() => run(() => seedPlatform())}>
        {pending ? 'Seeding, this takes a moment…' : 'Seed platform & run demo pipeline'}
      </button>
      <ErrorNote error={error} />
    </div>
  );
}

export function DiscoverButton() {
  const { pending, error, run } = useAction();
  return (
    <div>
      <button className="btn-ghost" disabled={pending}
              onClick={() => run(() => triggerDiscovery())}>
        {pending ? 'Queued…' : 'Scan all niches'}
      </button>
      <ErrorNote error={error} />
    </div>
  );
}

export function CloneButton({ appId, disabled }: { appId: number; disabled?: boolean }) {
  const { pending, error, run } = useAction();
  return (
    <div>
      <button className="btn-primary" disabled={pending || disabled}
              onClick={() => run(() => startClone(appId))}>
        {pending ? 'Creating…' : 'Start clone'}
      </button>
      <ErrorNote error={error} />
    </div>
  );
}

export function AnalyzeButton({ appId }: { appId: number }) {
  const { pending, error, run } = useAction();
  return (
    <div>
      <button className="btn-ghost" disabled={pending}
              onClick={() => run(() => analyzeApp(appId))}>
        {pending ? 'Queued…' : 'Re-run analysis'}
      </button>
      <ErrorNote error={error} />
    </div>
  );
}

/** Approve / reject pair used at every human gate. */
export function ApprovalControls({ projectId, compact = false }: {
  projectId: number; compact?: boolean;
}) {
  const { pending, error, run } = useAction();
  const [feedback, setFeedback] = useState('');

  return (
    <div className={compact ? 'flex flex-col gap-2' : 'space-y-3'}>
      <label className="sr-only" htmlFor={`fb-${projectId}`}>Reviewer feedback</label>
      <textarea
        id={`fb-${projectId}`}
        className="input min-h-[72px]"
        placeholder="Feedback notes (required to reject)"
        value={feedback}
        onChange={(e) => setFeedback(e.target.value)}
      />
      <div className="flex gap-2">
        <button className="btn-primary flex-1" disabled={pending}
                onClick={() => run(() => approveProject(projectId, feedback))}>
          {pending ? 'Working…' : 'Approve'}
        </button>
        <button className="btn-danger flex-1" disabled={pending || !feedback.trim()}
                title={!feedback.trim() ? 'Add feedback to reject' : undefined}
                onClick={() => run(() => rejectProject(projectId, feedback))}>
          Needs changes
        </button>
      </div>
      <ErrorNote error={error} />
    </div>
  );
}
