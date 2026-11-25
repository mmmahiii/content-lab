'use client';

import { AnimatePresence, motion, type PanInfo } from 'framer-motion';
import { ChevronUp, Shuffle } from 'lucide-react';
import { useMemo, useRef } from 'react';

import type { QuickReelVisual } from '@content-lab/reel-templates';

import { Button } from '@/components/ui/button';
import { cn } from '@/lib/cn';

import { hookReelTimeline, idleTimeline } from '../_lib/timelines';
import type { HookCandidate } from '../_lib/types';
import { ReelPlayer } from './ReelPlayer';

const MECHANISM_LABEL: Record<string, string> = {
  curiosity_gap: 'Curiosity gap',
  bold_claim: 'Bold claim',
  visual_first: 'Visual first',
  problem_agitation: 'Pain point',
  contrarian: 'Contrarian',
  story_open: 'Story open',
  list_promise: 'List promise',
  direct_question: 'Question',
};

export interface HookReelProps {
  topic: string;
  hooks: HookCandidate[] | null;
  focused: number;
  visuals: QuickReelVisual[];
  source: 'llm' | 'fallback' | null;
  surprising: boolean;
  error: string | null;
  onFocus: (index: number) => void;
  onChoose: (index: number) => void;
  onSurprise: () => void;
  onRetry: () => void;
}

const SWIPE_OFFSET = 70;
const SWIPE_VELOCITY = 450;

/** ② Hook reel: three hooks autoplay; swipe up (or ↓) for the next, tap (or Enter) to pick. */
export function HookReel(props: HookReelProps) {
  const { hooks, focused } = props;
  const loading = useMemo(
    () => idleTimeline(props.topic, props.visuals),
    [props.topic, props.visuals],
  );
  const timelines = useMemo(
    () => (hooks ?? []).map((h) => hookReelTimeline(h.overlay_text, props.visuals)),
    [hooks, props.visuals],
  );

  // A drag must never count as a tap: remember it and swallow the click that follows.
  const dragged = useRef(false);
  const onDragEnd = (_: unknown, info: PanInfo) => {
    setTimeout(() => {
      dragged.current = false;
    }, 0);
    if (!hooks) return;
    if (info.offset.y < -SWIPE_OFFSET || info.velocity.y < -SWIPE_VELOCITY) {
      props.onFocus(Math.min(hooks.length - 1, focused + 1));
    } else if (info.offset.y > SWIPE_OFFSET || info.velocity.y > SWIPE_VELOCITY) {
      props.onFocus(Math.max(0, focused - 1));
    }
  };

  if (!hooks || props.surprising) {
    return (
      <div className="absolute inset-0" data-testid="hooks-loading">
        <ReelPlayer timeline={loading} loop />
        <div className="absolute inset-x-0 bottom-[18%] flex flex-col items-center gap-3 px-8 text-center">
          {props.error ? (
            <>
              <p className="text-sm font-semibold text-danger">{props.error}</p>
              <Button size="sm" onClick={props.onRetry}>
                Try again
              </Button>
            </>
          ) : (
            <p className="animate-breathe text-sm font-semibold text-fg-muted">
              {props.surprising ? 'Putting a surprise together…' : 'Writing hooks…'}
            </p>
          )}
        </div>
      </div>
    );
  }

  const hook = hooks[focused];
  return (
    <div className="absolute inset-0 overflow-hidden" data-testid="hook-reel">
      <motion.div
        className="absolute inset-0 touch-none"
        drag="y"
        dragConstraints={{ top: 0, bottom: 0 }}
        dragElastic={0.35}
        onDragStart={() => {
          dragged.current = true;
        }}
        onDragEnd={onDragEnd}
        onClick={() => {
          if (!dragged.current) props.onChoose(focused);
        }}
        aria-label={`Hook ${focused + 1} of ${hooks.length}: ${hook.overlay_text}. Tap to use it.`}
        role="button"
      >
        <AnimatePresence initial={false} mode="popLayout">
          <motion.div
            key={focused}
            className="absolute inset-0"
            initial={{ y: '100%' }}
            animate={{ y: 0 }}
            exit={{ y: '-100%' }}
            transition={{ type: 'spring', damping: 30, stiffness: 300 }}
          >
            <ReelPlayer timeline={timelines[focused]} loop />
          </motion.div>
        </AnimatePresence>
      </motion.div>

      <div className="pointer-events-none absolute inset-x-0 top-0 flex items-center justify-between pl-16 pr-5 pt-[max(1.9rem,calc(env(safe-area-inset-top)+1.1rem))]">
        <p className="text-sm font-semibold text-fg-muted">Pick a hook</p>
        <div className="flex gap-1.5" aria-hidden>
          {hooks.map((_, i) => (
            <span
              key={i}
              className={cn('h-1.5 rounded-full transition-all', i === focused ? 'w-5 bg-fg' : 'w-1.5 bg-white/35')}
            />
          ))}
        </div>
      </div>

      <div className="absolute inset-x-0 bottom-0 space-y-3 px-5 pb-[max(1.25rem,env(safe-area-inset-bottom))]">
        <div className="pointer-events-none flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-fg-muted">
          <span className="rounded-full bg-black/45 px-2.5 py-1 backdrop-blur">
            {MECHANISM_LABEL[hook.mechanism] ?? hook.mechanism}
          </span>
          {props.source === 'fallback' ? (
            <span className="rounded-full bg-black/45 px-2.5 py-1 text-fg-subtle backdrop-blur">Offline hooks</span>
          ) : null}
        </div>
        <div className="flex gap-2">
          <Button variant="primary" size="lg" className="flex-1" onClick={() => props.onChoose(focused)}>
            Use this hook
          </Button>
          <Button size="lg" onClick={props.onSurprise} aria-label="Surprise me">
            <Shuffle className="h-5 w-5" />
          </Button>
        </div>
        {focused < hooks.length - 1 ? (
          <button
            type="button"
            onClick={() => props.onFocus(focused + 1)}
            className="flex w-full items-center justify-center gap-1 text-xs font-medium text-fg-subtle"
          >
            <ChevronUp className="h-4 w-4 animate-bounce" /> Swipe up for another hook
          </button>
        ) : (
          <p className="text-center text-xs font-medium text-fg-subtle">That&apos;s all {hooks.length}. Swipe down to go back.</p>
        )}
      </div>
    </div>
  );
}
