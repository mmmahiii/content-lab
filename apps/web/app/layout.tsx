import type { ReactNode } from 'react';

import { OperatorShell } from './_components/operator-shell';

export default function RootLayout({ children }: { children: ReactNode }) {
  return <OperatorShell>{children}</OperatorShell>;
}
