import type { ReactNode } from 'react';

import './globals.css';

export const metadata = {
  title: 'Content Lab',
  description: 'Content Lab UI rebuild workspace.',
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
