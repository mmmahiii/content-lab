import Link from 'next/link';

import { demoIds, packagePath, pagePath, reelPath, runPath } from '../_lib/content-lab-data';

export const metadata = {
  title: 'UI demo — Content Lab',
  description: 'Static reference for the operator shell, menus, and table row actions.',
};

export default function UiDemoPage() {
  return (
    <div style={{ display: 'grid', gap: 20, maxWidth: 920 }}>
      <header
        style={{
          padding: 18,
          borderRadius: 14,
          border: '1px solid var(--cl-border)',
          background: 'var(--cl-surface)',
          boxShadow: 'var(--cl-shadow)',
        }}
      >
        <p
          style={{
            margin: 0,
            fontSize: 11,
            fontWeight: 700,
            letterSpacing: '0.12em',
            textTransform: 'uppercase',
            color: 'var(--cl-text-muted)',
          }}
        >
          Review route
        </p>
        <h1 style={{ margin: '8px 0 6px', fontSize: '1.55rem', letterSpacing: '-0.02em' }}>
          Operator UI demo
        </h1>
        <p style={{ margin: 0, color: 'var(--cl-text-muted)', lineHeight: 1.55, maxWidth: 640, fontSize: 13 }}>
          Open this page at{' '}
          <Link href="/ui-demo" style={{ color: 'var(--cl-accent)', fontWeight: 600 }}>
            /ui-demo
          </Link>{' '}
          while <code style={{ fontFamily: 'var(--cl-mono)', fontSize: 12 }}>pnpm --filter web dev</code>{' '}
          is running. The sticky top bar, section menus, and row actions use the same patterns as the
          rest of the console.
        </p>
      </header>

      <section
        style={{
          padding: 16,
          borderRadius: 14,
          border: '1px solid var(--cl-border)',
          background: 'var(--cl-surface)',
        }}
      >
        <h2 style={{ margin: '0 0 8px', fontSize: '1.08rem' }}>Dropdown summaries</h2>
        <p style={{ margin: '0 0 12px', color: 'var(--cl-text-muted)', fontSize: 13 }}>
          Native <code style={{ fontFamily: 'var(--cl-mono)', fontSize: 12 }}>details</code> menus
          keep dependencies minimal and work without JavaScript for disclosure.
        </p>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'flex-start' }}>
          <details className="cl-dropdown">
            <summary>
              Demo org links <span className="cl-chevron" aria-hidden />
            </summary>
            <div className="cl-dropdown-menu">
              <div className="cl-dropdown-hint">Deep links</div>
              <Link href={pagePath(demoIds.orgId, demoIds.pageId)} className="cl-dropdown-item">
                Page detail
              </Link>
              <Link
                href={reelPath(demoIds.orgId, demoIds.pageId, demoIds.reelId)}
                className="cl-dropdown-item"
              >
                Reel detail
              </Link>
              <Link href={runPath(demoIds.orgId, demoIds.runId)} className="cl-dropdown-item">
                Run detail
              </Link>
              <Link href={packagePath(demoIds.orgId, demoIds.runId)} className="cl-dropdown-item">
                Package detail
              </Link>
            </div>
          </details>

          <details className="cl-dropdown">
            <summary>
              Section menu <span className="cl-chevron" aria-hidden />
            </summary>
            <div className="cl-dropdown-menu">
              <div className="cl-dropdown-hint">Matches dashboard panels</div>
              <Link href="/pages" className="cl-dropdown-item">
                Open focused route
              </Link>
              <Link href="/" className="cl-dropdown-item">
                Back to dashboard
              </Link>
            </div>
          </details>
        </div>
      </section>

      <section
        style={{
          padding: 16,
          borderRadius: 14,
          border: '1px solid var(--cl-border)',
          background: 'var(--cl-surface)',
          overflowX: 'auto',
        }}
      >
        <h2 style={{ margin: '0 0 8px', fontSize: '1.08rem' }}>Table row actions</h2>
        <p style={{ margin: '0 0 12px', color: 'var(--cl-text-muted)', fontSize: 13 }}>
          Ellipsis triggers mirror the Pages, Runs, Reels, and Queue tables.
        </p>
        <table
          style={{
            borderCollapse: 'collapse',
            width: '100%',
            minWidth: 480,
            fontSize: 13,
          }}
        >
          <thead>
            <tr style={{ borderBottom: '1px solid var(--cl-border)' }}>
              <th style={{ textAlign: 'left', padding: '8px 7px', fontWeight: 600 }}>Resource</th>
              <th style={{ textAlign: 'left', padding: '8px 7px', fontWeight: 600 }}>State</th>
              <th style={{ textAlign: 'right', padding: '8px 7px', fontWeight: 600 }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr style={{ borderTop: '1px solid var(--cl-border)' }}>
              <td style={{ padding: '9px 7px' }}>
                <strong>Northwind reel batch</strong>
                <div style={{ color: 'var(--cl-text-muted)', marginTop: 3, fontSize: 12 }}>Sample row</div>
              </td>
              <td style={{ padding: '9px 7px' }}>
                <span
                  style={{
                    display: 'inline-flex',
                    padding: '3px 8px',
                    borderRadius: 999,
                    background: 'rgba(31, 106, 77, 0.12)',
                    color: '#1f6a4d',
                    fontWeight: 600,
                    fontSize: 12,
                  }}
                >
                  Ready
                </span>
              </td>
              <td style={{ padding: '9px 7px', textAlign: 'right' }}>
                <details className="cl-row-dropdown">
                  <summary className="cl-actions-trigger" aria-label="Row actions">
                    ⋯
                  </summary>
                  <div className="cl-dropdown-menu">
                    <div className="cl-dropdown-hint">Navigate</div>
                    <Link href={runPath(demoIds.orgId, demoIds.runId)} className="cl-dropdown-item">
                      Run detail
                    </Link>
                    <Link
                      href={packagePath(demoIds.orgId, demoIds.runId)}
                      className="cl-dropdown-item"
                    >
                      Package detail
                    </Link>
                  </div>
                </details>
              </td>
            </tr>
          </tbody>
        </table>
      </section>

      <p style={{ margin: 0, fontSize: 12, color: 'var(--cl-text-muted)' }}>
        When you are done reviewing, use Browse → Dashboard in the top bar or go{' '}
        <Link href="/" style={{ color: 'var(--cl-accent)', fontWeight: 600 }}>
          home
        </Link>
        .
      </p>
    </div>
  );
}
