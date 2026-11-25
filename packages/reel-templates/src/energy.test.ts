import { describe, expect, it } from 'vitest';
import { BASE_STYLE, captionExitFrames, ENERGY_STYLES, energyStyle, shakeOffset } from './energy';
import { ENERGIES } from './timeline';

describe('energy styles', () => {
  it('keeps the original proof look when a timeline has no energy', () => {
    expect(energyStyle(undefined)).toBe(BASE_STYLE);
  });

  it('gives every energy a visibly different motion and palette', () => {
    const fingerprints = ENERGIES.map((e) => {
      const s = ENERGY_STYLES[e];
      return JSON.stringify([s.wordStagger, s.exitFrames, s.accent, s.backdrop]);
    });
    expect(new Set(fingerprints).size).toBe(ENERGIES.length);
  });

  it('orders pacing chill/dramatic slower than punchy', () => {
    expect(ENERGY_STYLES.punchy.wordStagger).toBeLessThan(ENERGY_STYLES.chill.wordStagger);
    expect(ENERGY_STYLES.punchy.exitFrames).toBeLessThan(ENERGY_STYLES.dramatic.exitFrames);
    expect(ENERGY_STYLES.dramatic.letterboxPx).toBeGreaterThan(0);
    expect(ENERGY_STYLES.punchy.flash).toBeGreaterThan(0);
    expect(ENERGY_STYLES.chill.shakePx).toBe(0);
  });

  it('shake decays to rest within a quarter second', () => {
    expect(shakeOffset(0, 10, 30)).toBe(0);
    expect(Math.abs(shakeOffset(2, 10, 30))).toBeGreaterThan(0);
    expect(shakeOffset(8, 10, 30)).toBe(0);
    expect(shakeOffset(3, 0, 30)).toBe(0);
  });

  it('never lets a caption spend more than a third of its time fading out', () => {
    expect(captionExitFrames(90, ENERGY_STYLES.dramatic)).toBe(12);
    expect(captionExitFrames(18, ENERGY_STYLES.dramatic)).toBe(6);
  });
});
