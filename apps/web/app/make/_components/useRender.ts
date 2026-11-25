'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

import type { ReelTimeline } from '@content-lab/reel-templates';

import type { QuickReelApi } from '../_lib/api';
import type { RenderJobView } from '../_lib/types';

const POLL_MS = 900;

/**
 * Start a local MP4 render for the current timeline and poll it. Starting again with a new
 * timeline (Remix) replaces the previous request if it has not started rendering yet.
 */
export function useRender(api: QuickReelApi) {
  const [job, setJob] = useState<RenderJobView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const current = useRef<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const stopPolling = () => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
  };

  const poll = useCallback(
    (renderId: string) => {
      stopPolling();
      timer.current = setTimeout(async () => {
        try {
          const next = await api.getRender(renderId);
          if (current.current !== renderId) return;
          setJob(next);
          if (next.status === 'queued' || next.status === 'rendering') poll(renderId);
        } catch (e) {
          if (current.current === renderId) setError(e instanceof Error ? e.message : String(e));
        }
      }, POLL_MS);
    },
    [api],
  );

  const start = useCallback(
    async (timeline: ReelTimeline) => {
      setError(null);
      try {
        const started = await api.startRender(timeline, current.current);
        current.current = started.renderId;
        setJob(started);
        if (started.status === 'queued' || started.status === 'rendering') poll(started.renderId);
        return started;
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
        return null;
      }
    },
    [api, poll],
  );

  const reset = useCallback(() => {
    stopPolling();
    current.current = null;
    setJob(null);
    setError(null);
  }, []);

  useEffect(() => stopPolling, []);

  return { job, error, start, reset };
}
