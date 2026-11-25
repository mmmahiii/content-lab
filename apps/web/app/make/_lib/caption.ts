import type { ComposedReel, HookCandidate, Page } from './types';

const MAX_CAPTION = 2_200;

function hashtag(text: string): string | null {
  const tag = text
    .normalize('NFKD')
    .replace(/[^\p{L}\p{N}\s]/gu, '')
    .split(/\s+/)
    .filter(Boolean)
    .map((w, i) => (i === 0 ? w.toLowerCase() : w[0].toUpperCase() + w.slice(1).toLowerCase()))
    .join('');
  return tag.length >= 2 && tag.length <= 40 ? `#${tag.toLowerCase()}` : null;
}

/**
 * Ready-to-post caption from the composed reel: the spoken hook, the on-screen beats as a
 * skimmable list, the closing line, and a few honest hashtags (topic + niche). Nothing is
 * invented beyond what the reel says.
 */
export function buildCaption(opts: {
  hook: HookCandidate;
  composed: ComposedReel;
  page: Pick<Page, 'metadata'> | null;
  topic: string;
}): string {
  const { hook, composed } = opts;
  const scenes = composed.scenes;
  const middle = scenes.slice(1, -1).map((scene) => scene.overlay_text.trim());
  const closing = scenes.at(-1);
  const lines: string[] = [hook.spoken_line.trim(), ''];
  middle.forEach((text) => lines.push(`→ ${text}`));
  if (closing) {
    lines.push('', closing.overlay_role === 'disclosure' ? closing.overlay_text : closing.narration);
  }
  const tags = [opts.topic, opts.page?.metadata?.niche ?? '']
    .map((t) => (t ? hashtag(t) : null))
    .filter((t): t is string => t !== null);
  const unique = [...new Set(tags)];
  if (unique.length) lines.push('', unique.join(' '));
  return lines.join('\n').trim().slice(0, MAX_CAPTION);
}
