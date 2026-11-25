/** Real fallback API payloads for tests (crispy potatoes, no LLM). */
import { quickReelComposed } from '@content-lab/reel-templates';

import type { BranchGenerationResult, BranchSet, ComposedReel, HookCandidate, Selection } from './types';

export const hook: HookCandidate = {
  mechanism: 'curiosity_gap',
  overlay_text: 'The crispy potatoes detail most people miss',
  spoken_line: "There's one crispy potatoes detail almost everyone skips.",
  visual_direction: 'Open on the clearest visual of crispy potatoes.',
  payoff_promise: 'Reveal the one detail clearly by the end.',
};

export const hooks: HookCandidate[] = [
  hook,
  { ...hook, mechanism: 'bold_claim', overlay_text: "You're doing crispy potatoes the hard way" },
  { ...hook, mechanism: 'visual_first', overlay_text: 'Watch this crispy potatoes come together' },
];

const beat = (overlay: string) => ({ narration: `${overlay}.`, overlay_text: overlay, shot_direction: 'Close-up', seconds: 3 });

export const branchSet: BranchSet = {
  structure: [
    { option_id: 'breakdown', label: 'Quick breakdown', teaser: 'Three clear steps', beats: [beat('Step 1'), beat('Step 2'), beat('Step 3')] },
    { option_id: 'mistake_fix', label: 'Mistake, then fix', teaser: 'The slip and the fix', beats: [beat('The mistake'), beat('The fix')] },
    { option_id: 'secret_reveal', label: 'Secret reveal', teaser: 'Build to the secret', beats: [beat('Not that'), beat('This')] },
  ],
  energy: [
    { option_id: 'chill', label: 'Chill & satisfying', teaser: 'Slow', pace: 'chill', duration_scale: 1.2, music_mood: 'lo-fi' },
    { option_id: 'punchy', label: 'Fast & punchy', teaser: 'Quick', pace: 'punchy', duration_scale: 0.8, music_mood: 'drums' },
    { option_id: 'dramatic', label: 'Dramatic', teaser: 'Build', pace: 'dramatic', duration_scale: 1.1, music_mood: 'strings' },
  ],
  ending: [
    { option_id: 'reveal', label: 'Big reveal', teaser: 'Result', style: 'reveal', beat: beat('The result') },
    { option_id: 'part_two', label: 'Part 2?', teaser: 'Tease', style: 'cliffhanger', beat: beat('Part 2 next?') },
    { option_id: 'save_it', label: 'Save it', teaser: 'Keep it', style: 'call_to_action', beat: beat('Save this one') },
  ],
};

export const defaultSelection: Selection = { structure: 'breakdown', energy: 'chill', ending: 'reveal' };

export function composedFor(selection: Selection): ComposedReel {
  const base = quickReelComposed[branchSet.energy.find((e) => e.option_id === selection.energy)!.pace];
  return { ...(base as unknown as ComposedReel), selection };
}

export const branchResult: BranchGenerationResult = {
  hook,
  moments: ['structure', 'energy', 'ending'],
  branches: branchSet,
  default_selection: defaultSelection,
  preview: composedFor(defaultSelection),
  source: 'fallback',
  niche: 'cooking',
};
