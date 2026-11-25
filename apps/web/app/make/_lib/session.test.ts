import { describe, expect, it, vi } from 'vitest';

import type { QuickReelApi } from './api';
import { branchResult, composedFor, hooks } from './fixtures.test-data';
import { QuickReelSession } from './session';
import type { Selection } from './types';

function fakeApi() {
  let inFlight = 0;
  let maxInFlight = 0;
  const api = {
    hooks: vi.fn(async () => ({ hooks, source: 'fallback' as const, niche: 'cooking' })),
    branches: vi.fn(async (_o: string, _p: string, { hook }: { hook: (typeof hooks)[number] }) => ({ ...branchResult, hook })),
    compose: vi.fn(async (_o: string, _p: string, { selection }: { selection: Selection; hook?: unknown }) => {
      inFlight += 1;
      maxInFlight = Math.max(maxInFlight, inFlight);
      await new Promise((r) => setTimeout(r, 1));
      inFlight -= 1;
      return composedFor(selection);
    }),
  };
  return { api: api as unknown as QuickReelApi, calls: api, maxInFlight: () => maxInFlight };
}

const context = { orgId: 'o', pageId: 'p', topic: 'crispy potatoes', assetLabels: ['basil'] };
const settle = () => new Promise((r) => setTimeout(r, 30));

describe('QuickReelSession', () => {
  it('fetches branches for every hook as soon as hooks arrive', async () => {
    const { api, calls } = fakeApi();
    const session = new QuickReelSession(api, context);
    await session.hooks();
    await settle();
    expect(calls.hooks).toHaveBeenCalledWith('o', 'p', { topic: 'crispy potatoes', asset_labels: ['basil'] });
    expect(calls.branches).toHaveBeenCalledTimes(3);
    expect(session.peekBranches(2)?.hook.overlay_text).toBe(hooks[2].overlay_text);
  });

  it('starts on the punchy energy and pre-composes the hook and every structure card', async () => {
    const { api } = fakeApi();
    const session = new QuickReelSession(api, context);
    await session.hooks();
    await settle();
    expect(session.defaults(0)).toEqual({ structure: 'breakdown', energy: 'punchy', ending: 'reveal' });
    expect(session.activeReel(0, {})?.selection.energy).toBe('punchy');
    for (const structure of ['breakdown', 'mistake_fix', 'secret_reveal']) {
      expect(session.peekCompose(0, { structure, energy: 'punchy', ending: 'reveal' })).toBeDefined();
    }
    // The API's own preview (its default selection) is cached without a compose call.
    expect(session.peekCompose(0, branchResult.default_selection)).toBe(branchResult.preview);
  });

  it('composes each combination once, a few at a time, and notifies subscribers', async () => {
    const { api, calls, maxInFlight } = fakeApi();
    const session = new QuickReelSession(api, context, 3);
    const listener = vi.fn();
    session.subscribe(listener);
    await session.hooks();
    await session.prefetchAll(1, {});
    await session.prefetchAll(1, {});
    const keys = calls.compose.mock.calls.filter(([, , body]) => body.hook === hooks[1]).map(([, , body]) => JSON.stringify(body.selection));
    expect(new Set(keys).size).toBe(keys.length);
    // 27 combinations minus the API's preview, which never needs a call.
    expect(keys).toHaveLength(26);
    expect(maxInFlight()).toBeLessThanOrEqual(3);
    expect(listener).toHaveBeenCalled();
    expect(session.getVersion()).toBeGreaterThan(0);
  });

  it('retries a failed request on the next ask instead of caching the failure', async () => {
    const { api, calls } = fakeApi();
    const session = new QuickReelSession(api, context);
    await session.hooks();
    await settle();
    calls.compose.mockRejectedValueOnce(new Error('boom'));
    const selection = { structure: 'mistake_fix', energy: 'dramatic', ending: 'save_it' };
    await expect(session.compose(0, selection)).rejects.toThrow('boom');
    await expect(session.compose(0, selection)).resolves.toMatchObject({ selection });
  });
});
