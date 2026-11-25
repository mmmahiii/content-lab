import { describe, expect, it } from 'vitest';

import { branchSet, defaultSelection } from './fixtures.test-data';
import {
  allSelections,
  cardSelections,
  fillSelection,
  optionLabel,
  randomSelection,
  sameSelection,
  selectionKey,
} from './selection';

const seq = (...values: number[]) => {
  let i = 0;
  return () => values[i++ % values.length];
};

describe('selection helpers', () => {
  it('fills unchosen moments from the defaults', () => {
    expect(fillSelection({ energy: 'dramatic' }, defaultSelection)).toEqual({ ...defaultSelection, energy: 'dramatic' });
    expect(selectionKey(1, defaultSelection)).toBe('1|breakdown|chill|reveal');
    expect(optionLabel(branchSet, 'ending', 'part_two')).toBe('Part 2?');
  });

  it('enumerates every combination and the cards for a moment', () => {
    expect(allSelections(branchSet)).toHaveLength(27);
    const cards = cardSelections(branchSet, 'energy', { structure: 'mistake_fix' }, defaultSelection);
    expect(cards).toEqual([
      { structure: 'mistake_fix', energy: 'chill', ending: 'reveal' },
      { structure: 'mistake_fix', energy: 'punchy', ending: 'reveal' },
      { structure: 'mistake_fix', energy: 'dramatic', ending: 'reveal' },
    ]);
  });

  it('keeps chosen moments when surprising', () => {
    const s = randomSelection(branchSet, seq(0.99, 0.5, 0.1), { keep: { structure: 'secret_reveal' } });
    // Kept moments consume no random draws: energy gets 0.99, ending 0.5.
    expect(s).toEqual({ structure: 'secret_reveal', energy: 'dramatic', ending: 'part_two' });
  });

  it('a remix always differs from the current reel, even with an unlucky random source', () => {
    const stuck = () => 0; // would roll breakdown/chill/reveal forever
    const remix = randomSelection(branchSet, stuck, { avoid: defaultSelection });
    expect(sameSelection(remix, defaultSelection)).toBe(false);
    for (let i = 0; i < 50; i++) {
      expect(sameSelection(randomSelection(branchSet, Math.random, { avoid: defaultSelection }), defaultSelection)).toBe(false);
    }
  });
});
