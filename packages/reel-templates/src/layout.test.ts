import { describe, expect, it } from 'vitest';
import { balanceLines, blockHeight, layoutText, lineWidth } from './layout';
import { fakeMeasure } from './test-utils';

const base = {
  fontFamily: 'Test',
  fontWeight: '900',
  boxWidth: 900,
  maxLines: 3,
  maxSize: 140,
  minSize: 50,
  gapEm: 0.24,
  measure: fakeMeasure,
};

describe('layoutText', () => {
  it('picks the largest size that fits and keeps every word', () => {
    const layout = layoutText({ ...base, text: 'Crispy potatoes in ten minutes' });
    expect(layout.fontSize).toBeLessThanOrEqual(140);
    expect(layout.lines.flat().join(' ')).toBe('Crispy potatoes in ten minutes');
    for (const line of layout.lines) {
      expect(lineWidth(line, { ...base, fontSize: layout.fontSize })).toBeLessThanOrEqual(900);
    }
    // One step bigger would not fit.
    expect(() => layoutText({ ...base, text: 'Crispy potatoes in ten minutes', minSize: layout.fontSize + 2 })).toThrow();
  });

  it('measures uppercase text, which is wider, so captions do not overflow', () => {
    const text = 'Step 2: the key move that matters';
    const plain = layoutText({ ...base, text, maxLines: 2 });
    const upper = layoutText({ ...base, text, maxLines: 2, textTransform: 'uppercase' });
    expect(upper.fontSize).toBeLessThan(plain.fontSize);
  });

  it('shrinks the available width by the horizontal inset', () => {
    const text = 'One clean move worth saving today';
    const open = layoutText({ ...base, text });
    const inset = layoutText({ ...base, text, insetEm: 0.5 });
    expect(inset.fontSize).toBeLessThan(open.fontSize);
  });

  it('respects a maximum block height', () => {
    const text = 'The crispy potatoes detail most people miss';
    const tall = layoutText({ ...base, text, maxLines: 4 });
    const capped = layoutText({ ...base, text, maxLines: 4, maxHeight: 260, lineHeight: 1.08 });
    expect(capped.fontSize).toBeLessThan(tall.fontSize);
    expect(blockHeight(capped.lines.length, capped.fontSize, 1.08, 0)).toBeLessThanOrEqual(260);
  });

  it('throws instead of truncating when copy cannot fit', () => {
    expect(() =>
      layoutText({ ...base, text: 'Supercalifragilisticexpialidocious', boxWidth: 300 }),
    ).toThrow(/cannot fit/);
  });
});

describe('balanceLines', () => {
  it('avoids an orphan word when the line count stays the same', () => {
    const words = ['STEP', '1:', 'GET', 'READY'];
    const widths = [310, 90, 230, 360];
    expect(balanceLines(words, widths, 24, 2)).toEqual([
      ['STEP', '1:'],
      ['GET', 'READY'],
    ]);
  });

  it('handles one line and more lines than words', () => {
    expect(balanceLines(['a', 'b'], [1, 1], 0, 1)).toEqual([['a', 'b']]);
    expect(balanceLines(['a', 'b'], [1, 1], 0, 3)).toEqual([['a'], ['b']]);
  });
});
