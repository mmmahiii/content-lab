import type { Metadata, Viewport } from 'next';
import type { ReactNode } from 'react';

import { Toaster } from '@/components/ui/toast';

import './globals.css';

export const metadata: Metadata = {
  title: 'Content Lab',
  description: 'Content Lab: Quick Reel and the operator studio.',
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  viewportFit: 'cover',
  themeColor: '#07070b',
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Toaster>{children}</Toaster>
      </body>
    </html>
  );
}
