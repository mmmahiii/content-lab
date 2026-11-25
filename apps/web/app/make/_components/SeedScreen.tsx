'use client';

import { motion } from 'framer-motion';
import { ArrowUp, Shuffle } from 'lucide-react';
import { useEffect, useMemo, useState, type FormEvent } from 'react';

import type { QuickReelVisual } from '@content-lab/reel-templates';

import { Button } from '@/components/ui/button';
import { Chip } from '@/components/ui/chip';

import { topicSuggestions } from '../_lib/suggestions';
import { idleTimeline } from '../_lib/timelines';
import type { Org, Page } from '../_lib/types';
import { ReelPlayer } from './ReelPlayer';

export interface SeedScreenProps {
  orgs: Org[];
  orgId: string | null;
  onOrg: (orgId: string) => void;
  pages: Page[] | null;
  pageId: string | null;
  onPage: (pageId: string) => void;
  visuals: QuickReelVisual[];
  packName: string | null;
  loadError: string | null;
  onRetry: () => void;
  onStart: (topic: string, surprise: boolean) => void;
}

/** ① Seed: pick a page, then type a topic or tap a suggestion. The only typing in the flow. */
export function SeedScreen(props: SeedScreenProps) {
  const { pages, pageId, onStart } = props;
  const [topic, setTopic] = useState('');
  const page = pages?.find((p) => p.id === pageId) ?? null;
  const suggestions = useMemo(() => topicSuggestions(page), [page]);
  // The typed topic plays live as kinetic text; debounced so it re-animates per pause.
  const settled = useDebounced(topic.trim(), 450);
  const preview = useMemo(
    () => idleTimeline(settled || 'What is your reel about?', props.visuals),
    [settled, props.visuals],
  );
  const ready = Boolean(page);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (ready && topic.trim()) onStart(topic.trim(), false);
  };

  return (
    <div className="absolute inset-0">
      <div className="absolute inset-0 opacity-80" aria-hidden>
        <ReelPlayer timeline={preview} loop />
      </div>
      <div className="absolute inset-x-0 top-0 flex items-center justify-between px-5 pt-[max(1rem,env(safe-area-inset-top))]">
        <p className="shrink-0 font-display text-lg font-black tracking-tight">Quick Reel</p>
        {props.packName ? (
          <span className="max-w-[60%] truncate rounded-full bg-black/40 px-3 py-1 text-xs text-fg-muted backdrop-blur">
            Visuals: {props.packName}
          </span>
        ) : null}
      </div>

      <motion.div
        initial={{ y: 40, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ type: 'spring', damping: 26, stiffness: 260 }}
        className="absolute inset-x-0 bottom-0 space-y-4 rounded-t-[28px] border-t border-line bg-ink/75 px-5 pb-[max(1.25rem,env(safe-area-inset-bottom))] pt-5 backdrop-blur-xl"
      >
        {props.loadError ? (
          <div className="space-y-3 rounded-2xl border border-danger/30 bg-danger/10 p-4 text-sm">
            <p className="font-semibold text-danger">{props.loadError}</p>
            <Button size="sm" onClick={props.onRetry}>
              Try again
            </Button>
          </div>
        ) : null}

        {props.orgs.length > 1 ? (
          <div className="-mx-5 flex gap-2 overflow-x-auto px-5 pb-1" role="radiogroup" aria-label="Org">
            {props.orgs.map((org) => (
              <Chip key={org.id} selected={org.id === props.orgId} onClick={() => props.onOrg(org.id)}>
                {org.name}
              </Chip>
            ))}
          </div>
        ) : null}

        <div className="space-y-2">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-fg-subtle">Page</p>
          <div className="-mx-5 flex gap-2 overflow-x-auto px-5 pb-1" role="radiogroup" aria-label="Page">
            {pages === null && !props.loadError
              ? [0, 1, 2].map((i) => (
                  <div
                    key={i}
                    className="h-10 w-28 shrink-0 animate-shimmer rounded-full bg-[linear-gradient(90deg,rgba(255,255,255,0.06),rgba(255,255,255,0.16),rgba(255,255,255,0.06))] bg-[length:200%_100%]"
                  />
                ))
              : null}
            {pages?.length === 0 ? (
              <p className="text-sm text-fg-muted">
                No pages in this org yet. Create one with <code>POST /orgs/{'{org}'}/pages</code>.
              </p>
            ) : null}
            {pages?.map((p) => (
              <Chip key={p.id} selected={p.id === pageId} onClick={() => props.onPage(p.id)}>
                <span className="grid h-6 w-6 place-items-center rounded-full bg-white/15 text-xs font-bold">
                  {p.display_name.slice(0, 1).toUpperCase()}
                </span>
                {p.display_name}
                {p.metadata?.niche ? <span className="text-fg-subtle">· {String(p.metadata.niche)}</span> : null}
              </Chip>
            ))}
          </div>
        </div>

        <form onSubmit={submit} className="flex items-center gap-2">
          <label htmlFor="topic" className="sr-only">
            Topic
          </label>
          <input
            id="topic"
            value={topic}
            onChange={(e) => setTopic(e.target.value.slice(0, 120))}
            placeholder={suggestions[0] ? `e.g. ${suggestions[0]}` : 'What is it about?'}
            autoComplete="off"
            enterKeyHint="go"
            disabled={!ready}
            className="h-14 min-w-0 flex-1 rounded-2xl border border-line-strong bg-white/8 px-4 text-base text-fg placeholder:text-fg-subtle focus:border-fg focus:outline-none disabled:opacity-50"
          />
          <Button
            type="submit"
            variant="accent"
            size="icon"
            className="h-14 w-14 rounded-2xl"
            disabled={!ready || !topic.trim()}
            aria-label="Make hooks"
          >
            <ArrowUp className="h-5 w-5" />
          </Button>
        </form>

        <div className="-mx-5 flex gap-2 overflow-x-auto px-5 pb-1" aria-label="Suggested topics">
          {suggestions.map((s) => (
            <Chip key={s} disabled={!ready} onClick={() => onStart(s, false)}>
              {s}
            </Chip>
          ))}
        </div>

        <Button
          variant="ghost"
          size="sm"
          className="w-full"
          disabled={!ready}
          onClick={() => onStart(topic.trim() || suggestions[Math.floor(Math.random() * suggestions.length)] || 'one quick win', true)}
        >
          <Shuffle className="h-4 w-4" /> Surprise me
        </Button>
      </motion.div>
    </div>
  );
}

function useDebounced<T>(value: T, ms: number): T {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setSettled(value), ms);
    return () => clearTimeout(id);
  }, [value, ms]);
  return settled;
}
