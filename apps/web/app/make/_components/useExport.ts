'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

import type { ExportResult, QuickReelApi } from '../_lib/api';
import type { RenderJobView } from '../_lib/types';

type ExportBody = Parameters<QuickReelApi['exportReel']>[2];

/** Typical export time; only drives the progress bar (the real result arrives when done). */
const EXPECTED_MS = 20_000;

/**
 * Fast MP4 export (FFmpeg on the API) started as soon as the reel is final. Reports in the
 * same `RenderJobView` shape as the Remotion render so the Ship screen is unchanged; progress
 * is time-based because the export is a single request.
 */
export function useExport(api: QuickReelApi) {
  const [job, setJob] = useState<RenderJobView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const current = useRef<string | null>(null);
  const ticker = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopTicker = () => {
    if (ticker.current) clearInterval(ticker.current);
    ticker.current = null;
  };

  const start = useCallback(
    async (orgId: string, pageId: string, body: ExportBody) => {
      const key = JSON.stringify([orgId, pageId, body]);
      if (current.current === key) return;
      current.current = key;
      setError(null);
      stopTicker();
      const startedAt = Date.now();
      setJob(pendingView(0));
      ticker.current = setInterval(() => {
        if (current.current !== key) return;
        // Ease towards 95% so the bar keeps moving but never claims done before it is.
        const progress = 0.95 * (1 - Math.exp(-(Date.now() - startedAt) / EXPECTED_MS));
        setJob((prev) => (prev && prev.status === 'rendering' ? { ...prev, progress } : prev));
      }, 250);
      try {
        const result = await api.exportReel(orgId, pageId, body);
        if (current.current !== key) return;
        setJob(doneView(result));
      } catch (e) {
        if (current.current !== key) return;
        setError(e instanceof Error ? e.message : String(e));
        setJob((prev) => (prev ? { ...prev, status: 'failed', error: String(e) } : prev));
      } finally {
        if (current.current === key) stopTicker();
      }
    },
    [api],
  );

  const reset = useCallback(() => {
    stopTicker();
    current.current = null;
    setJob(null);
    setError(null);
  }, []);

  useEffect(() => stopTicker, []);

  return { job, error, start, reset };
}

function pendingView(progress: number): RenderJobView {
  return {
    renderId: '',
    status: 'rendering',
    progress,
    error: null,
    durationSeconds: 0,
    width: 1080,
    height: 1920,
    fps: 30,
    overlayTraceStatus: null,
    videoUrl: null,
    traceUrl: null,
  };
}

export function doneView(result: ExportResult): RenderJobView {
  const trace = result.checks.find((check) => check.gate_name === 'package_overlay_render_trace');
  return {
    renderId: result.export_id,
    status: 'done',
    progress: 1,
    error: null,
    durationSeconds: result.duration_seconds,
    width: 1080,
    height: 1920,
    fps: 30,
    overlayTraceStatus: trace ? (trace.verdict === 'fail' ? 'fail' : 'pass') : null,
    videoUrl: result.video_url,
    traceUrl: null,
  };
}
