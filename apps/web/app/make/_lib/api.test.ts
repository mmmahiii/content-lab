import { describe, expect, it, vi } from 'vitest';

import { ApiError, createApi, REEL_SECONDS } from './api';
import { hook } from './fixtures.test-data';

const ok = (body: unknown) => new Response(JSON.stringify(body), { status: 200 });

describe('Quick Reel API client', () => {
  it('posts hooks / branches / compose to the page proxy routes with the reel length', async () => {
    const fetcher = vi.fn(async () => ok({}));
    const api = createApi(fetcher as unknown as typeof fetch);
    await api.hooks('o', 'p', { topic: 't', asset_labels: [] });
    await api.branches('o', 'p', { hook, topic: 't', asset_labels: ['basil'] });
    const calls = fetcher.mock.calls as unknown as Array<[string, RequestInit]>;
    expect(calls[0][0]).toBe('/api/orgs/o/pages/p/hooks');
    expect(JSON.parse(String(calls[0][1].body))).toEqual({ count: 3, topic: 't', asset_labels: [] });
    expect(calls[1][0]).toBe('/api/orgs/o/pages/p/quick-reel/branches');
    expect(JSON.parse(String(calls[1][1].body)).duration_seconds).toBe(REEL_SECONDS);
  });

  it('turns API errors into readable messages', async () => {
    const api = createApi((async () =>
      new Response(JSON.stringify({ detail: 'unknown structure option' }), { status: 422 })) as unknown as typeof fetch);
    await expect(api.compose('o', 'p', { hook, branches: {} as never, selection: {} as never })).rejects.toEqual(
      new ApiError(422, 'unknown structure option'),
    );
    const validation = createApi((async () =>
      new Response(JSON.stringify({ detail: [{ msg: 'Field required' }] }), { status: 422 })) as unknown as typeof fetch);
    await expect(validation.listOrgs()).rejects.toThrow('Field required');
  });

  it('reports an unreachable server as status 0', async () => {
    const api = createApi((async () => {
      throw new TypeError('fetch failed');
    }) as unknown as typeof fetch);
    await expect(api.listOrgs()).rejects.toMatchObject({ status: 0, message: 'Could not reach the Content Lab server.' });
  });
});
