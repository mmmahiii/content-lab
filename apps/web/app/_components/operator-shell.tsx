import type { ReactNode } from 'react';

import { OperatorWorkspaceLayout } from './operator-workspace-layout';
import { resolveOperatorContext } from '../_lib/operator-dashboard';

export async function OperatorShell({ children }: { children: ReactNode }) {
  const context = await resolveOperatorContext();

  return (
    <html lang="en">
      <body className="cl-body">
        <a className="cl-skip" href="#main-content">
          Skip to content
        </a>
        <OperatorWorkspaceLayout context={context}>{children}</OperatorWorkspaceLayout>
      </body>
    </html>
  );
}
