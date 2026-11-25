import { measureText } from '@remotion/layout-utils';

export interface TextLayout {
  fontSize: number;
  lines: string[][];
}

export interface MeasureInput {
  text: string;
  fontFamily: string;
  fontWeight: string;
  fontSize: number;
  letterSpacingEm: number;
  textTransform: 'none' | 'uppercase';
}

/** Returns the rendered width in px of `text`. Injected in tests; the DOM in browsers. */
export type MeasureFn = (input: MeasureInput) => number;

/** Browser measurement via @remotion/layout-utils (DOM-based, so only works in a browser). */
export const domMeasure: MeasureFn = (input) =>
  measureText({
    text: input.text,
    fontFamily: input.fontFamily,
    fontWeight: input.fontWeight,
    fontSize: input.fontSize,
    letterSpacing: `${input.letterSpacingEm}em`,
    textTransform: input.textTransform,
  }).width;

export interface LayoutTextOptions {
  text: string;
  fontFamily: string;
  fontWeight: string;
  /** Width available to the text block, including its horizontal inset. */
  boxWidth: number;
  maxLines: number;
  maxSize: number;
  minSize: number;
  letterSpacingEm?: number;
  /** Measure what is actually drawn: an uppercased caption is wider than its source text. */
  textTransform?: 'none' | 'uppercase';
  /** Horizontal inset per side, in em (box padding or highlight bleed). */
  insetEm?: number;
  /** Gap between words, in em. Matches the flex `gap` used when rendering. */
  gapEm?: number;
  /** Line height as a multiple of the font size (for the height check). */
  lineHeight?: number;
  /** Vertical inset per side, in em (box padding). */
  insetYEm?: number;
  /** Maximum block height in px including vertical insets. Omit for no height limit. */
  maxHeight?: number;
  measure?: MeasureFn;
}

/** Height in px of a wrapped text block (lines plus vertical insets). */
export function blockHeight(
  lineCount: number,
  fontSize: number,
  lineHeight: number,
  insetYEm: number,
): number {
  return lineCount * fontSize * lineHeight + 2 * insetYEm * fontSize;
}

/**
 * Wrap `text` into at most `maxLines` lines that fit `boxWidth` (and `maxHeight`, when
 * given), choosing the largest font size in [minSize, maxSize]. Never truncates: if the text
 * cannot fit at `minSize`, it throws so the plan has to change instead of silently clipping
 * copy.
 */
export function layoutText(opts: LayoutTextOptions): TextLayout {
  const measure = opts.measure ?? domMeasure;
  const words = opts.text.split(/\s+/).filter(Boolean);
  const ref = 100;
  const letterSpacingEm = opts.letterSpacingEm ?? 0;
  const textTransform = opts.textTransform ?? 'none';
  const at = (t: string) =>
    measure({
      text: t,
      fontFamily: opts.fontFamily,
      fontWeight: opts.fontWeight,
      fontSize: ref,
      letterSpacingEm,
      textTransform,
    });
  const wordWidths = words.map(at);
  const gapRef = opts.gapEm === undefined ? at('a a') - at('aa') : opts.gapEm * ref;
  const insetEm = opts.insetEm ?? 0;
  const lineHeight = opts.lineHeight ?? 1.08;
  const insetYEm = opts.insetYEm ?? 0;

  for (let size = opts.maxSize; size >= opts.minSize; size -= 2) {
    const k = size / ref;
    const available = opts.boxWidth - 2 * insetEm * size;
    const lines: string[][] = [];
    let current: string[] = [];
    let width = 0;
    let fits = available > 0;
    words.forEach((word, i) => {
      const w = wordWidths[i] * k;
      if (w > available) fits = false;
      const next = current.length === 0 ? w : width + gapRef * k + w;
      if (current.length > 0 && next > available) {
        lines.push(current);
        current = [word];
        width = w;
      } else {
        current.push(word);
        width = next;
      }
    });
    if (current.length) lines.push(current);
    const tallEnough =
      opts.maxHeight === undefined ||
      blockHeight(lines.length, size, lineHeight, insetYEm) <= opts.maxHeight;
    if (fits && lines.length <= opts.maxLines && tallEnough) {
      return { fontSize: size, lines: balanceLines(words, wordWidths, gapRef, lines.length) };
    }
  }
  throw new Error(
    `"${opts.text}" cannot fit ${opts.maxLines} line(s) of ${opts.boxWidth}px at ${opts.minSize}px`,
  );
}

/**
 * Re-split `words` into exactly `count` lines so the widest line is as narrow as possible
 * (like CSS `text-wrap: balance`): avoids a lone orphan word under a full line. Widths are at
 * the reference size; the result never has a wider line than greedy wrapping did.
 */
export function balanceLines(
  words: string[],
  widths: number[],
  gap: number,
  count: number,
): string[][] {
  const n = words.length;
  if (count <= 1 || n <= count) {
    return count <= 1 ? [words] : words.map((w) => [w]);
  }
  const width = (from: number, to: number) => {
    let total = 0;
    for (let i = from; i < to; i++) total += widths[i];
    return total + gap * (to - from - 1);
  };
  // best[k][i]: minimal widest line splitting the first i words into k lines.
  const best: number[][] = Array.from({ length: count + 1 }, () => Array(n + 1).fill(Infinity));
  const cut: number[][] = Array.from({ length: count + 1 }, () => Array(n + 1).fill(0));
  best[0][0] = 0;
  for (let k = 1; k <= count; k++) {
    for (let i = k; i <= n; i++) {
      for (let j = k - 1; j < i; j++) {
        const value = Math.max(best[k - 1][j], width(j, i));
        if (value < best[k][i]) {
          best[k][i] = value;
          cut[k][i] = j;
        }
      }
    }
  }
  const lines: string[][] = [];
  let end = n;
  for (let k = count; k >= 1; k--) {
    const start = cut[k][end];
    lines.unshift(words.slice(start, end));
    end = start;
  }
  return lines;
}

/** Width in px of one laid-out line, using the same gap the renderer uses. */
export function lineWidth(
  words: string[],
  opts: Pick<
    LayoutTextOptions,
    'fontFamily' | 'fontWeight' | 'letterSpacingEm' | 'textTransform' | 'gapEm' | 'measure'
  > & { fontSize: number },
): number {
  const measure = opts.measure ?? domMeasure;
  const base = {
    fontFamily: opts.fontFamily,
    fontWeight: opts.fontWeight,
    fontSize: opts.fontSize,
    letterSpacingEm: opts.letterSpacingEm ?? 0,
    textTransform: opts.textTransform ?? 'none',
  } as const;
  const gap =
    opts.gapEm === undefined
      ? measure({ ...base, text: 'a a' }) - measure({ ...base, text: 'aa' })
      : opts.gapEm * opts.fontSize;
  const total = words.reduce((sum, word) => sum + measure({ ...base, text: word }), 0);
  return total + gap * Math.max(0, words.length - 1);
}
