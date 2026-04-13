import type { ReactNode } from 'react';

import { OperatorTopBar } from './operator-top-bar';

export function OperatorShell({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="cl-body">
        <a className="cl-skip" href="#main-content">
          Skip to content
        </a>
        <OperatorTopBar />
        <div id="main-content" className="cl-main">
          {children}
        </div>
      </body>
    </html>
  );
}
