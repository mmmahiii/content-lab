'use client';

import { motion } from 'framer-motion';
import { Shuffle } from 'lucide-react';

import type { ReelTimeline } from '@content-lab/reel-templates';

import { Button } from '@/components/ui/button';
import { cn } from '@/lib/cn';

import type { ChoiceOption, Moment } from '../_lib/types';
import { ReelPlayer } from './ReelPlayer';

export const MOMENT_QUESTION: Record<Moment, string> = {
  structure: 'Where does this go?',
  energy: 'Pick the energy',
  ending: 'How does it end?',
};

export interface ChoiceCard {
  option: ChoiceOption;
  /** Looping mini-preview; undefined while it is still being composed. */
  timeline?: ReelTimeline;
}

export interface ChoiceSheetProps {
  moment: Moment;
  cards: ChoiceCard[];
  focused: number;
  /** Option chosen before ("Change one thing"), highlighted. */
  current?: string;
  onChoose: (optionId: string) => void;
  onFocus: (index: number) => void;
  onSurprise: () => void;
}

/** ③ Cliffhanger: 2-3 choice cards slide up, each a looping preview of what plays next. */
export function ChoiceSheet({ moment, cards, focused, current, onChoose, onFocus, onSurprise }: ChoiceSheetProps) {
  return (
    <motion.div
      className="absolute inset-x-0 bottom-0 z-20 px-4 pb-[max(1rem,env(safe-area-inset-bottom))]"
      initial={{ y: '100%' }}
      animate={{ y: 0 }}
      exit={{ y: '100%' }}
      transition={{ type: 'spring', damping: 28, stiffness: 280 }}
      data-testid="choice-sheet"
    >
      <h2 className="mb-3 text-center font-display text-2xl font-black drop-shadow-[0_2px_12px_rgba(0,0,0,0.6)]">
        {MOMENT_QUESTION[moment]}
      </h2>
      <div className="grid grid-cols-3 gap-2.5" role="radiogroup" aria-label={MOMENT_QUESTION[moment]}>
        {cards.map((card, i) => (
          <motion.button
            key={card.option.option_id}
            type="button"
            role="radio"
            aria-checked={card.option.option_id === current}
            aria-label={`${i + 1}. ${card.option.label}: ${card.option.teaser}`}
            initial={{ y: 60, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            transition={{ delay: 0.05 + i * 0.06, type: 'spring', damping: 24, stiffness: 300 }}
            whileTap={{ scale: 0.95 }}
            onClick={() => onChoose(card.option.option_id)}
            onMouseEnter={() => onFocus(i)}
            onFocus={() => onFocus(i)}
            className={cn(
              'group relative flex flex-col overflow-hidden rounded-2xl border bg-ink-raised text-left transition-colors',
              i === focused ? 'border-fg' : 'border-line-strong',
            )}
          >
            <div className="relative aspect-[9/14] w-full overflow-hidden bg-ink-sunken">
              {card.timeline ? (
                <ReelPlayer timeline={card.timeline} loop className="scale-[1.02]" />
              ) : (
                <div className="h-full w-full animate-shimmer bg-[linear-gradient(110deg,rgba(255,255,255,0.04),rgba(255,255,255,0.14),rgba(255,255,255,0.04))] bg-[length:200%_100%]" />
              )}
              <span className="absolute left-1.5 top-1.5 grid h-6 w-6 place-items-center rounded-full bg-black/60 text-xs font-bold backdrop-blur">
                {i + 1}
              </span>
              {card.option.option_id === current ? (
                <span className="absolute right-1.5 top-1.5 rounded-full bg-accent px-2 py-0.5 text-[10px] font-bold text-accent-ink">
                  Now
                </span>
              ) : null}
            </div>
            <div className="space-y-0.5 p-2.5">
              <p className="text-[13px] font-bold leading-tight">{card.option.label}</p>
              <p className="line-clamp-2 text-[11px] leading-snug text-fg-muted">{card.option.teaser}</p>
            </div>
          </motion.button>
        ))}
      </div>
      <Button variant="ghost" size="sm" className="mx-auto mt-2 flex" onClick={onSurprise}>
        <Shuffle className="h-4 w-4" /> Surprise me
      </Button>
    </motion.div>
  );
}
