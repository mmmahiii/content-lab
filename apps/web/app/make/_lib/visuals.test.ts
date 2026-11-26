import { describe, expect, it } from 'vitest';

import type { AssetLibraryItem, AssetPack } from './types';
import { isImage, packsForPage, pageVisuals } from './visuals';

const pack = (over: Partial<AssetPack>): AssetPack => ({
  id: 'pack-1', name: 'Kitchen', niche: 'cooking', status: 'ready', actual_asset_count: 3, ...over,
});
const asset = (over: Partial<AssetLibraryItem>): AssetLibraryItem => ({
  id: 'a1', asset_class: 'image', asset_kind: 'cutout', media_type: 'image', tags: ['basil'],
  has_transparency: true, ready_status: 'ready', metadata: { label: 'basil' }, ...over,
});

describe('page visuals', () => {
  it('uses only packs whose niche matches the page, never another niche', () => {
    const packs = [
      pack({ id: 'cook' }),
      pack({ id: 'fit', niche: 'fitness' }),
      pack({ id: 'empty', actual_asset_count: 0 }),
      pack({ id: 'failed', status: 'failed' }),
    ];
    expect(packsForPage({ metadata: { niche: 'Cooking' } }, packs).map((p) => p.id)).toEqual(['cook']);
    expect(packsForPage({ metadata: { niche: 'travel' } }, packs)).toEqual([]);
    expect(packsForPage({ metadata: {} }, packs)).toEqual([]);
  });

  it('turns images into stable same-origin proxy URLs, by id, with a fit per transparency', () => {
    const out = pageVisuals('org-1', pack({}), [
      asset({ id: 'cut' }),
      asset({ id: 'photo', has_transparency: false, metadata: { title: 'tray of potatoes' } }),
      asset({ id: 'clip', asset_class: 'video', asset_kind: 'clip', media_type: 'video' }),
      asset({ id: 'bad', ready_status: 'failed' }),
    ]);
    expect(out.visuals).toEqual([
      { src: '/api/orgs/org-1/assets/cut/file?max_px=1080', fit: 'cutout' },
      { src: '/api/orgs/org-1/assets/photo/file?max_px=1080', fit: 'cover' },
    ]);
    expect(out.assets).toEqual([
      { asset_id: 'cut', fit: 'cutout' },
      { asset_id: 'photo', fit: 'cover' },
    ]);
    expect(out.labels).toEqual(['basil', 'tray of potatoes']);
    expect(out.packName).toBe('Kitchen');
  });

  it('falls back to no visuals (gradient) when a pack has no usable images', () => {
    const out = pageVisuals('org-1', pack({}), [asset({ asset_class: 'audio', asset_kind: 'music', media_type: 'audio' })]);
    expect(out.visuals).toEqual([]);
    expect(isImage(asset({ asset_kind: null, media_type: 'image/png', asset_class: 'x' }))).toBe(true);
  });
});
