import { expect, it } from 'vitest';
import { createFixtureState } from './fixtures';
import { buildPrototypeHandoff } from './prototype-handoff';
it('exports pinned representations and repeated instances despite a new current asset version', () => {
  const state = createFixtureState('portfolio', Date.parse('2026-09-09T12:00:00Z'));
  const pack = state.packages.find((p) => p.contentId === 'content-published')!;
  const before = buildPrototypeHandoff(state, pack);
  const visual = before.provenance.filter((p) => p.assetId === 'asset-mug');
  expect(visual.length).toBeGreaterThan(1);
  expect(new Set(visual.map((p) => p.instanceId)).size).toBe(visual.length);
  state.assets.find((a) => a.id === 'asset-mug')!.currentVersionId = 'future-version';
  expect(buildPrototypeHandoff(state, pack)).toEqual(before);
  expect(before.revision.id).toBe(pack.revisionId);
});
