import { fromPipelineOverlays, type ReelTimeline } from './timeline';

/**
 * A: the exact overlay_timeline from
 * packages/qa/tests/fixtures/bad_reels/cases/latest_trace_smoke_operations.json —
 * the plan behind the FFmpeg-rendered package in artifacts/page/.../8ac8e82f.../final_video.mp4.
 * Same black backdrop as that render, so only text and motion differ.
 */
export const operationsBaseline: ReelTimeline = {
  ...fromPipelineOverlays(
    [
      {
        emphasis: 'hook',
        start_seconds: 0,
        end_seconds: 3,
        text: 'The operations reset busy founders can do today',
      },
      { emphasis: 'value', start_seconds: 3, end_seconds: 6, text: 'operations' },
      { emphasis: 'value', start_seconds: 6, end_seconds: 9, text: 'One repeatable move' },
      { emphasis: 'cta', start_seconds: 9, end_seconds: 12, text: 'Save this reset' },
    ],
    { fps: 24, durationSeconds: 12 },
  ),
  width: 1080,
  height: 1920,
  backdrop: ['#000000', '#000000'],
  visuals: [],
};

/**
 * B: the ratatouille cinematic plan used in apps/api/tests/test_runs_routes.py,
 * with cut-out PNGs from the faceless cooking pack in artifacts/asset_packs/.
 */
export const ratatouilleAssets: ReelTimeline = {
  ...fromPipelineOverlays(
    [
      { emphasis: 'hook', start_seconds: 0, end_seconds: 3, text: 'Tomato texture starts the stack' },
      {
        emphasis: 'value',
        start_seconds: 3,
        end_seconds: 6,
        text: 'Eggplant and pepper build the colour',
      },
      { emphasis: 'value', start_seconds: 6, end_seconds: 8.5, text: 'Layer it tight' },
      { emphasis: 'cta', start_seconds: 8.5, end_seconds: 11, text: 'Basil makes it ready' },
    ],
    { fps: 30, durationSeconds: 11 },
  ),
  width: 1080,
  height: 1920,
  backdrop: ['#3a1410', '#120605'],
  visuals: [
    { src: 'tomato_cut.png', startFrame: 0, endFrame: 90 },
    { src: 'cut_eggplant.png', startFrame: 90, endFrame: 140 },
    { src: 'bell_pepper.png', startFrame: 140, endFrame: 180 },
    { src: 'ratatouille_ingredients.png', startFrame: 180, endFrame: 255 },
    { src: 'basil.png', startFrame: 255, endFrame: 330 },
  ],
};
