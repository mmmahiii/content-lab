import React from 'react';
import type { ReactNode } from 'react';

export const metadata = {
  title: 'Content Lab Operator Console',
  description: 'Org-safe operational detail views for pages, reels, runs, and packages.',
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body
        style={{
          margin: 0,
          color: '#172033',
          backgroundColor: '#f7efe4',
          fontFamily: '"IBM Plex Sans", "Segoe UI", "Helvetica Neue", Helvetica, Arial, sans-serif',
        }}
      >
        {children}
      </body>
    </html>
  );
}
