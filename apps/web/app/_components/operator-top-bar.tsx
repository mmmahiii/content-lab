'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

const DEMO_ORG_ID = '7d3d7599-820e-4c8d-9c74-3d3b6d6f2785';
const DEMO_PAGE_ID = '495d0d7e-acde-4c1d-b7ef-e5bc0d8ba3f4';

function shortOrg(value: string): string {
  return `${value.slice(0, 8)}…`;
}

type NavItem = { href: string; label: string; hint?: string };

const browseItems: NavItem[] = [
  { href: '/', label: 'Dashboard', hint: 'Workspace + API console' },
  { href: '/pages', label: 'Pages', hint: 'Owned portfolio' },
  { href: '/runs', label: 'Runs', hint: 'Workflow activity' },
  { href: '/reels', label: 'Reels', hint: 'Recent content state' },
  { href: '/queue', label: 'Queue', hint: 'Review & posting' },
  { href: '/policy', label: 'Policy', hint: 'Guardrails editor' },
];

function NavLink({ item, pathname }: { item: NavItem; pathname: string }) {
  const active = pathname === item.href || (item.href !== '/' && pathname.startsWith(item.href));
  return (
    <Link
      href={item.href}
      className={`cl-dropdown-item${active ? ' is-active' : ''}`}
      aria-current={active ? 'page' : undefined}
    >
      <span>{item.label}</span>
      {item.hint ? <div className="cl-dropdown-item-muted">{item.hint}</div> : null}
    </Link>
  );
}

export function OperatorTopBar() {
  const pathname = usePathname();
  const orgId =
    typeof process.env.NEXT_PUBLIC_CONTENT_LAB_OPERATOR_ORG_ID === 'string' &&
    process.env.NEXT_PUBLIC_CONTENT_LAB_OPERATOR_ORG_ID.length > 0
      ? process.env.NEXT_PUBLIC_CONTENT_LAB_OPERATOR_ORG_ID
      : DEMO_ORG_ID;

  return (
    <header className="cl-topbar">
      <div className="cl-topbar-inner">
        <Link href="/" className="cl-brand">
          <span className="cl-brand-mark" aria-hidden />
          <span className="cl-brand-text">
            <span className="cl-brand-kicker">Content Lab</span>
            <span className="cl-brand-title">Operator console</span>
          </span>
        </Link>

        <div className="cl-topbar-tools">
          <label className="cl-search">
            <span className="visually-hidden">Search (preview)</span>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden>
              <path
                d="M10.5 18a7.5 7.5 0 1 1 0-15 7.5 7.5 0 0 1 0 15Z"
                stroke="currentColor"
                strokeWidth="2"
              />
              <path d="M16 16 21 21" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            </svg>
            <input type="search" placeholder="Search pages, runs, reels…" readOnly tabIndex={-1} />
          </label>

          <details className="cl-dropdown">
            <summary>
              Workspace <span className="cl-chevron" aria-hidden />
            </summary>
            <div className="cl-dropdown-menu">
              <div className="cl-dropdown-hint">Active org</div>
              <div className="cl-dropdown-item" style={{ cursor: 'default' }}>
                <span style={{ fontFamily: 'var(--cl-mono)', fontSize: 13 }}>{shortOrg(orgId)}</span>
                <div className="cl-dropdown-item-muted">Set via CONTENT_LAB_OPERATOR_ORG_ID</div>
              </div>
              <div className="cl-dropdown-divider" />
              <Link href="/" className="cl-dropdown-item">
                Workspace home
              </Link>
              <Link
                href={`/orgs/${orgId}/pages/${DEMO_PAGE_ID}`}
                className="cl-dropdown-item"
              >
                Sample page detail
              </Link>
            </div>
          </details>

          <details className="cl-dropdown">
            <summary>
              Browse <span className="cl-chevron" aria-hidden />
            </summary>
            <div className="cl-dropdown-menu">
              <div className="cl-dropdown-hint">Navigate</div>
              {browseItems.map((item) => (
                <NavLink key={item.href} item={item} pathname={pathname} />
              ))}
            </div>
          </details>

          <details className="cl-dropdown">
            <summary>
              Help <span className="cl-chevron" aria-hidden />
            </summary>
            <div className="cl-dropdown-menu">
              <div className="cl-dropdown-hint">Review</div>
              <Link href="/ui-demo" className="cl-dropdown-item">
                UI demo & patterns
                <div className="cl-dropdown-item-muted">Shell, menus, tables</div>
              </Link>
              <div className="cl-dropdown-divider" />
              <Link href="/#operator-actions" className="cl-dropdown-item">
                Operator API actions
                <div className="cl-dropdown-item-muted">Forms at the bottom of the home route</div>
              </Link>
            </div>
          </details>
        </div>
      </div>
    </header>
  );
}
