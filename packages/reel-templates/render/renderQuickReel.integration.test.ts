/**
 * Real render through headless Chrome + FFmpeg. Opt-in (slow, needs a browser):
 *   RENDER_INTEGRATION=1 REMOTION_BROWSER_EXECUTABLE=/path/to/chrome-headless-shell pnpm test
 */
import { execFileSync } from 'node:child_process';
import { mkdtemp, readFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { quickReelFixtures } from '../src/fixtures';
import { loopWindow } from '../src/quickReel';
import { renderQuickReel } from './renderQuickReel';

const enabled = process.env.RENDER_INTEGRATION === '1';

describe.runIf(enabled)('renderQuickReel (real render)', () => {
  it('renders a 1080x1920 H.264 file whose length matches the timeline', async () => {
    const outDir = await mkdtemp(path.join(tmpdir(), 'quick-reel-it-'));
    // Two seconds of the dramatic reel keeps the test quick.
    const timeline = loopWindow(quickReelFixtures.dramatic, { startFrame: 0, endFrame: 60 });
    const result = await renderQuickReel({
      timeline: { ...timeline, showProgress: true },
      outDir,
      basename: 'it',
      browserExecutable: process.env.REMOTION_BROWSER_EXECUTABLE ?? null,
    });
    const probe = JSON.parse(
      execFileSync('ffprobe', [
        '-v', 'error', '-select_streams', 'v:0',
        '-show_entries', 'stream=codec_name,width,height,nb_frames,pix_fmt:format=duration',
        '-of', 'json', result.videoPath,
      ]).toString(),
    );
    expect(probe.streams[0]).toMatchObject({ codec_name: 'h264', width: 1080, height: 1920, pix_fmt: 'yuv420p' });
    expect(Number(probe.streams[0].nb_frames)).toBe(60);
    const trace = JSON.parse(await readFile(result.tracePath, 'utf8'));
    expect(trace.status).toBe('pass');
    expect(trace.overlays[0].font_family).toContain('Montserrat Reel');
  }, 240_000);
});
