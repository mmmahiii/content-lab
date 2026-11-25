'use client';

import { motion } from 'framer-motion';
import { Check, Copy, Download, RotateCcw, Send, Shuffle, SlidersHorizontal } from 'lucide-react';
import { useState } from 'react';

import type { ReelTimeline } from '@content-lab/reel-templates';

import { Button, buttonVariants } from '@/components/ui/button';
import { Chip } from '@/components/ui/chip';
import { cn } from '@/lib/cn';

import type { Moment, RenderJobView } from '../_lib/types';
import { ReelPlayer } from './ReelPlayer';

export type ReviewState =
  | { status: 'idle' }
  | { status: 'sending' }
  | { status: 'sent'; reelId: string }
  | { status: 'failed'; message: string };

const MOMENT_NAME: Record<Moment, string> = { structure: 'Story', energy: 'Energy', ending: 'Ending' };

export interface ShipScreenProps {
  timeline: ReelTimeline;
  caption: string;
  pageName: string;
  render: RenderJobView | null;
  renderError: string | null;
  review: ReviewState;
  choiceLabels: Record<Moment, string>;
  onDownload: () => void;
  onRetryRender: () => void;
  onCopyCaption: () => void;
  onSendToReview: () => void;
  onRemix: () => void;
  onChangeOne: (moment: Moment) => void;
  onRestart: () => void;
}

function DownloadButton({
  render,
  renderError,
  onDownload,
  onRetry,
}: Pick<ShipScreenProps, 'render' | 'renderError'> & { onDownload: () => void; onRetry: () => void }) {
  if (render?.status === 'done' && render.videoUrl) {
    return (
      <a
        href={`${render.videoUrl}?download=1`}
        download={`quick-reel-${render.renderId}.mp4`}
        onClick={onDownload}
        className={cn(buttonVariants({ variant: 'accent', size: 'lg' }), 'w-full')}
      >
        <Download className="h-5 w-5" /> Download MP4
      </a>
    );
  }
  if (renderError || render?.status === 'failed' || render?.status === 'cancelled') {
    return (
      <div className="space-y-1">
        <Button variant="glass" size="lg" className="w-full" onClick={onRetry}>
          <RotateCcw className="h-5 w-5" /> Retry MP4 render
        </Button>
        <p className="line-clamp-2 text-center text-xs text-danger">{renderError ?? render?.error ?? 'Render stopped'}</p>
      </div>
    );
  }
  // Rendering: the button fills as the MP4 renders (motion, not a spinner).
  const progress = render?.progress ?? 0;
  return (
    <Button variant="glass" size="lg" className="w-full" disabled aria-live="polite">
      <span
        className="absolute inset-y-0 left-0 bg-accent/35 transition-[width] duration-700"
        style={{ width: `${Math.max(4, progress * 100)}%` }}
        aria-hidden
      />
      <span className="relative flex items-center gap-2">
        <Download className="h-5 w-5" />
        {render?.status === 'rendering' ? `Rendering MP4 · ${Math.round(progress * 100)}%` : 'Preparing MP4…'}
      </span>
    </Button>
  );
}

/** ⑥ Ship: download, caption, review queue, remix, or change one choice. */
export function ShipScreen(props: ShipScreenProps) {
  const [changing, setChanging] = useState(false);
  return (
    <div className="absolute inset-0 flex flex-col bg-ink" data-testid="ship">
      <motion.div
        className="relative min-h-0 flex-1 px-6 pb-3 pt-[max(1.5rem,env(safe-area-inset-top))]"
        initial={{ scale: 1.08, opacity: 0.6 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ type: 'spring', damping: 26, stiffness: 220 }}
      >
        <div className="mx-auto aspect-[9/16] h-full max-w-full overflow-hidden rounded-2xl border border-line shadow-2xl">
          <ReelPlayer timeline={props.timeline} loop />
        </div>
      </motion.div>
      <motion.div
        initial={{ y: '100%' }}
        animate={{ y: 0 }}
        transition={{ type: 'spring', damping: 28, stiffness: 260 }}
        className="relative space-y-3 rounded-t-[28px] border-t border-line bg-ink-raised px-4 pb-[max(1rem,env(safe-area-inset-bottom))] pt-4"
      >
        <DownloadButton
          render={props.render}
          renderError={props.renderError}
          onDownload={props.onDownload}
          onRetry={props.onRetryRender}
        />
        <div className="grid grid-cols-2 gap-2">
          <Button onClick={props.onCopyCaption}>
            <Copy className="h-4 w-4" /> Copy caption
          </Button>
          <Button
            onClick={props.onSendToReview}
            disabled={props.review.status === 'sending' || props.review.status === 'sent'}
            className={cn(props.review.status === 'sent' && 'text-signal')}
          >
            {props.review.status === 'sent' ? <Check className="h-4 w-4" /> : <Send className="h-4 w-4" />}
            {props.review.status === 'sent'
              ? 'In review'
              : props.review.status === 'sending'
                ? 'Sending…'
                : 'Send to Review'}
          </Button>
          <Button onClick={props.onRemix}>
            <Shuffle className="h-4 w-4" /> Remix
          </Button>
          <Button onClick={() => setChanging((v) => !v)} aria-expanded={changing}>
            <SlidersHorizontal className="h-4 w-4" /> Change one thing
          </Button>
        </div>
        {changing ? (
          <div className="flex flex-wrap gap-2" role="group" aria-label="Change one thing">
            {(Object.keys(MOMENT_NAME) as Moment[]).map((moment) => (
              <Chip key={moment} onClick={() => props.onChangeOne(moment)}>
                <span className="text-fg-subtle">{MOMENT_NAME[moment]}</span> {props.choiceLabels[moment]}
              </Chip>
            ))}
          </div>
        ) : null}
        {props.review.status === 'failed' ? (
          <p className="text-center text-xs text-danger">{props.review.message}</p>
        ) : null}
        {props.review.status === 'sent' ? (
          <p className="text-center text-xs text-fg-muted">Saved to {props.pageName}&apos;s review queue.</p>
        ) : null}
        <details className="group rounded-2xl border border-line bg-white/4 px-3 py-2 text-sm">
          <summary className="cursor-pointer list-none text-xs font-semibold text-fg-muted">Caption</summary>
          <p className="mt-2 max-h-28 overflow-y-auto whitespace-pre-line text-xs leading-relaxed text-fg-muted">
            {props.caption}
          </p>
        </details>
        <Button variant="ghost" size="sm" className="w-full" onClick={props.onRestart}>
          <RotateCcw className="h-4 w-4" /> New reel
        </Button>
      </motion.div>
    </div>
  );
}
