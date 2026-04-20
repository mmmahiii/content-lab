'use client';

import { useState, type ReactNode } from 'react';

import type { OperatorContextSource } from '../_lib/operator-context';
import { OperatorTopBar } from './operator-top-bar';

export function OperatorWorkspaceLayout({
  children,
  context,
}: {
  children: ReactNode;
  context: { orgId: string | null; source: OperatorContextSource };
}) {
  const [sidebarOpen, setSidebarOpen] = useState(true);

  return (
    <div className={sidebarOpen ? 'cl-shell' : 'cl-shell is-sidebar-collapsed'}>
      <OperatorTopBar context={context} onCollapseSidebar={() => setSidebarOpen(false)} />
      <div className="cl-shell-main">
        {!sidebarOpen ? (
          <div className="cl-sidebar-reopen-bar">
            <button
              type="button"
              className="cl-sidebar-reopen-button"
              onClick={() => setSidebarOpen(true)}
              aria-expanded="false"
            >
              Show workspace menu
            </button>
          </div>
        ) : null}
        <main id="main-content" className="cl-main">
          {children}
        </main>
      </div>
    </div>
  );
}
