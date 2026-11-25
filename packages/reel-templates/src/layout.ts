import { measureText } from '@remotion/layout-utils';

export interface TextLayout {
  fontSize: number;
  lines: string[][];
}

/**
 * Wrap `text` into at most `maxLines` lines that fit `boxWidth`, choosing the largest
 * font size in [minSize, maxSize]. Never truncates: if the text cannot fit at
 * `minSize`, it throws so the plan has to change instead of silently clipping copy.
 */
export function layoutText(opts: {
  text: string;
  fontFamily: string;
  fontWeight: string;
  boxWidth: number;
  maxLines: number;
  maxSize: number;
  minSize: number;
  letterSpacingEm?: number;
}): TextLayout {
  const words = opts.text.split(/\s+/).filter(Boolean);
  const ref = 100;
  const measure = (t: string) =>
    measureText({
      text: t,
      fontFamily: opts.fontFamily,
      fontWeight: opts.fontWeight,
      fontSize: ref,
      letterSpacing: `${opts.letterSpacingEm ?? 0}em`,
    }).width;
  const wordWidths = words.map(measure);
  const spaceWidth = measure('a a') - measure('aa');

  for (let size = opts.maxSize; size >= opts.minSize; size -= 2) {
    const k = size / ref;
    const lines: string[][] = [];
    let current: string[] = [];
    let width = 0;
    let fits = true;
    words.forEach((word, i) => {
      const w = wordWidths[i] * k;
      if (w > opts.boxWidth) fits = false;
      const next = current.length === 0 ? w : width + spaceWidth * k + w;
      if (current.length > 0 && next > opts.boxWidth) {
        lines.push(current);
        current = [word];
        width = w;
      } else {
        current.push(word);
        width = next;
      }
    });
    if (current.length) lines.push(current);
    if (fits && lines.length <= opts.maxLines) {
      return { fontSize: size, lines };
    }
  }
  throw new Error(
    `"${opts.text}" cannot fit ${opts.maxLines} line(s) of ${opts.boxWidth}px at ${opts.minSize}px`,
  );
}
