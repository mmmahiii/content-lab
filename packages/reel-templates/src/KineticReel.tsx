import { useEffect, useMemo, useState } from 'react';
import {
  AbsoluteFill,
  Audio,
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
import { captionExitFrames, energyStyle, shakeOffset, type EnergyStyle } from './energy';
import { REEL_FONT_FAMILY, waitForReelFont } from './fonts';
import {
  ACCENT_BLEED_EM,
  captionGeometry,
  layoutMode,
  PROGRESS_TOP,
  SAFE_INSETS,
  visualBand,
  type CaptionGeometry,
  type LayoutMode,
} from './geometry';
import type { ReelTimeline, TimelineOverlay, TimelineVisual } from './timeline';

function useFontReady(): boolean {
  const [handle] = useState(() => delayRender('Loading Montserrat'));
  const [ready, setReady] = useState(false);
  useEffect(() => {
    waitForReelFont().then(() => {
      setReady(true);
      continueRender(handle);
    });
  }, [handle]);
  return ready;
}

/** Public-dir file names go through staticFile(); URLs are used as they are. */
export function resolveVisualSrc(src: string): string {
  return /^(https?:|data:|blob:|\/)/.test(src) ? src : staticFile(src);
}

export const KineticReel: React.FC<ReelTimeline> = (timeline) => {
  const ready = useFontReady();
  const style = energyStyle(timeline.energy);
  const mode = layoutMode(timeline);
  // The original proof look (no energy) only vignettes images; energies always shape light.
  const vignette = timeline.energy || timeline.visuals.length > 0 ? style.vignette : 0;
  return (
    <AbsoluteFill
      style={{
        overflow: 'hidden',
        background: `linear-gradient(180deg, ${timeline.backdrop[0]}, ${timeline.backdrop[1]})`,
      }}
    >
      {timeline.audio && (
        <Audio src={resolveVisualSrc(timeline.audio.src)} volume={timeline.audio.volume ?? 1} />
      )}
      {timeline.energy && mode !== 'cover' && <Glow style={style} />}
      {timeline.visuals.map((visual) => (
        <Sequence
          key={`${visual.src}-${visual.startFrame}`}
          from={visual.startFrame}
          durationInFrames={visual.endFrame - visual.startFrame}
        >
          {mode === 'cover' ? (
            <CoverVisual visual={visual} style={style} />
          ) : (
            <CutoutVisual visual={visual} style={style} />
          )}
        </Sequence>
      ))}
      {mode === 'cover' && <Scrims />}
      {vignette > 0 && <Vignette strength={vignette} />}
      {style.letterboxPx > 0 && <Letterbox height={style.letterboxPx} />}
      {timeline.showProgress !== false && <ProgressBar timeline={timeline} />}
      {ready && <Captions timeline={timeline} mode={mode} style={style} />}
      {style.flash > 0 &&
        timeline.overlays.slice(1).map((overlay) => (
          <Sequence key={`flash-${overlay.startFrame}`} from={overlay.startFrame} durationInFrames={5}>
            <Flash strength={style.flash} />
          </Sequence>
        ))}
    </AbsoluteFill>
  );
};

const Captions: React.FC<{ timeline: ReelTimeline; mode: LayoutMode; style: EnergyStyle }> = ({
  timeline,
  mode,
  style,
}) => {
  const geometries = useMemo(
    () =>
      timeline.overlays.map((overlay) =>
        captionGeometry(overlay, {
          width: timeline.width,
          height: timeline.height,
          mode,
          style,
          fontFamily: REEL_FONT_FAMILY,
        }),
      ),
    [timeline.overlays, timeline.width, timeline.height, mode, style],
  );
  return (
    <>
      {timeline.overlays.map((overlay, i) => (
        <Sequence
          key={`${overlay.text}-${overlay.startFrame}`}
          from={overlay.startFrame}
          durationInFrames={overlay.endFrame - overlay.startFrame}
        >
          <Caption overlay={overlay} geometry={geometries[i]} style={style} />
        </Sequence>
      ))}
    </>
  );
};

const Glow: React.FC<{ style: EnergyStyle }> = ({ style }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  const a = { x: 30 + Math.sin(t * 0.5) * 14, y: 28 + Math.cos(t * 0.4) * 10 };
  const b = { x: 72 + Math.cos(t * 0.45) * 12, y: 74 + Math.sin(t * 0.35) * 10 };
  return (
    <AbsoluteFill
      style={{
        background: `radial-gradient(circle at ${a.x}% ${a.y}%, ${style.glow} 0%, rgba(0,0,0,0) 45%),
          radial-gradient(circle at ${b.x}% ${b.y}%, ${style.glow} 0%, rgba(0,0,0,0) 40%)`,
      }}
    />
  );
};

function useVisualMotion(visual: TimelineVisual, style: EnergyStyle) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const length = visual.endFrame - visual.startFrame;
  const enter = spring({ frame, fps, config: style.visualSpring });
  const drift = interpolate(frame, [0, length], [0, 1]);
  const exitFrames = Math.max(4, Math.min(style.exitFrames, Math.floor(length / 3)));
  const exit = interpolate(frame, [length - exitFrames, length], [1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  return { enter, drift, exit };
}

const VisualImg: React.FC<{ src: string; style: React.CSSProperties }> = ({ src, style }) => {
  const [failed, setFailed] = useState(false);
  if (failed) return null;
  return (
    <Img
      src={resolveVisualSrc(src)}
      maxRetries={2}
      onError={() => setFailed(true)}
      style={style}
    />
  );
};

const CutoutVisual: React.FC<{ visual: TimelineVisual; style: EnergyStyle }> = ({
  visual,
  style,
}) => {
  const { width, height } = useVideoConfig();
  const { enter, drift, exit } = useVisualMotion(visual, style);
  if (!visual.src) return null;
  const band = visualBand(width, height);
  return (
    <AbsoluteFill
      style={{
        top: band.top,
        height: band.height,
        alignItems: 'center',
        justifyContent: 'center',
        opacity: exit,
      }}
    >
      <VisualImg
        src={visual.src}
        style={{
          maxWidth: '82%',
          // Leave headroom for the push-in scale so the visual stays inside its band.
          maxHeight: `${Math.round(100 / (1 + style.visualPush) - 2)}%`,
          objectFit: 'contain',
          transform: `translateY(${(1 - enter) * 120}px) scale(${
            (0.85 + enter * 0.15) * (1 + drift * style.visualPush)
          }) rotate(${(1 - enter) * -6 + drift * style.visualTilt}deg)`,
          filter: 'drop-shadow(0 40px 60px rgba(0,0,0,0.55))',
        }}
      />
    </AbsoluteFill>
  );
};

const CoverVisual: React.FC<{ visual: TimelineVisual; style: EnergyStyle }> = ({
  visual,
  style,
}) => {
  const frame = useCurrentFrame();
  const { drift, exit } = useVisualMotion(visual, style);
  if (!visual.src) return null;
  const fadeIn = interpolate(frame, [0, 6], [0, 1], { extrapolateRight: 'clamp' });
  return (
    <AbsoluteFill style={{ opacity: Math.min(fadeIn, exit) }}>
      <VisualImg
        src={visual.src}
        style={{
          width: '100%',
          height: '100%',
          objectFit: 'cover',
          transform: `scale(${1.02 + drift * style.visualPush})`,
        }}
      />
    </AbsoluteFill>
  );
};

const Scrims: React.FC = () => (
  <AbsoluteFill
    style={{
      background:
        'linear-gradient(180deg, rgba(0,0,0,0.6) 0%, rgba(0,0,0,0) 38%, rgba(0,0,0,0) 52%, rgba(0,0,0,0.78) 100%)',
    }}
  />
);

const Vignette: React.FC<{ strength: number }> = ({ strength }) => (
  <AbsoluteFill
    style={{
      background: `radial-gradient(ellipse at 50% 45%, rgba(0,0,0,0) 45%, rgba(0,0,0,${strength}) 100%)`,
    }}
  />
);

const Letterbox: React.FC<{ height: number }> = ({ height }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const h = height * spring({ frame, fps, config: { damping: 30, mass: 1, stiffness: 80 } });
  const bar: React.CSSProperties = { position: 'absolute', left: 0, right: 0, height: h, background: '#000' };
  return (
    <AbsoluteFill>
      <div style={{ ...bar, top: 0 }} />
      <div style={{ ...bar, bottom: 0 }} />
    </AbsoluteFill>
  );
};

const Flash: React.FC<{ strength: number }> = ({ strength }) => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [0, 4], [strength, 0], { extrapolateRight: 'clamp' });
  return <AbsoluteFill style={{ background: '#fff', opacity }} />;
};

const ProgressBar: React.FC<{ timeline: ReelTimeline }> = ({ timeline }) => {
  const frame = useCurrentFrame();
  return (
    <div
      style={{
        position: 'absolute',
        top: PROGRESS_TOP,
        left: SAFE_INSETS.left,
        right: SAFE_INSETS.right,
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
              style={{ width: `${p * 100}%`, height: '100%', borderRadius: 4, background: '#fff' }}
            />
          </div>
        );
      })}
    </div>
  );
};

const Caption: React.FC<{
  overlay: TimelineOverlay;
  geometry: CaptionGeometry;
  style: EnergyStyle;
}> = ({ overlay, geometry: g, style }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const length = overlay.endFrame - overlay.startFrame;
  const exitFrames = captionExitFrames(length, style);
  const exit = interpolate(frame, [length - exitFrames, length], [1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const words = g.lines.flatMap((line) => line.words);
  const accentIndex = overlay.role === 'hook' ? pickAccentWord(words) : -1;
  const punch = spring({ frame, fps, config: style.boxSpring });
  const boxScale = style.boxFromScale + (1 - style.boxFromScale) * punch;
  let wordIndex = 0;

  const background =
    overlay.role === 'cta'
      ? style.accent
      : overlay.role === 'value'
        ? style.captionBg
        : overlay.role === 'disclosure'
          ? 'rgba(0,0,0,0.6)'
          : 'none';

  return (
    <div
      style={{
        position: 'absolute',
        left: g.zone.left,
        width: g.zone.width,
        top: g.box.top,
        display: 'flex',
        justifyContent: 'center',
        opacity: exit,
        transform: `translateX(${shakeOffset(frame, style.shakePx, fps)}px)`,
      }}
    >
      <div
        style={{
          fontFamily: g.fontFamily,
          fontWeight: Number(g.fontWeight),
          fontSize: g.fontSize,
          lineHeight: `${g.lineHeightPx}px`,
          letterSpacing: `${g.letterSpacingEm}em`,
          textTransform: g.textTransform,
          whiteSpace: 'nowrap',
          textAlign: 'center',
          padding: `${g.insetY}px ${g.insetX}px`,
          borderRadius: g.boxed ? `${style.captionRadiusEm}em` : 0,
          textShadow: g.boxed ? 'none' : '0 6px 24px rgba(0,0,0,0.6)',
          background,
          color: overlay.role === 'cta' ? style.accentInk : '#fff',
          transform: g.boxed ? `scale(${boxScale})` : undefined,
        }}
      >
        {g.lines.map((line, li) => (
          <div key={li} style={{ display: 'flex', justifyContent: 'center', gap: `${g.gapEm}em` }}>
            {line.words.map((word) => {
              const i = wordIndex++;
              const delay = overlay.role === 'hook' ? i * style.wordStagger : 0;
              const pop = spring({ frame: frame - delay, fps, config: style.wordSpring });
              const scale = style.wordFromScale + (1 - style.wordFromScale) * pop;
              const blur = Math.max(0, (1 - pop) * style.wordFromBlur);
              const isAccent = i === accentIndex;
              return (
                <span
                  key={i}
                  style={{
                    display: 'inline-block',
                    transform: `translateY(${(1 - pop) * style.wordFromY}px) scale(${scale})`,
                    filter: blur > 0.1 ? `blur(${blur}px)` : undefined,
                    opacity: Math.min(1, pop * 1.5),
                    color: isAccent ? style.accentInk : undefined,
                    background: isAccent ? style.accent : 'transparent',
                    borderRadius: isAccent ? '0.12em' : 0,
                    // Highlight bleed drawn with a shadow so it never changes the layout.
                    boxShadow: isAccent ? `0 0 0 ${ACCENT_BLEED_EM}em ${style.accent}` : undefined,
                  }}
                >
                  {word}
                </span>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
};

/** Highlight the longest word in the hook (a stand-in for a planner-chosen keyword). */
export function pickAccentWord(words: string[]): number {
  let best = 0;
  words.forEach((w, i) => {
    if (w.length > words[best].length) best = i;
  });
  return best;
}
