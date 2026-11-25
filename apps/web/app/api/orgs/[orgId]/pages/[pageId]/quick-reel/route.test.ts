import { afterEach, describe, expect, it, vi } from 'vitest';

import { POST as postHooks } from '../hooks/route';
import { POST as postBranches } from './branches/route';
import { POST as postCompose } from './compose/route';

const params = Promise.resolve({ orgId: 'org-1', pageId: 'page-1' });

describe('creative generation proxy routes', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it.each([
    ['hooks', postHooks, '/orgs/org-1/pages/page-1/hooks'],
    ['branches', postBranches, '/orgs/org-1/pages/page-1/quick-reel/branches'],
    ['compose', postCompose, '/orgs/org-1/pages/page-1/quick-reel/compose'],
  ])('forwards %s requests with their JSON body', async (_name, handler, apiPath) => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(
        Response.json({ source: 'llm' }, { headers: { 'x-request-id': 'req-1' } }),
      );

    const response = await handler(
      new Request('http://web.test/api', {
        method: 'POST',
        body: JSON.stringify({ topic: 'squat depth' }),
        headers: { 'x-actor-id': 'operator:test' },
      }),
      { params },
    );

    expect(response.status).toBe(200);
    expect(response.headers.get('x-request-id')).toBe('req-1');
    expect(await response.json()).toEqual({ source: 'llm' });
    expect(fetchMock).toHaveBeenCalledWith(
      `http://127.0.0.1:8000${apiPath}`,
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ topic: 'squat depth' }),
        headers: expect.objectContaining({
          'Content-Type': 'application/json',
          'X-Actor-Id': 'operator:test',
        }),
      }),
    );
  });

  it('relays API validation errors unchanged', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      Response.json({ detail: 'unknown structure option' }, { status: 422 }),
    );

    const response = await postCompose(new Request('http://web.test/api', { method: 'POST' }), {
      params,
    });

    expect(response.status).toBe(422);
    expect(await response.json()).toEqual({ detail: 'unknown structure option' });
  });
});
