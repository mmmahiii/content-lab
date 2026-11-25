import { describe, expect, it } from 'vitest';

import { buildCaption } from './caption';
import { composedFor, hook } from './fixtures.test-data';

describe('buildCaption', () => {
  const composed = composedFor({ structure: 'breakdown', energy: 'punchy', ending: 'reveal' });

  it('uses only what the reel says, plus topic and niche hashtags', () => {
    const caption = buildCaption({ hook, composed, page: { metadata: { niche: 'cooking' } }, topic: 'crispy potatoes' });
    const lines = caption.split('\n');
    expect(lines[0]).toBe(hook.spoken_line);
    expect(lines).toContain('→ Step 1: get ready');
    expect(lines).toContain("And that's the result.");
    expect(lines.at(-1)).toBe('#crispypotatoes #cooking');
  });

  it('ends with the disclosure when the page requires one', () => {
    const disclosed = structuredClone(composed);
    const last = disclosed.scenes.at(-1)!;
    last.overlay_role = 'disclosure';
    last.overlay_text = 'Paid partnership';
    const caption = buildCaption({ hook, composed: disclosed, page: null, topic: '5-minute pasta!' });
    expect(caption).toContain('Paid partnership');
    expect(caption.endsWith('#5minutepasta')).toBe(true);
  });

  it('stays within the 2,200 character platform limit', () => {
    const long = { ...hook, spoken_line: 'x'.repeat(3000) };
    expect(buildCaption({ hook: long, composed, page: null, topic: '' }).length).toBeLessThanOrEqual(2200);
  });
});
