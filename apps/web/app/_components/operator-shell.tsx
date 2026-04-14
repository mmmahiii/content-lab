import type { ReactNode } from 'react';

import { OperatorTopBar } from './operator-top-bar';
import { resolveOperatorContext } from '../_lib/operator-dashboard';

export async function OperatorShell({ children }: { children: ReactNode }) {
  const context = await resolveOperatorContext();

  return (
    <html lang="en">
      <body className="cl-body">
        <a className="cl-skip" href="#main-content">
          Skip to content
        </a>
        <div className="cl-shell">
          <OperatorTopBar context={context} />
          <div className="cl-shell-main">
            <main id="main-content" className="cl-main">
              {children}
            </main>
          </div>
        </div>
      </body>
    </html>
  );
}
