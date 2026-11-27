import type { ReelTimeline } from '@content-lab/reel-templates';

import type {
  AssetLibraryItem,
  AssetPack,
  BranchGenerationResult,
  BranchSet,
  ComposedReel,
  HookCandidate,
  HookGenerationResult,
  Org,
  Page,
  ReelOut,
  RenderJobView,
  Selection,
} from './types';

/** Target reel length handed to branches / compose (the energy choice stretches it). */
export const REEL_SECONDS = 15;

/** A stored FFmpeg export: its QA report plus where to fetch the MP4. */
export interface ExportResult {
  export_id: string;
  status: 'pass' | 'warn' | 'fail';
  video_url: string;
  duration_seconds: number;
  checks: Array<{ gate_name: string; verdict: string }>;
  timings?: Record<string, number>;
}

/** Voice + music for a composed reel (`src` is null when neither TTS nor music is enabled). */
export interface SoundtrackResult {
  soundtrack_id: string;
  src: string | null;
  duration_seconds: number;
  voiceover: { provider: string; mock: boolean } | null;
  music: { provider: string; mood: string } | null;
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

type Fetch = typeof fetch;

function detailOf(body: unknown, status: number): string {
  if (body && typeof body === 'object') {
    const detail = (body as { detail?: unknown; message?: unknown }).detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail) && detail[0] && typeof detail[0] === 'object') {
      const msg = (detail[0] as { msg?: unknown }).msg;
      if (typeof msg === 'string') return msg;
    }
    const message = (body as { message?: unknown }).message;
    if (typeof message === 'string') return message;
  }
  return `Request failed (${status})`;
}

async function request<T>(fetcher: Fetch, url: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetcher(url, {
      ...init,
      headers: { Accept: 'application/json', 'Content-Type': 'application/json', ...init?.headers },
    });
  } catch {
    throw new ApiError(0, 'Could not reach the Content Lab server.');
  }
  const text = await response.text();
  let body: unknown = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = null;
  }
  if (!response.ok) throw new ApiError(response.status, detailOf(body, response.status));
  return body as T;
}

const post = <T>(fetcher: Fetch, url: string, body: unknown) =>
  request<T>(fetcher, url, { method: 'POST', body: JSON.stringify(body) });

/** Browser client for the Next.js proxy routes (`/api/...`). */
export function createApi(fetcher: Fetch = (...args) => fetch(...args)) {
  const page = (orgId: string, pageId: string) => `/api/orgs/${orgId}/pages/${pageId}`;
  return {
    listOrgs: () => request<Org[]>(fetcher, '/api/orgs'),
    listPages: (orgId: string) => request<Page[]>(fetcher, `/api/orgs/${orgId}/pages`),
    listAssetPacks: (orgId: string) =>
      request<AssetPack[]>(fetcher, `/api/orgs/${orgId}/asset-packs`),
    listPackAssets: (orgId: string, packId: string) =>
      request<AssetLibraryItem[]>(
        fetcher,
        `/api/orgs/${orgId}/assets?asset_pack_id=${encodeURIComponent(packId)}&limit=24`,
      ),
    hooks: (
      orgId: string,
      pageId: string,
      body: { topic: string; asset_labels: string[]; count?: number },
    ) => post<HookGenerationResult>(fetcher, `${page(orgId, pageId)}/hooks`, { count: 3, ...body }),
    branches: (
      orgId: string,
      pageId: string,
      body: { hook: HookCandidate; topic: string; asset_labels: string[] },
    ) =>
      post<BranchGenerationResult>(fetcher, `${page(orgId, pageId)}/quick-reel/branches`, {
        duration_seconds: REEL_SECONDS,
        ...body,
      }),
    compose: (
      orgId: string,
      pageId: string,
      body: { hook: HookCandidate; branches: BranchSet; selection: Selection },
    ) =>
      post<ComposedReel>(fetcher, `${page(orgId, pageId)}/quick-reel/compose`, {
        duration_seconds: REEL_SECONDS,
        ...body,
      }),
    soundtrack: (
      orgId: string,
      pageId: string,
      body: { hook: HookCandidate; branches: BranchSet; selection: Selection },
    ) =>
      post<SoundtrackResult>(fetcher, `${page(orgId, pageId)}/quick-reel/soundtrack`, {
        duration_seconds: REEL_SECONDS,
        ...body,
      }),
    exportReel: (
      orgId: string,
      pageId: string,
      body: {
        hook: HookCandidate;
        branches: BranchSet;
        selection: Selection;
        visuals: Array<{ asset_id: string; fit: 'cutout' | 'cover' }>;
      },
    ) =>
      post<ExportResult>(fetcher, `${page(orgId, pageId)}/quick-reel/exports`, {
        duration_seconds: REEL_SECONDS,
        ...body,
      }),
    sendToReview: (orgId: string, pageId: string, body: Record<string, unknown>) =>
      post<ReelOut>(fetcher, `${page(orgId, pageId)}/quick-reel/reels`, {
        duration_seconds: REEL_SECONDS,
        ...body,
      }),
    startRender: (timeline: ReelTimeline, replaces?: string | null) =>
      post<RenderJobView>(fetcher, '/api/quick-reel/renders', { timeline, replaces: replaces ?? null }),
    getRender: (renderId: string) =>
      request<RenderJobView>(fetcher, `/api/quick-reel/renders/${renderId}`),
  };
}

export type QuickReelApi = ReturnType<typeof createApi>;
