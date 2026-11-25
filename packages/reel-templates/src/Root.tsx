import { AbsoluteFill, Composition, Sequence, type CalculateMetadataFunction } from 'remotion';
import { operationsBaseline, quickReelFixtures, ratatouilleAssets } from './fixtures';
import { REEL_FONT_FAMILY, waitForReelFont } from './fonts';
import { KineticReel } from './KineticReel';
import type { ReelTimeline } from './timeline';
import { buildOverlayRenderTrace, type OverlayRenderTrace } from './trace';

const compositions: Array<{ id: string; timeline: ReelTimeline }> = [
  { id: 'OperationsBaseline', timeline: operationsBaseline },
  { id: 'RatatouilleAssets', timeline: ratatouilleAssets },
];

/** Quick Reel renders take the timeline as input props; size and length follow it. */
export const QUICK_REEL_COMPOSITION = 'QuickReel';
/** Same timeline; `calculateMetadata` adds the overlay render trace to the props. */
export const QUICK_REEL_TRACE_COMPOSITION = 'QuickReelTrace';

const fromTimeline: CalculateMetadataFunction<ReelTimeline> = ({ props }) => ({
  durationInFrames: props.durationInFrames,
  fps: props.fps,
  width: props.width,
  height: props.height,
});

export type TraceProps = { timeline: ReelTimeline; trace?: OverlayRenderTrace };

/**
 * Runs in the (headless) browser with the reel font loaded, so the trace uses real glyph
 * metrics: the same `captionGeometry` call `KineticReel` makes while rendering.
 */
export const calculateTrace: CalculateMetadataFunction<TraceProps> = async ({ props }) => {
  await waitForReelFont();
  const trace = buildOverlayRenderTrace(props.timeline, {
    fontFamily: REEL_FONT_FAMILY,
    composition: QUICK_REEL_COMPOSITION,
  });
  return {
    durationInFrames: props.timeline.durationInFrames,
    fps: props.timeline.fps,
    width: props.timeline.width,
    height: props.timeline.height,
    props: { ...props, trace },
  };
};

/** Studio debug view: the reel with its traced caption boxes outlined. */
const TraceView: React.FC<TraceProps> = ({ timeline, trace }) => (
  <AbsoluteFill>
    <KineticReel {...timeline} />
    {trace?.overlays.map((o) => (
      <Sequence
        key={o.index}
        from={o.visible_start_frame}
        durationInFrames={o.visible_end_frame - o.visible_start_frame}
      >
        <div
          style={{
            position: 'absolute',
            left: o.text_box.left_px,
            top: o.text_box.top_px,
            width: o.text_box.width_px,
            height: o.text_box.height_px,
            outline: `4px dashed ${o.safe_area_passed ? '#00e676' : '#ff1744'}`,
          }}
        />
      </Sequence>
    ))}
  </AbsoluteFill>
);

export const Root: React.FC = () => (
  <>
    {compositions.map(({ id, timeline }) => (
      <Composition
        key={id}
        id={id}
        component={KineticReel}
        fps={timeline.fps}
        durationInFrames={timeline.durationInFrames}
        width={timeline.width}
        height={timeline.height}
        defaultProps={timeline}
      />
    ))}
    <Composition
      id={QUICK_REEL_COMPOSITION}
      component={KineticReel}
      defaultProps={quickReelFixtures.punchy}
      calculateMetadata={fromTimeline}
    />
    <Composition
      id={QUICK_REEL_TRACE_COMPOSITION}
      component={TraceView}
      defaultProps={{ timeline: quickReelFixtures.dramatic } satisfies TraceProps}
      calculateMetadata={calculateTrace}
    />
  </>
);
