import { describe, expect, it } from 'vitest';
import { quickReelComposed, quickReelFixtures, quickReelHookText } from './fixtures';
import {
  assignVisuals,
  fromComposedReel,
  hookTimeline,
  loopWindow,
  previewWindow,
  quickReelSegments,
  sceneWindows,
} from './quickReel';

describe('fromComposedReel', () => {
  it('turns the compose response into a 30 fps 1080x1920 timeline on one clock', () => {
    const t = quickReelFixtures.punchy;
    expect(t.fps).toBe(30);
    expect([t.width, t.height]).toEqual([1080, 1920]);
    expect(t.durationInFrames).toBe(quickReelComposed.punchy.duration_seconds * 30);
    expect(t.energy).toBe('punchy');
    expect(t.overlays[0]).toMatchObject({ role: 'hook', text: quickReelHookText, startFrame: 0 });
    expect(t.overlays.at(-1)?.role).toBe('cta');
    expect(t.overlays.at(-1)?.endFrame).toBe(t.durationInFrames);
  });

  it('follows the energy: different lengths and backdrops per pace', () => {
    const lengths = new Set(Object.values(quickReelFixtures).map((t) => t.durationInFrames));
    const backdrops = new Set(Object.values(quickReelFixtures).map((t) => t.backdrop.join()));
    expect(lengths.size).toBe(3);
    expect(backdrops.size).toBe(3);
  });

  it('maps a page disclosure ending to the disclosure role', () => {
    const composed = structuredClone(quickReelComposed.chill);
    const last = composed.overlay_timeline.at(-1)!;
    last.emphasis = 'disclosure';
    last.text = 'Paid partnership';
    expect(fromComposedReel(composed).overlays.at(-1)?.role).toBe('disclosure');
  });

  it('gives each scene one visual, cycling through the pack', () => {
    const t = fromComposedReel(quickReelComposed.chill, {
      visuals: [{ src: '/a.png' }, { src: '/b.jpg', fit: 'cover' }],
    });
    const scenes = sceneWindows(quickReelComposed.chill);
    expect(t.visuals).toHaveLength(scenes.length);
    expect(t.visuals.map((v) => v.src)).toEqual(scenes.map((_, i) => (i % 2 ? '/b.jpg' : '/a.png')));
    expect(t.visuals.map((v) => [v.startFrame, v.endFrame])).toEqual(
      scenes.map((s) => [s.startFrame, s.endFrame]),
    );
    expect(assignVisuals(scenes, [])).toEqual([]);
  });
});

describe('quickReelSegments', () => {
  it('splits the reel at the three choice moments and covers it without gaps', () => {
    const composed = quickReelComposed.chill;
    const s = quickReelSegments(composed);
    expect(s.hook.startFrame).toBe(0);
    expect(s.firstBeat.startFrame).toBe(s.hook.endFrame);
    expect(s.restBeats.startFrame).toBe(s.firstBeat.endFrame);
    expect(s.ending.startFrame).toBe(s.restBeats.endFrame);
    expect(s.ending.endFrame).toBe(composed.duration_seconds * 30);
  });

  it('rejects a reel without enough story beats', () => {
    const composed = structuredClone(quickReelComposed.chill);
    composed.scenes = composed.scenes.slice(0, 3);
    expect(() => quickReelSegments(composed)).toThrow(/needs a hook/);
  });
});

describe('loop previews', () => {
  it('cuts a re-based window and hides the in-video progress bar', () => {
    const t = fromComposedReel(quickReelComposed.punchy, { visuals: [{ src: '/a.png' }] });
    const s = quickReelSegments(quickReelComposed.punchy);
    const w = previewWindow(s.firstBeat);
    const loop = loopWindow(t, w);
    expect(loop.durationInFrames).toBe(w.endFrame - w.startFrame);
    expect(loop.showProgress).toBe(false);
    expect(loop.overlays).toHaveLength(1);
    expect(loop.overlays[0]).toMatchObject({ startFrame: 0, text: t.overlays[1].text });
    expect(loop.visuals.every((v) => v.startFrame >= 0 && v.endFrame <= loop.durationInFrames)).toBe(true);
  });

  it('caps a preview at two seconds but never runs past its segment', () => {
    expect(previewWindow({ startFrame: 60, endFrame: 300 })).toEqual({ startFrame: 60, endFrame: 120 });
    expect(previewWindow({ startFrame: 60, endFrame: 90 })).toEqual({ startFrame: 60, endFrame: 90 });
    expect(() => loopWindow(quickReelFixtures.chill, { startFrame: 5, endFrame: 5 })).toThrow();
  });

  it('builds a standalone hook clip for the hook reel', () => {
    const t = hookTimeline('Watch this come together', { visuals: [{ src: '/a.png' }] });
    expect(t.durationInFrames).toBe(90);
    expect(t.overlays).toEqual([{ text: 'Watch this come together', role: 'hook', startFrame: 0, endFrame: 90 }]);
    expect(t.visuals).toHaveLength(1);
    expect(t.showProgress).toBe(false);
  });
});
