import Link from 'next/link';

export default function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center py-24 text-center">
      <h1 className="text-2xl font-semibold">Not found</h1>
      <p className="mt-2 text-sm text-muted">
        That resource does not exist or has been removed.
      </p>
      <Link href="/" className="btn-primary mt-6">Back to dashboard</Link>
    </div>
  );
}
