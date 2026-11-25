import type { MeasureFn } from './layout';

/**
 * Deterministic stand-in for browser glyph measurement in Node tests. Roughly Montserrat
 * Black proportions: wide capitals, narrower lowercase, spaces at ~0.28em.
 */
export const fakeMeasure: MeasureFn = ({ text, fontSize, letterSpacingEm, textTransform }) => {
  const shown = textTransform === 'uppercase' ? text.toUpperCase() : text;
  let em = 0;
  for (const ch of shown) {
    if (ch === ' ') em += 0.28;
    else if (/[A-Z]/.test(ch)) em += 0.8;
    else if (/[0-9]/.test(ch)) em += 0.7;
    else if (/[a-z]/.test(ch)) em += 0.64;
    else em += 0.4;
    em += letterSpacingEm;
  }
  return em * fontSize;
};
