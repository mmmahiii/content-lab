import { describe, expect, it } from 'vitest';

import { topicSuggestions } from './suggestions';

describe('topicSuggestions', () => {
  it('puts the page content pillars first, then niche ideas, without duplicates', () => {
    const s = topicSuggestions({ metadata: { niche: 'cooking', persona: { content_pillars: ['Crispy potatoes', 'weeknight dinners'] } } });
    expect(s).toEqual(['Crispy potatoes', 'weeknight dinners', '5-minute pasta', 'knife skills']);
  });

  it('falls back to generic ideas for an unknown niche or no page', () => {
    expect(topicSuggestions({ metadata: { niche: 'pottery' } })).toHaveLength(4);
    expect(topicSuggestions(null)[0]).toBe('a beginner mistake');
  });
});
