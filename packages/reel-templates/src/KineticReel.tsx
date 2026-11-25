import { loadFont } from '@remotion/google-fonts/Montserrat';
import { useEffect, useState } from 'react';
import {
  AbsoluteFill,
  Img,
  Sequence,
  continueRender,
  delayRender,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import { layoutText, type TextLayout } from './layout';
import type { OverlayRole, ReelTimeline, TimelineOverlay, TimelineVisual } from './timeline';

const { fontFamily, waitUntilDone } = loadFont('normal', {
  weights: ['800', '900'],
  subsets: ['latin'],
});

const ACCENT = '#FFD43B';

/** Vertical safe areas for 9:16 feeds (platform UI covers the top and bottom). */
const SAFE = { side: 90, top: 250, bottom: 420 };

/**
 * Layout bands so captions never cover the visual: hook text above, the visual in the
 * middle band, value/CTA captions below. Without visuals, value captions sit mid-screen.
 */
const VISUAL_BAND = { top: 700, height: 680 };

function roleStyle(role: OverlayRole, hasVisuals: boolean) {
  switch (role) {
    case 'hook':
      return { maxLines: 3, maxSize: 132, minSize: 60, weight: '900', top: SAFE.top };
    case 'value':
      return {
        maxLines: hasVisuals ? 2 : 3,
        maxSize: hasVisuals ? 110 : 150,
        minSize: 56,
        weight: '900',
        top: hasVisuals ? VISUAL_BAND.top + VISUAL_BAND.height + 30 : 1080,
      };
    case 'cta':
      return {
        maxLines: 2,
        maxSize: 96,
        minSize: 52,
        weight: '800',
        top: hasVisuals ? VISUAL_BAND.top + VISUAL_BAND.height + 40 : 1920 - SAFE.bottom - 220,
      };
  }
}

function useFontReady(): boolean {
  const [handle] = useState(() => delayRender('Loading Montserrat'));
  const [ready, setReady] = useState(false);
  useEffect(() => {
    waitUntilDone().then(() => {
      setReady(true);
      continueRender(handle);
    });
  }, [handle]);
  return ready;
}

export const KineticReel: React.FC<ReelTimeline> = (timeline) => {
  const ready = useFontReady();
  return (
    <AbsoluteFill
      style={{
        background: `linear-gradient(180deg, ${timeline.backdrop[0]}, ${timeline.backdrop[1]})`,
      }}
    >
      {timeline.visuals.map((visual) => (
        <Sequence
          key={`${visual.src}-${visual.startFrame}`}
          from={visual.startFrame}
          durationInFrames={visual.endFrame - visual.startFrame}
        >
          <CutoutVisual visual={visual} />
        </Sequence>
      ))}
      {timeline.visuals.length > 0 && <Vignette />}
      <ProgressBar timeline={timeline} />
      {ready &&
        timeline.overlays.map((overlay) => (
          <Sequence
            key={`${overlay.text}-${overlay.startFrame}`}
            from={overlay.startFrame}
            durationInFrames={overlay.endFrame - overlay.startFrame}
          >
            <Caption
              overlay={overlay}
              width={timeline.width}
              hasVisuals={timeline.visuals.length > 0}
            />
          </Sequence>
        ))}
    </AbsoluteFill>
  );
};

const CutoutVisual: React.FC<{ visual: TimelineVisual }> = ({ visual }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const length = visual.endFrame - visual.startFrame;
  const enter = spring({ frame, fps, config: { damping: 14, mass: 0.7 } });
  const drift = interpolate(frame, [0, length], [0, 1]);
  const exit = interpolate(frame, [length - 6, length], [1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  if (!visual.src) return null;
  return (
    <AbsoluteFill
      style={{
        top: VISUAL_BAND.top,
        height: VISUAL_BAND.height,
        alignItems: 'center',
        justifyContent: 'center',
        opacity: exit,
      }}
    >
      <Img
        src={staticFile(visual.src)}
        style={{
          maxWidth: '82%',
          // Leave headroom for the 8% drift scale so the visual stays inside its band.
          maxHeight: '90%',
          objectFit: 'contain',
          transform: `translateY(${(1 - enter) * 120}px) scale(${
            (0.85 + enter * 0.15) * (1 + drift * 0.08)
          }) rotate(${(1 - enter) * -6 + drift * 2}deg)`,
          filter: 'drop-shadow(0 40px 60px rgba(0,0,0,0.55))',
        }}
      />
    </AbsoluteFill>
  );
};

const Vignette: React.FC = () => (
  <AbsoluteFill
    style={{
      background:
        'radial-gradient(ellipse at 50% 45%, rgba(0,0,0,0) 45%, rgba(0,0,0,0.55) 100%)',
    }}
  />
);

const ProgressBar: React.FC<{ timeline: ReelTimeline }> = ({ timeline }) => {
  const frame = useCurrentFrame();
  return (
    <div
      style={{
        position: 'absolute',
        top: 150,
        left: SAFE.side,
        right: SAFE.side,
        display: 'flex',
        gap: 10,
      }}
    >
      {timeline.overlays.map((o) => {
        const p = interpolate(frame, [o.startFrame, o.endFrame], [0, 1], {
          extrapolateLeft: 'clamp',
          extrapolateRight: 'clamp',
        });
        return (
          <div
            key={o.startFrame}
            style={{ flex: 1, height: 8, borderRadius: 4, background: 'rgba(255,255,255,0.28)' }}
          >
            <div
              style={{
                width: `${p * 100}%`,
                height: '100%',
                borderRadius: 4,
                background: '#fff',
              }}
            />
          </div>
        );
      })}
    </div>
  );
};

const Caption: React.FC<{ overlay: TimelineOverlay; width: number; hasVisuals: boolean }> = ({
  overlay,
  width,
  hasVisuals,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const style = roleStyle(overlay.role, hasVisuals);
  const length = overlay.endFrame - overlay.startFrame;
  const boxWidth = width - SAFE.side * 2 - (overlay.role === 'hook' ? 0 : 80);

  const layout: TextLayout = layoutText({
    text: overlay.text,
    fontFamily,
    fontWeight: style.weight,
    boxWidth,
    maxLines: style.maxLines,
    maxSize: style.maxSize,
    minSize: style.minSize,
  });

  const exit = interpolate(frame, [length - 5, length], [1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const allWords = layout.lines.flat();
  const accentIndex = pickAccentWord(allWords);
  let wordIndex = 0;

  const words = layout.lines.map((line, li) => (
    <div key={li} style={{ display: 'flex', justifyContent: 'center', gap: '0.24em' }}>
      {line.map((word) => {
        const i = wordIndex++;
        const delay = overlay.role === 'hook' ? i * 3 : 0;
        const pop = spring({
          frame: frame - delay,
          fps,
          config: { damping: 11, mass: 0.5, stiffness: 180 },
        });
        const isAccent = overlay.role === 'hook' && i === accentIndex;
        return (
          <span
            key={i}
            style={{
              display: 'inline-block',
              transform: `translateY(${(1 - pop) * 40}px) scale(${0.6 + pop * 0.4})`,
              opacity: Math.min(1, pop * 1.5),
              color: isAccent ? '#111' : '#fff',
              background: isAccent ? ACCENT : 'transparent',
              padding: isAccent ? '0 0.18em' : 0,
              borderRadius: isAccent ? '0.12em' : 0,
            }}
          >
            {word}
          </span>
        );
      })}
    </div>
  ));

  const boxed = overlay.role !== 'hook';
  const punch = spring({ frame, fps, config: { damping: 9, mass: 0.6 } });

  return (
    <div
      style={{
        position: 'absolute',
        top: style.top,
        left: SAFE.side,
        right: SAFE.side,
        display: 'flex',
        justifyContent: 'center',
        opacity: exit,
      }}
    >
      <div
        style={{
          fontFamily,
          fontWeight: Number(style.weight),
          fontSize: layout.fontSize,
          lineHeight: 1.08,
          textAlign: 'center',
          textTransform: overlay.role === 'value' ? 'uppercase' : 'none',
          textShadow: boxed ? 'none' : '0 6px 24px rgba(0,0,0,0.6)',
          padding: boxed ? '0.28em 0.5em' : 0,
          borderRadius: boxed ? '0.4em' : 0,
          background:
            overlay.role === 'cta' ? ACCENT : overlay.role === 'value' ? 'rgba(0,0,0,0.55)' : 'none',
          color: overlay.role === 'cta' ? '#111' : '#fff',
          transform: boxed ? `scale(${0.7 + punch * 0.3})` : undefined,
        }}
      >
        {overlay.role === 'cta'
          ? layout.lines.map((l, i) => <div key={i}>{l.join(' ')}</div>)
          : words}
      </div>
    </div>
  );
};

/** Highlight the longest word in the hook (a stand-in for a planner-chosen keyword). */
function pickAccentWord(words: string[]): number {
  let best = 0;
  words.forEach((w, i) => {
    if (w.length > words[best].length) best = i;
  });
  return best;
}
