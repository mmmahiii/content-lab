'use client';

import dynamic from 'next/dynamic';

import { PhoneFrame } from '@/components/ui/phone-frame';

/** While the player code loads: a moving gradient, never a spinner. */
function Warmup() {
  return (
    <PhoneFrame>
      <div
        data-testid="make-warmup"
        className="absolute inset-0 animate-shimmer bg-[linear-gradient(160deg,#F6A57D_0%,#4A2158_45%,#FF3D71_100%)] bg-[length:200%_200%] opacity-70"
      />
    </PhoneFrame>
  );
}

// The Remotion Player and font loading need the DOM, so the app renders client-side only.
const QuickReelApp = dynamic(() => import('./QuickReelApp'), { ssr: false, loading: Warmup });

export function MakeClient() {
  return <QuickReelApp />;
}
