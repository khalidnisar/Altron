'use client';

export default function Error({ error, reset }: { error: Error; reset: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-24 text-center">
      <h1 className="text-2xl font-semibold">Something went wrong</h1>
      <p className="mt-2 max-w-lg text-sm text-muted">{error.message}</p>
      <button onClick={reset} className="btn-primary mt-6">Try again</button>
    </div>
  );
}
