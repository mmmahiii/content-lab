import { describe, expect, it } from 'vitest';
import { ENERGY_STYLES } from './energy';
import {
  captionGeometry,
  layoutMode,
  rectInside,
  rectsOverlap,
  safeRect,
  visualBand,
  type LayoutMode,
} from './geometry';
import { fakeMeasure } from './test-utils';
import { ENERGIES, type OverlayRole } from './timeline';

// Longest copy the API allows: hooks 72 chars / 12 words, beats 56 chars / 9 words.
const LONGEST: Record<OverlayRole, string> = {
  hook: 'What nobody tells you about crispy potatoes before the oven is preheated',
  value: 'Toss them in the hot oil before they hit the baking tray',
  cta: 'Save this one and try it with tonight dinner for real',
  disclosure: 'Paid partnership with a kitchen brand we really use',
};

const ctx = (mode: LayoutMode, energy = ENERGIES[1]) => ({
  width: 1080,
  height: 1920,
  mode,
  style: ENERGY_STYLES[energy],
  fontFamily: 'Test',
  measure: fakeMeasure,
});

describe('captionGeometry', () => {
  it('picks the layout from the visuals', () => {
    expect(layoutMode({ visuals: [] })).toBe('text');
    expect(layoutMode({ visuals: [{ startFrame: 0, endFrame: 1 }] })).toBe('text');
    expect(layoutMode({ visuals: [{ src: 'a.png', startFrame: 0, endFrame: 1 }] })).toBe('cutout');
    expect(
      layoutMode({ visuals: [{ src: 'a.jpg', fit: 'cover', startFrame: 0, endFrame: 1 }] }),
    ).toBe('cover');
  });

  it.each(['text', 'cutout', 'cover'] as LayoutMode[])(
    'keeps the longest allowed copy inside the safe area in %s layout, for every energy',
    (mode) => {
      const safe = safeRect(1080, 1920);
      for (const energy of ENERGIES) {
        for (const role of Object.keys(LONGEST) as OverlayRole[]) {
          const g = captionGeometry({ role, text: LONGEST[role] }, ctx(mode, energy));
          expect(rectInside(g.box, safe), `${mode}/${energy}/${role}`).toBe(true);
          expect(g.lines.flatMap((l) => l.words).join(' ')).toBe(LONGEST[role]);
          expect(g.fontSize).toBeGreaterThanOrEqual(36);
        }
      }
    },
  );

  it('never puts cut-out captions on top of the visual band', () => {
    const band = visualBand(1080, 1920);
    for (const role of Object.keys(LONGEST) as OverlayRole[]) {
      const g = captionGeometry({ role, text: LONGEST[role] }, ctx('cutout'));
      expect(rectsOverlap(g.box, band), role).toBe(false);
    }
  });

  it('centres lines inside the box and stacks them on the line height', () => {
    const g = captionGeometry({ role: 'hook', text: LONGEST.hook }, ctx('text'));
    expect(g.lines.length).toBeGreaterThan(1);
    g.lines.forEach((line, i) => {
      const centre = line.left + line.width / 2;
      expect(centre).toBeCloseTo(g.box.left + g.box.width / 2, 5);
      expect(line.top).toBeCloseTo(g.box.top + g.insetY + i * g.lineHeightPx, 5);
    });
    expect(g.box.height).toBeCloseTo(g.lines.length * g.lineHeightPx + 2 * g.insetY, 5);
  });

  it('uppercases value captions only for energies that shout', () => {
    const punchy = captionGeometry({ role: 'value', text: 'Step one' }, ctx('text', 'punchy'));
    const chill = captionGeometry({ role: 'value', text: 'Step one' }, ctx('text', 'chill'));
    expect(punchy.displayText).toBe('STEP ONE');
    expect(chill.displayText).toBe('Step one');
  });

  it('measures dramatic letter spacing so wide headlines still fit', () => {
    const dramatic = captionGeometry({ role: 'hook', text: LONGEST.hook }, ctx('text', 'dramatic'));
    const punchy = captionGeometry({ role: 'hook', text: LONGEST.hook }, ctx('text', 'punchy'));
    expect(dramatic.letterSpacingEm).toBeGreaterThan(0);
    expect(dramatic.fontSize).toBeLessThanOrEqual(punchy.fontSize);
  });
});
