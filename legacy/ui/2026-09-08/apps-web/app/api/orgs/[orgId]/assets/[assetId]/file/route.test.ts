import { afterEach, describe, expect, it, vi } from 'vitest';

import { GET } from './route';

describe('asset file route', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('streams signed asset bytes through the same-origin route', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(
        Response.json({
          url: 'http://localhost:9000/content-lab/assets/demo.png?X-Amz-Signature=signed',
        }),
      )
      .mockResolvedValueOnce(
        new Response('image-bytes', {
          status: 200,
          headers: {
            'content-length': '11',
            'content-type': 'image/png',
          },
        }),
      );

    const response = await GET(new Request('http://web.test/api/file'), {
      params: Promise.resolve({ orgId: 'org-1', assetId: 'asset-1' }),
    });

    expect(response.status).toBe(200);
    expect(response.headers.get('content-type')).toBe('image/png');
    expect(response.headers.get('location')).toBeNull();
    expect(await response.text()).toBe('image-bytes');
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      'http://localhost:9000/content-lab/assets/demo.png?X-Amz-Signature=signed',
      expect.objectContaining({ method: 'GET' }),
    );
  });
});
