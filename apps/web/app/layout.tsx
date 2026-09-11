import type { ReactNode } from 'react';

import './globals.css';

export const metadata = {
  title: 'Content Laboratory · Operator studio',
  description:
    'A local operator prototype for thoughtful content production. All services are simulated.',
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
