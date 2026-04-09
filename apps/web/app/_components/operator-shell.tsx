import Link from 'next/link';
import type { ReactNode } from 'react';

const shellStyle = {
  backgroundColor: '#f6f5f1',
  color: '#16202a',
  fontFamily: '"Segoe UI", system-ui, sans-serif',
  minHeight: '100vh',
  margin: 0,
} as const;

const frameStyle = {
  margin: '0 auto',
  maxWidth: '1200px',
  padding: '24px',
} as const;

const headerStyle = {
  alignItems: 'flex-start',
  borderBottom: '1px solid #d9ddd4',
  display: 'flex',
  flexWrap: 'wrap',
  gap: '16px',
  justifyContent: 'space-between',
  marginBottom: '24px',
  paddingBottom: '18px',
} as const;

const navStyle = {
  display: 'flex',
  flexWrap: 'wrap',
  gap: '10px',
} as const;

const navLinkStyle = {
  border: '1px solid #c4cbc0',
  borderRadius: '999px',
  color: '#16202a',
  fontSize: '0.95rem',
  padding: '8px 12px',
  textDecoration: 'none',
} as const;

export function OperatorShell({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body style={shellStyle}>
        <div style={frameStyle}>
          <header style={headerStyle}>
            <div>
              <p
                style={{
                  fontSize: '0.85rem',
                  letterSpacing: '0.08em',
                  margin: 0,
                  textTransform: 'uppercase',
                }}
              >
                Content Lab
              </p>
              <h1 style={{ fontSize: '1.75rem', margin: '8px 0 0' }}>Operator console</h1>
            </div>

            <nav aria-label="Primary" style={navStyle}>
              <Link href="/" style={navLinkStyle}>
                Dashboard
              </Link>
              <Link href="/pages" style={navLinkStyle}>
                Pages
              </Link>
              <Link href="/runs" style={navLinkStyle}>
                Runs
              </Link>
              <Link href="/reels" style={navLinkStyle}>
                Reels
              </Link>
            </nav>
          </header>

          {children}
        </div>
      </body>
    </html>
  );
}
