import type { Metadata } from 'next';
import Link from 'next/link';
import './globals.css';

export const metadata: Metadata = {
  title: 'AppForge AI',
  description: 'Autonomous viral app discovery, cloning, and monetization platform',
};

const NAV = [
  { href: '/', label: 'Dashboard' },
  { href: '/discover', label: 'Discover' },
  { href: '/pipeline', label: 'Pipeline' },
  { href: '/simulator', label: 'Simulator' },
  { href: '/revenue', label: 'Revenue' },
  { href: '/settings', label: 'Settings' },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="flex min-h-screen">
          <aside className="hidden w-60 shrink-0 border-r border-edge bg-panel md:block">
            <div className="flex h-16 items-center gap-2 border-b border-edge px-5">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand
                              text-sm font-bold text-white">
                AF
              </div>
              <span className="font-semibold tracking-tight">AppForge AI</span>
            </div>
            <nav className="flex flex-col gap-1 p-3" aria-label="Main">
              {NAV.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className="rounded-lg px-3 py-2 text-sm text-muted transition-colors
                             hover:bg-panel2 hover:text-ink"
                >
                  {item.label}
                </Link>
              ))}
            </nav>
          </aside>

          <div className="flex min-w-0 flex-1 flex-col">
            <header className="flex h-16 items-center justify-between border-b border-edge
                               bg-panel px-6">
              <nav className="flex gap-4 overflow-x-auto md:hidden" aria-label="Mobile">
                {NAV.map((item) => (
                  <Link key={item.href} href={item.href}
                        className="whitespace-nowrap text-sm text-muted hover:text-ink">
                    {item.label}
                  </Link>
                ))}
              </nav>
              <div className="hidden text-sm text-muted md:block">
                Autonomous app factory
              </div>
              <Link href="/pipeline" className="btn-primary">
                Review queue
              </Link>
            </header>

            <main className="flex-1 overflow-x-hidden p-6">{children}</main>
          </div>
        </div>
      </body>
    </html>
  );
}
