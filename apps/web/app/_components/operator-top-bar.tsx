'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

import type { OperatorContextSource } from '../_lib/operator-context';
import { WorkspaceOrgSwitcher } from './workspace-org-switcher';

type NavItem = {
  href: string;
  label: string;
  hint: string;
};

const navItems: NavItem[] = [
  { href: '/pages', label: 'Pages', hint: 'Primary workspace hub' },
  { href: '/queue', label: 'Queue', hint: 'Cross-page review work' },
  { href: '/actions', label: 'Actions', hint: 'Audited operator tasks' },
];

const flowItems = [
  {
    title: 'Choose a page',
    description: 'Open Pages first, then stay inside that page workspace for reels, runs, and policy.',
  },
  {
    title: 'Inspect page context',
    description: 'Use the page tabs to review recent reels, page-scoped runs, and current guardrails.',
  },
  {
    title: 'Start or review work',
    description: 'Open Actions when you need to trigger a workflow or complete an audited human step.',
  },
  {
    title: 'Track page activity',
    description: 'Use the page workspace itself to move between reel detail, run detail, and package output.',
  },
  {
    title: 'Handle cross-page review',
    description: 'Use Queue when human review work spans multiple pages.',
  },
];

function NavLink({ item, pathname }: { item: NavItem; pathname: string }) {
  const active = pathname === item.href || (item.href !== '/' && pathname.startsWith(item.href));

  return (
    <Link href={item.href} className="cl-nav-link" aria-current={active ? 'page' : undefined}>
      <span className="cl-nav-label">{item.label}</span>
      <span className="cl-nav-hint">{item.hint}</span>
    </Link>
  );
}

export function OperatorTopBar({
  context,
}: {
  context: { orgId: string | null; source: OperatorContextSource };
}) {
  const pathname = usePathname();

  return (
    <aside className="cl-sidebar" aria-label="Primary workspace navigation">
      <div className="cl-sidebar-card">
        <Link href="/" className="cl-brand">
          <span className="cl-brand-mark" aria-hidden />
          <span className="cl-brand-text">
            <span className="cl-brand-kicker">Content Lab</span>
            <span className="cl-brand-title">Operator Workspace</span>
            <span className="cl-brand-subtitle">Compact control surface for daily reel operations</span>
          </span>
        </Link>
        <p className="cl-compact cl-help-text">
          Pick a workspace org once here, then move from Pages into each page workspace without
          re-entering org context everywhere.
        </p>
        <WorkspaceOrgSwitcher initialOrgId={context.orgId} source={context.source} />
      </div>

      <nav className="cl-sidebar-card cl-nav" aria-label="Primary">
        {navItems.map((item) => (
          <NavLink key={item.href} item={item} pathname={pathname} />
        ))}
      </nav>

      <details className="cl-sidebar-card cl-disclosure">
        <summary className="cl-disclosure-summary">
          <span>
            <span className="cl-kicker">How Content Lab Works</span>
            <strong className="cl-disclosure-title">Workflow map</strong>
          </span>
          <span className="cl-disclosure-hint">Show</span>
        </summary>
        <ol className="cl-flow-list">
          {flowItems.map((item, index) => (
            <li key={item.title} className="cl-flow-item">
              <span className="cl-flow-step">{index + 1}</span>
              <div className="cl-flow-copy">
                <strong>{item.title}</strong>
                <span>{item.description}</span>
              </div>
            </li>
          ))}
        </ol>
      </details>

      <details className="cl-sidebar-card cl-disclosure">
        <summary className="cl-disclosure-summary">
          <span>
            <span className="cl-kicker">Need A Reference?</span>
            <strong className="cl-disclosure-title">Help and preview</strong>
          </span>
          <span className="cl-disclosure-hint">Show</span>
        </summary>
        <p className="cl-compact cl-help-text">
          Use the sample route if you want to explore the UI patterns before working with live data.
        </p>
        <div className="cl-button-row">
          <Link href="/ui-demo" className="cl-link-button">
            Open UI demo
          </Link>
          <Link href="/pages" className="cl-link-button is-secondary">
            Open pages
          </Link>
        </div>
      </details>
    </aside>
  );
}
