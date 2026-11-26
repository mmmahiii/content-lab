import type { QuickReelVisual } from '@content-lab/reel-templates';

import type { AssetLibraryItem, AssetPack, Page } from './types';

export interface PageVisuals {
  /** For the Player and the render (same-origin proxy URLs, stable, no expiry). */
  visuals: QuickReelVisual[];
  /** For Send to Review (stored by id, not URL). */
  assets: Array<{ asset_id: string; fit: 'cutout' | 'cover' }>;
  /** Handed to the hook / branch generators so copy only promises what we can show. */
  labels: string[];
  packName: string | null;
}

export const NO_VISUALS: PageVisuals = { visuals: [], assets: [], labels: [], packName: null };

const MAX_VISUALS = 6;
const UNUSABLE_PACK = new Set(['failed', 'rejected', 'planned', 'generating']);

const norm = (s: string | null | undefined) => (s ?? '').trim().toLowerCase();

/**
 * Asset packs belong to the org, not the page; a pack is the page's when its niche matches
 * the page niche. Other niches' packs are never used (cooking photos on a fitness page would
 * be worse than the gradient backdrop).
 */
export function packsForPage(page: Pick<Page, 'metadata'>, packs: AssetPack[]): AssetPack[] {
  const niche = norm(page.metadata?.niche ?? null);
  if (!niche) return [];
  return packs.filter(
    (pack) => norm(pack.niche) === niche && !UNUSABLE_PACK.has(norm(pack.status)) && pack.actual_asset_count > 0,
  );
}

export function isImage(asset: AssetLibraryItem): boolean {
  const media = norm(asset.media_type);
  const kind = norm(asset.asset_kind);
  return (
    media.startsWith('image') ||
    ['image', 'png', 'jpg', 'jpeg', 'webp'].includes(media) ||
    kind === 'image' ||
    kind === 'cutout' ||
    norm(asset.asset_class) === 'image'
  );
}

function label(asset: AssetLibraryItem): string | null {
  const meta = asset.metadata ?? {};
  for (const key of ['label', 'title', 'name', 'subject', 'display_name']) {
    const value = meta[key];
    if (typeof value === 'string' && value.trim()) return value.trim().slice(0, 80);
  }
  return asset.tags[0]?.slice(0, 80) ?? null;
}

/** Long side of the image copies used in previews and renders (the frame is 1080x1920). */
export const VISUAL_MAX_PX = 1080;

export function pageVisuals(orgId: string, pack: AssetPack, assets: AssetLibraryItem[]): PageVisuals {
  const usable = assets
    .filter((a) => isImage(a) && !['failed', 'rejected', 'archived'].includes(norm(a.ready_status)))
    .slice(0, MAX_VISUALS);
  if (usable.length === 0) return NO_VISUALS;
  const fit = (a: AssetLibraryItem): 'cutout' | 'cover' =>
    a.has_transparency === false ? 'cover' : 'cutout';
  return {
    // The API's cached 1080 px copy: full-size pack PNGs (2.6-14 MB) made renders ~70 s.
    visuals: usable.map((a) => ({
      src: `/api/orgs/${orgId}/assets/${a.id}/file?max_px=${VISUAL_MAX_PX}`,
      fit: fit(a),
    })),
    assets: usable.map((a) => ({ asset_id: a.id, fit: fit(a) })),
    labels: [...new Set(usable.map(label).filter((l): l is string => l !== null))],
    packName: pack.name,
  };
}
