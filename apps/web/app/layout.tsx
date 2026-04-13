import React from 'react';
import type { ReactNode } from 'react';

import { OperatorShell } from './_components/operator-shell';

import './globals.css';

export const metadata = {
  title: 'Content Lab Operator Console',
  description: 'Org-safe operational detail views for pages, reels, runs, and packages.',
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return <OperatorShell>{children}</OperatorShell>;
}
