import type { Metadata } from 'next';

import { MakeClient } from './_components/MakeClient';

export const metadata: Metadata = {
  title: 'Quick Reel · Content Lab',
  description: 'Hook-first reel creator: pick a hook, make three choices, ship the reel.',
};

export default function MakePage() {
  return <MakeClient />;
}
