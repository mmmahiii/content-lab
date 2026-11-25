import { MONTSERRAT_WOFF2 } from './fonts/montserrat-data';

/**
 * The reel typeface, self-hosted (no Google Fonts request) so the Player, the headless
 * render tab and the render trace all measure and draw the exact same glyphs, offline.
 */
const FAMILY = 'Montserrat Reel';
export const REEL_FONT_FAMILY = `"${FAMILY}", Montserrat, sans-serif`;

let loading: Promise<void> | null = null;

export function waitForReelFont(): Promise<void> {
  if (typeof document === 'undefined' || typeof FontFace === 'undefined') {
    return Promise.resolve();
  }
  loading ??= Promise.all(
    (Object.keys(MONTSERRAT_WOFF2) as Array<keyof typeof MONTSERRAT_WOFF2>).map((weight) => {
      const face = new FontFace(FAMILY, `url(data:font/woff2;base64,${MONTSERRAT_WOFF2[weight]})`, {
        weight,
        style: 'normal',
      });
      document.fonts.add(face);
      return face.load();
    }),
  ).then(() => undefined);
  return loading;
}

// Start loading as soon as the module is imported in a browser.
void waitForReelFont();
