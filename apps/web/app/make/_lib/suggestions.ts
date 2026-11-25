import type { Page } from './types';

const BY_NICHE: Record<string, string[]> = {
  cooking: ['crispy potatoes', '5-minute pasta', 'knife skills', 'one-pan dinner'],
  food: ['crispy potatoes', '5-minute pasta', 'knife skills', 'one-pan dinner'],
  fitness: ['squat depth', 'first pull-up', 'desk-job mobility', 'protein on a budget'],
  finance: ['emergency fund', 'first budget', 'credit score myths', 'saving on groceries'],
  beauty: ['5-minute makeup', 'skincare order', 'brow shaping', 'heat-free curls'],
  travel: ['carry-on packing', 'cheap flights', 'jet lag', 'hidden city spots'],
  business: ['cold outreach', 'pricing your work', 'weekly planning', 'first hire'],
  luxury: ['quiet luxury', 'watch care', 'capsule wardrobe', 'hotel upgrades'],
};

const GENERIC = ['a beginner mistake', 'one quick win', 'myth vs truth', 'before and after'];

/** Up to four one-tap topic ideas: the page's own content pillars first, then its niche. */
export function topicSuggestions(page: Pick<Page, 'metadata'> | null): string[] {
  const pillars = page?.metadata?.persona?.content_pillars ?? [];
  const niche = (page?.metadata?.niche ?? '').toString().trim().toLowerCase();
  const byNiche = Object.entries(BY_NICHE).find(([key]) => niche.includes(key))?.[1] ?? GENERIC;
  const seen = new Set<string>();
  return [...pillars, ...byNiche]
    .map((s) => s.trim())
    .filter((s) => s.length > 0 && s.length <= 60)
    .filter((s) => {
      const key = s.toLowerCase();
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .slice(0, 4);
}
