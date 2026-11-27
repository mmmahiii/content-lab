import { describe, expect, it } from 'vitest';

import { doneView } from './useExport';

describe('doneView', () => {
  it('maps an export result to the render job the Ship screen shows', () => {
    const view = doneView({
      export_id: 'a'.repeat(20),
      status: 'warn',
      video_url: '/api/orgs/o/quick-reel/renders/aaaaaaaaaaaaaaaaaaaa/file',
      duration_seconds: 16,
      checks: [{ gate_name: 'package_overlay_render_trace', verdict: 'pass' }],
    });
    expect(view).toMatchObject({
      renderId: 'a'.repeat(20),
      status: 'done',
      progress: 1,
      durationSeconds: 16,
      overlayTraceStatus: 'pass',
      videoUrl: '/api/orgs/o/quick-reel/renders/aaaaaaaaaaaaaaaaaaaa/file',
    });
  });
});
