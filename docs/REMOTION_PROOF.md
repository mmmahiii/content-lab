# Remotion proof — findings (2026-11-25)

Step 1 of `docs/UI_PLAN.md`: render existing pipeline data with Remotion and compare
against the current FFmpeg output. Code: `packages/reel-templates`.

## Verdict: **Go** — adopt Remotion for templates and preview, keep FFmpeg for plumbing

## What was rendered

| | Input | Background | Output |
|---|---|---|---|
| **A** | `overlay_timeline` from `packages/qa/tests/fixtures/bad_reels/cases/latest_trace_smoke_operations.json` ("operations reset for busy founders") | Black, same as FFmpeg render | 1080×1920, 24 fps, 12.0 s |
| **B** | Ratatouille plan from `apps/api/tests/test_runs_routes.py` | Cut-out PNGs from `artifacts/asset_packs/faceless_cooking_real_png/` | 1080×1920, 30 fps, 11.0 s |

FFmpeg baseline: `artifacts/page/.../8ac8e82f.../final_video.mp4` — the rendered package of the
same "operations" reel concept. Its captions differ slightly from the fixture (it is the same
reel idea, not byte-identical input), so A compares rendering quality, not a pixel diff.

Reproduce:

```powershell
cd packages/reel-templates
pnpm render:operations
pnpm render:ratatouille
pnpm studio   # live editor/preview
```

## Results

| Criterion | FFmpeg today | Remotion proof |
|---|---|---|
| Text clipping | **Clips captions** ("Test a fresh angle that still") | Impossible by construction: `layoutText` picks the largest size that fits, or throws so the plan must change |
| Typography | Small default sans, one size, bottom-anchored | Montserrat 800/900, per-role styles (hook / value / CTA), keyword highlight |
| Motion | None (static text) | Word-by-word hook pop-in, punch-in captions, image spring + slow drift, story progress bar |
| Duration accuracy | **10.0 s for a 12 s plan** (another existing bug) | Exactly matches plan (frame-based, half-open intervals) |
| Layout safety | Fixed bottom position | Safe-area margins; text and visual bands never overlap (fixed during the proof) |
| Render time | Not measured (needs Docker stack) | **36 s** for 12 s text-only; **64 s** for 11 s with 5 large PNGs (first-run Chrome download excluded) |
| Audio | AAC track present | **None yet** — not implemented in the proof |
| Live preview in browser | Not possible | Yes, same component via `@remotion/player` |

## Problems found

1. **Text over visuals (fixed).** First render put the hook and captions on top of images.
   Fixed with layout bands: hook above, visual in a middle band, captions below. Long-term this
   should use the asset's subject mask (master plan §08) instead of fixed bands.
2. **Asset quality.** `tomato_cut.png` and `ratatouille_ingredients.png` are diagrams /
   infographics with baked-in text, not clean cut-outs. They look wrong in a reel. The asset
   registry should flag "contains text / diagram" so templates can skip or treat them differently.
3. **Render time scales with image size.** 2–5 MP source PNGs cost ~30 s extra. Pre-resizing
   representations to delivery size (an existing derivation concept) will cut this.
4. **Accent word is a heuristic** (longest word). The planner should choose it.

## Not covered yet (needed before production)

- **Audio**: music bed, voiceover, SFX via `<Audio>`; loudness and sync checks.
- **QA parity**: templates must emit an `overlay_render_trace` (text, font size, line boxes,
  visible frame intervals) so `packages/qa` keeps working. `layoutText` already computes the
  data; it needs to be exported alongside the MP4.
- **Pipeline integration**: worker → Node render service → MinIO → package builder.
- **Python ↔ TS contract**: generate the `ReelTimeline` schema from one source instead of the
  hand-written adapter (`fromPipelineOverlays`).
- **Licence**: Remotion is free for individuals and companies up to 3 people; check terms
  before scaling the team.

## Next steps

1. Export overlay render traces from the template (QA parity).
2. Add audio (music bed + optional VO).
3. Render service + worker hook, behind a flag, alongside FFmpeg.
4. Use the same component in the new UI via `@remotion/player` (Quick Reel prototype).
