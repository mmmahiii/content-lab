# Content Lab Backlog — Composable Asset Registry and Asset Compounding Engine

**Status:** Additive backlog stream for the existing scaffold-aligned Content Lab project  
**Purpose:** Convert the Asset Registry from a full-video-only mindset into a component-aware asset system that supports layered, reusable image/video/audio/text assets and planned niche asset packs.  
**Scope:** Everything discussed in this chat: component-level assets, PNG/object/background support, layered reel composition, planned asset batch creation, user-defined pack sizes, intentional asset selection, reverse idea generation, asset combinations, provenance, QA, and performance tracking.

---

## 0. Executive summary

The system must not treat an asset as only a complete generated video clip.

A reel should be buildable from multiple reusable components, including backgrounds, object PNGs, props, subject layers, foreground videos, effects, text overlays, audio, and final render outputs. The Asset Registry should remember and resolve these assets, while the Editing/Composition layer should combine them into realistic vertical reels.

The system must also support a second production loop:

```text
Niche → intentional asset pack → reusable asset bank → asset-led ideas → combinations → layered reels
```

This is in addition to the existing loop:

```text
Idea → brief → required assets → generated video/package
```

The goal is to turn assets into reusable capital rather than disposable one-off outputs.

---

## 1. Non-negotiable requirements from this chat

### 1.1 Assets are not only full video clips

The Asset Registry must support, at minimum:

- PNG images
- transparent PNG cut-outs
- object images
- subject images
- prop images
- background images
- generated images
- uploaded/source images
- generated video clips
- uploaded/source video clips
- background videos
- object videos
- foreground video layers
- transparent/alpha video layers where supported
- effect layers
- transition layers
- hook text
- overlay plans
- subtitle/caption plans
- caption text
- audio/music
- sound effects
- voiceovers
- final rendered videos
- cover images
- package artifacts

### 1.2 Final video is a derived output, not the only asset

The final rendered reel should be treated as a derived asset/output created from a component graph.

Reusable component assets must remain separately tracked so they can be reused across future reels.

### 1.3 Reels must support layered composition

The system should be able to assemble a reel from:

```text
background image/video
+ foreground object PNG/video
+ subject/prop layer
+ effect layer
+ hook/text overlay
+ audio layer
+ motion/camera/composition instructions
= realistic final vertical reel
```

### 1.4 Asset pack size is operator-defined

The number of assets in an asset pack must be defined by the operator.

Examples:

```text
Generate an asset pack for luxury mindset with 40 assets.
```

```text
Generate 80 assets:
- 15 backgrounds
- 25 object/prop assets
- 10 subject/foreground assets
- 15 hooks
- 5 audio moods
- 10 formats/effects
```

If no split is provided, the system should propose a sensible split based on niche, target reel types, format goals, and policy.

### 1.5 Asset pack choices must be intentional

The system must not bulk-generate random assets.

It must first produce an Asset Pack Plan explaining why the chosen assets are needed, how they will be reused, and which future reel types they unlock.

### 1.6 Asset packs are reusable but not exhaustive

The goal is not to create a complete asset universe.

The goal is to create an intentional starter asset set that maximises useful reel output potential.

The guiding phrase is:

```text
Reusable but output-optimised, not exhaustive.
```

### 1.7 Initial asset choices should maximise reel output potential

The planner should prioritise assets that:

- can be reused across multiple videos
- combine well with other assets
- unlock multiple future reel concepts
- reduce future generation cost
- help produce realistic-looking videos
- support immediate reel creation
- avoid bloating the pack with low-utility assets

---

## 2. Target operating model

### 2.1 Existing linear production loop

```text
Trend / idea
→ brief
→ generate or retrieve assets
→ edit
→ QA
→ package
→ human review/posting
```

### 2.2 New compounding production loop

```text
Niche
→ asset pack plan
→ intentional batch asset creation
→ reusable asset bank
→ reverse idea generation
→ asset combinator
→ layered composition
→ ready-to-post package
→ asset-level performance tracking
→ better future asset choices
```

### 2.3 Two-way generation requirement

The system must support both:

```text
Idea → required assets → reel
```

and:

```text
Existing assets → possible ideas → reel
```

This is the key strategic upgrade.

---

## 3. Implementation principles

### 3.1 Keep the current scaffold

Do not introduce a parallel architecture.

The work must fit the existing project pattern:

- `packages/assets` owns registry logic, AssetKey logic, asset policy, reuse decisions, and asset metadata types.
- `packages/storage` owns object storage paths, checksums, upload/download/presign helpers.
- `packages/editing` owns composition manifests, FFmpeg composition, overlays, covers, and final media outputs.
- `packages/creative` owns asset pack planning, hooks, captions, reverse idea generation, and posting plans.
- `packages/qa` owns format, package, provenance, repetition, and layered-composition QA.
- `packages/intelligence` later owns performance weighting, scoring, and policy tuning.
- `apps/api` owns routes, services, ORM models, schemas, migrations, and control-plane validation.
- `apps/worker` owns asynchronous generation, transformation, composition, packaging, and dispatch work.
- `apps/orchestrator` owns Prefect flows and sequencing.
- `apps/web` owns the operator UI.

### 3.2 Do not make the registry the editor

The Asset Registry should:

- store assets
- resolve assets
- reuse assets
- track asset metadata
- track asset usage
- support deterministic AssetKeys
- support provenance and lineage

The editor/compositor should:

- layer assets
- animate assets
- apply transforms
- create the final render
- extract cover images

### 3.3 Treat storage as canonical

Authoritative binary outputs must live in MinIO/S3-compatible object storage.

Local temp folders are allowed for worker processing only, not as the product surface.

### 3.4 Keep human posting as the MVP boundary

This backlog does not add autonomous posting.

It prepares ready-to-post packages and operator-visible review flows.

---

## 4. Backlog roadmap overview

Recommended implementation order:

1. Audit current asset baseline
2. Add component-aware asset taxonomy
3. Add image/video/alpha/visual metadata
4. Add Asset Pack data model
5. Add user-defined asset pack planning
6. Add output-optimised asset selection strategy
7. Add batch asset generation/registration
8. Extend AssetKey canonicalisation by component type
9. Add component-level registry decisions
10. Add asset usage/component lineage
11. Add compatibility metadata and combinator logic
12. Add reverse idea generation
13. Add composition manifest
14. Add layered FFmpeg composition
15. Add provenance from component graph
16. Add layered QA and realism checks
17. Add asset-level performance tracking
18. Add API routes
19. Add web/operator views
20. Add end-to-end smoke and regression tests

---

# EPIC 1 — Baseline audit and alignment

## CAR-000 — Audit current asset implementation
**Agent:** `codex-medium`

**Objective:** Confirm what the current repo actually supports before implementing component-level Asset Registry work.

**Why:** The current scaffold may only have starter asset records. This task prevents implementation against assumptions.

**Likely files to inspect:**

```text
apps/api/migrations/
apps/api/src/content_lab_api/models/
apps/api/src/content_lab_api/schemas/
packages/assets/
packages/storage/
packages/editing/
apps/worker/
apps/orchestrator/
```

**Implementation steps:**

1. Inspect current `assets` table/schema.
2. Inspect whether `run_assets` is still the only lineage table.
3. Check whether `asset_usage` exists.
4. Check whether `asset_gen_params` exists.
5. Check whether `asset_families` exists.
6. Check whether assets have `kind`, `media_type`, `source`, `status`, `storage_uri`, and `content_hash` fields.
7. Check whether image assets are supported.
8. Check whether transparent PNG/cut-out metadata is supported.
9. Check whether final renders are distinct from reusable source/component assets.
10. Check whether package artifacts are represented as artifacts/assets.
11. Produce a gap report.

**Acceptance criteria:**

- Implemented state is clearly separated from target-state.
- Missing prerequisites are identified.
- No later task assumes missing schema exists.

**Audit result (2026-05-05):**

Implemented state:

- `assets` exists and has the current columns `org_id`, `asset_class`, `storage_uri`, `source`, `asset_key`, `content_hash`, `phash`, `status`, `metadata`, `embedding`, `family_id`, and `asset_key_hash`.
- The initial `kind` column was renamed to `asset_class` in migration `0002`; there is no current `kind` column and no `media_type` column.
- `asset_families` exists via migration `0007` and model `AssetFamily`.
- `asset_gen_params` exists via migration `0007` and model `AssetGenParam`; the phase-1 resolver writes canonical generation params with `seq` and `asset_key_hash`.
- `asset_usage` exists via migration `0007` and model `AssetUsage`; `run_assets` is explicitly marked legacy/operational lineage, not the preferred creative lineage table.
- `run_assets` still exists with `asset_role`, but it is not the only lineage table.
- Phase-1 registry resolution is implemented for exact reuse/generation intents using `asset_key_hash`, staged assets, `tasks`, and `provider_jobs`.
- Asset storage helpers support canonical derived asset objects and filename/content-type handling for `image/png`, `image/jpeg`, `video/mp4`, and common audio types.
- Package artifacts are represented in package payloads and object storage paths, with package routes exposing artifacts and signed downloads.

Target-state gaps:

- Component-aware `AssetKind` is not implemented. The current `asset_class` is a free string and does not distinguish background/object/subject/prop/final_render/package_artifact roles.
- `MediaType` is not implemented as schema or DB state. Media type may appear in storage/package artifact payloads, but not on `assets`.
- Transparent PNG/cut-out metadata is not first-class. It can only be placed ad hoc in `assets.metadata`; there are no typed fields such as `alpha_mode`, `has_transparency`, `mask_uri`, or `subject_bbox`.
- Image assets are partially supported by storage and generic registry records, but the phase-1 generator path is still primarily Runway video-generation oriented and does not provide image-specific generation/registration workflows.
- `asset_usage` exists but no production write path was found in the inspected process-reel/package flow. Later component-lineage tasks must not assume populated `asset_usage` rows.
- Final renders and package artifacts are distinct at the storage/package layer (`reels/packages/.../final_video.mp4`, `cover.png`, manifests, traces), but they are not represented as `assets` with final/package artifact kinds.
- Package artifacts are not first-class Asset Registry records; they live in run output/package metadata and object storage.
- No asset-pack, planned asset spec, component compatibility, reverse-idea, composition manifest, or asset-level performance schema exists yet.

Prerequisites for later tasks:

- Add explicit `AssetKind` and `MediaType` vocabulary before component registry decisions.
- Add typed image/transparency/visual metadata before relying on cut-out or layered composition filters.
- Add or populate component-level `asset_usage` write paths before provenance/performance tasks rely on creative lineage.
- Decide whether final renders/package artifacts should become `assets`, separate artifact records, or both before implementing package-level provenance.

---

# EPIC 2 — Component-aware asset taxonomy

## CAR-001 — Add AssetKind taxonomy
**Agent:** `codex-medium`

**Objective:** Define asset kinds so the system does not flatten everything into full generated video clips.

**Suggested AssetKind values:**

```text
background_image
background_video
object_image
object_video
subject_image
subject_video
prop_image
prop_video
foreground_layer_image
foreground_layer_video
transparent_cutout_png
masked_image
effect_image
effect_video
transition_layer
generated_clip
source_clip
final_render
cover_image
hook_text
overlay_plan
subtitle_plan
caption_text
design_template
audio_track
sound_effect
voiceover
trimmed_audio
package_artifact
provenance_artifact
posting_plan_artifact
```

**Likely files:**

```text
packages/assets/src/content_lab_assets/types.py
apps/api/src/content_lab_api/models/assets.py
apps/api/src/content_lab_api/schemas/assets.py
```

**Implementation steps:**

1. Add `AssetKind` enum.
2. Add tests for all required values.
3. Use `AssetKind` in registry payloads.
4. Ensure full videos are only one kind among many.
5. Keep enum extensible for future assets.

**Acceptance criteria:**

- PNG, object, subject, prop, background, audio, text, final render, and package artifacts are first-class.
- The registry can distinguish reusable components from final outputs.

---

## CAR-002 — Add MediaType taxonomy
**Agent:** `codex-medium`

**Objective:** Separate what the asset is used for from what file/data format it has.

**Suggested MediaType values:**

```text
image
video
audio
text
json
package
unknown
```

**Implementation steps:**

1. Add `MediaType` enum.
2. Validate compatible combinations of `AssetKind` and `MediaType`.
3. Add tests for images, videos, audio, text, and JSON/package artifacts.
4. Use the enum in registry and API schemas.

**Acceptance criteria:**

- An object asset can be image or video.
- A background asset can be image or video.
- Text/overlay assets are not incorrectly treated as video files.

---

## CAR-003 — Add transparency and alpha metadata
**Agent:** `codex-high`

**Objective:** Support object-level PNG cut-outs and layerable media assets.

**Suggested fields/metadata:**

```text
alpha_mode: none | alpha | mask | chroma_key | unknown
has_transparency: boolean
mask_uri: optional
subject_bbox: optional
safe_crop: optional
```

**Implementation steps:**

1. Add transparency metadata in asset metadata JSON or schema fields.
2. Add basic transparent PNG detection where image processing exists.
3. Allow future chroma key/mask workflows.
4. Add tests with fixture image metadata.

**Acceptance criteria:**

- Transparent PNGs are representable.
- Cut-out objects can be filtered for layering.
- Future compositor logic can use alpha/mask metadata.

---

## CAR-004 — Add visual realism metadata
**Agent:** `codex-high`

**Objective:** Store metadata that helps assets combine into realistic videos.

**Suggested metadata:**

```text
width
height
duration
fps
aspect_ratio
shot_type
camera_angle
perspective
lighting
colour_temperature
visual_style
motion_type
loopable
foreground_safe
background_safe
```

**Implementation steps:**

1. Add metadata schema or typed model.
2. Populate metadata from ffprobe/image probe where possible.
3. Allow manual or generated metadata when automatic extraction is not possible.
4. Add tests for metadata shape.

**Acceptance criteria:**

- The system can filter assets by usefulness for composition.
- Backgrounds, objects, and videos have enough metadata for compatibility checks.

---

## CAR-005 — Add source/origin taxonomy
**Agent:** `codex-medium`

**Objective:** Track where each asset came from.

**Suggested values:**

```text
uploaded
generated
imported
observed_reference
derived
manual_template
package_output
```

**Implementation steps:**

1. Add `AssetSource` enum.
2. Attach source/origin to asset records.
3. Ensure generated and derived assets can be distinguished.
4. Add tests.

**Acceptance criteria:**

- Uploaded PNGs and generated videos are both valid assets.
- Derived outputs are not confused with source assets.

---

# EPIC 3 — Asset Pack data model

## PACK-001 — Add AssetPack entity
**Agent:** `codex-medium`

**Objective:** Represent a planned group of reusable assets for a specific niche.

**Suggested fields:**

```text
asset_pack_id
org_id
name
niche
purpose
target_audience
requested_asset_count
asset_mix_requested_json
asset_mix_final_json
status
strategy_summary
created_at
updated_at
```

**Implementation steps:**

1. Add `asset_packs` table/model/schema if schema stage is ready.
2. Keep pack org-scoped.
3. Store requested asset count.
4. Store optional requested mix by asset category.
5. Add status lifecycle.

**Suggested lifecycle:**

```text
draft → planned → generating → ready
             └→ failed
ready → archived
```

**Acceptance criteria:**

- Asset packs are first-class objects.
- Pack size is operator-defined.
- Pack state is trackable.

---

## PACK-002 — Add AssetPackItem entity or join model
**Agent:** `codex-medium`

**Objective:** Link assets to asset packs with their intended role.

**Suggested fields:**

```text
asset_pack_item_id
asset_pack_id
asset_id
planned_asset_spec_id
asset_kind
pack_role
reuse_purpose
priority
status
metadata_json
created_at
```

**Implementation steps:**

1. Add asset-pack-to-asset join table or model.
2. Store intended role inside the pack.
3. Track whether an asset was planned, generated, uploaded, or selected from existing library.
4. Add tests.

**Acceptance criteria:**

- A single asset can belong to multiple packs.
- Pack membership includes why the asset exists.
- Assets are not just dumped into a folder without purpose.

---

## PACK-003 — Add PlannedAssetSpec model
**Agent:** `codex-medium`

**Objective:** Represent intentional assets before they are generated or registered.

**Suggested fields:**

```text
planned_asset_spec_id
asset_pack_id
asset_kind
media_type
working_title
purpose
prompt_or_description
required_traits
compatible_with
intended_reel_formats
priority
estimated_reuse_count
status
```

**Implementation steps:**

1. Add planned asset specs to hold the pack plan.
2. Use planned specs to drive generation/registration.
3. Keep planned specs separate from created assets.
4. Add tests for status transitions.

**Acceptance criteria:**

- The system can plan assets before creating them.
- The asset pack is intentional, not random.
- Each generated asset can be traced back to a planned reason.

---

# EPIC 4 — Asset Pack planning and optimisation

## PLAN-001 — Implement Asset Pack Plan generator
**Agent:** `codex-high`

**Objective:** Generate an explicit plan before creating assets.

**Input:**

```text
niche
requested_asset_count
optional asset mix
optional target reel types
optional style/persona constraints
```

**Output:**

```text
asset_pack_plan
asset_mix
planned_asset_specs
strategy_summary
reuse_rationale
expected_reel_formats
```

**Implementation steps:**

1. Take niche and asset count as required inputs.
2. If no mix is provided, propose a default mix.
3. Identify high-value asset categories for the niche.
4. Generate planned asset specs.
5. Explain why each category exists.
6. Store the plan before generation begins.

**Acceptance criteria:**

- No batch asset generation starts without a plan.
- The plan explains how the pack supports future reels.
- The pack size matches the user-defined count.

---

## PLAN-002 — Implement user-defined asset count and mix validation
**Agent:** `codex-medium`

**Objective:** Ensure asset pack size and mix are controlled by the operator.

**Rules:**

- Operator can provide only total asset count.
- Operator can provide exact split by type.
- If exact split is provided, totals must match.
- If only total is provided, system proposes split.
- If impossible or unbalanced, system returns validation guidance.

**Implementation steps:**

1. Add validation for total count.
2. Add validation for per-kind/category counts.
3. Add default mix generation.
4. Add tests for valid/invalid inputs.

**Acceptance criteria:**

- Pack size is never hardcoded.
- Operator controls the number of assets.
- The system can still propose a sensible mix when needed.

---

## PLAN-003 — Implement output-potential scoring
**Agent:** `codex-high`

**Objective:** Optimise initial asset choices for reel output potential.

**Scoring criteria:**

```text
reuse_potential
combination_potential
visual_flexibility
niche_relevance
realism_support
format_coverage
cost_saving_potential
novelty_without_bloat
```

**Implementation steps:**

1. Score planned asset specs before generation.
2. Prioritise assets that unlock many reel combinations.
3. Avoid low-reuse filler assets.
4. Return rationale for high-priority assets.
5. Add deterministic tests with sample plans.

**Acceptance criteria:**

- Asset choices are intentional.
- Pack is reusable but not exhaustive.
- The initial pack is optimised to output reels quickly.

---

## PLAN-004 — Implement pack strategy summary
**Agent:** `codex-medium`

**Objective:** Produce a human-readable explanation of the asset pack.

**Summary should include:**

- niche
- target audience
- visual style
- emotional angles
- core motifs
- asset category split
- expected reel formats
- why these assets were chosen
- how the pack can generate multiple reels

**Acceptance criteria:**

- Operators can review the pack before generation.
- The pack rationale is auditable.
- The system avoids random bulk generation.

---

# EPIC 5 — Asset batch generation and registration

## BATCH-001 — Add Asset Batch Mode
**Agent:** `codex-high`

**Objective:** Add a mode that creates asset packs directly from a niche, instead of only creating assets from a reel brief.

**Example command/API intent:**

```text
Generate an asset pack for "luxury mindset" with 60 assets.
```

**Implementation steps:**

1. Add batch generation service boundary.
2. Accept niche, count, optional mix, and optional target reel formats.
3. Create AssetPack.
4. Create AssetPackPlan.
5. Create PlannedAssetSpecs.
6. Submit generation/registration tasks.
7. Mark pack ready when enough assets are available.

**Acceptance criteria:**

- The system can build an asset library before specific reel ideas exist.
- Asset packs are stored and reusable.
- Pack generation is plan-led.

---

## BATCH-002 — Support mixed generation and existing asset selection
**Agent:** `codex-high`

**Objective:** Do not generate everything if useful assets already exist.

**Implementation steps:**

1. Search existing asset library for matching planned specs.
2. Reuse exact or compatible existing assets where possible.
3. Generate only missing assets.
4. Record whether each pack item was reused, uploaded, imported, or generated.

**Acceptance criteria:**

- Existing assets can seed new packs.
- Batch mode reduces unnecessary generation cost.
- Pack items preserve provenance.

---

## BATCH-003 — Register uploaded/source assets into packs
**Agent:** `codex-medium`

**Objective:** Allow manual/user-provided assets to become first-class pack assets.

**Use cases:**

- User uploads object PNGs.
- User uploads background videos.
- User saves a useful prop image.
- User imports a brand/product image.

**Implementation steps:**

1. Add registration path for source assets.
2. Extract/provide metadata.
3. Store in object storage.
4. Attach to asset pack.
5. Compute content hash and AssetKey where relevant.

**Acceptance criteria:**

- Asset packs are not limited to AI-generated assets.
- Uploaded PNGs/videos are reusable.
- Source assets are stored canonically.

---

## BATCH-004 — Add pack review/approval gate
**Agent:** `codex-medium`

**Objective:** Allow operator review before expensive batch generation or before using a generated pack.

**Implementation steps:**

1. Add `planned` state for pack.
2. Add approve/reject/regenerate-plan actions.
3. Allow editing requested mix before generation.
4. Store decision in audit/provenance.

**Acceptance criteria:**

- Intentionality is enforced operationally.
- Operators can stop bad/random packs before generation spend.

---
## CAR-5A-001 — Add Asset Acquisition Ladder

**Objective:**  
Add a formal acquisition decision model that decides how each planned asset should be fulfilled before generation is attempted.

The system should use this ladder:

1. Reuse existing ready asset from Asset Registry
2. Reuse existing asset with transform
3. Use operator-uploaded asset
4. Use approved/licensed external source asset
5. Generate new image/video asset
6. Block or replace asset if quality, licence, or realism risk is too high

**Why:**  
Asset packs should not blindly generate every asset. The system should minimise expensive generation by reusing or importing suitable assets where possible.

**Likely files:**

- `packages/assets/src/content_lab_assets/acquisition.py`
- `packages/assets/src/content_lab_assets/types.py`
- `packages/assets/tests/`
- `apps/api/src/content_lab_api/schemas/assets.py`
- `apps/api/src/content_lab_api/services/`

**Implementation steps:**

1. Add acquisition decision types:
   - `reuse_existing_registry_asset`
   - `reuse_with_transform`
   - `use_operator_uploaded_asset`
   - `use_approved_external_asset`
   - `generate_new_asset`
   - `block_or_replace_asset`

2. Add an acquisition decision object containing:
   - planned asset spec id
   - recommended acquisition path
   - reason/rationale
   - confidence score if available
   - quality risk
   - licence/source risk
   - realism risk
   - expected cost impact
   - fallback path

3. Add logic that evaluates planned asset specs before generation.

4. Ensure generation is not the default if a suitable existing/imported asset can satisfy the need.

5. Add tests for the decision ladder.

**Acceptance criteria:**

- Each planned asset can receive an acquisition decision before generation.
- The system can choose reuse/import/upload instead of generation.
- Expensive generation is only selected when justified.
- The decision output is deterministic and test-backed.
- The model is compatible with later AssetKey and provenance work.

**Tests:**

- `cd packages/assets && poetry run pytest`

---

## CAR-5A-002 — Add external/source asset metadata model

**Objective:**  
Add metadata fields/types required to safely represent externally sourced or operator-uploaded assets.

**Why:**  
Using online or uploaded assets can be useful, but the system must track where they came from, whether usage is allowed, and how they were imported.

**Metadata to support:**

- `source_type`
- `source_provider`
- `external_source_url`
- `source_reference_id`
- `licence_type`
- `licence_notes`
- `usage_allowed`
- `commercial_use_allowed`
- `attribution_required`
- `attribution_text`
- `imported_by`
- `imported_at`
- `original_content_hash`
- `stored_asset_id`
- `source_quality_score`
- `source_risk_notes`

**Recommended source_type values:**

- `generated`
- `operator_uploaded`
- `approved_external_source`
- `existing_registry_asset`
- `derived_from_existing`
- `package_output`
- `unknown`

**Likely files:**

- `packages/assets/src/content_lab_assets/types.py`
- `apps/api/src/content_lab_api/models/assets.py`
- `apps/api/src/content_lab_api/schemas/assets.py`
- `apps/api/migrations/versions/`
- `packages/assets/tests/`

**Implementation steps:**

1. Add `AssetSourceType` or equivalent enum.

2. Add source/provenance metadata fields or JSON schema.

3. Ensure existing generated assets remain supported.

4. Ensure uploaded/imported assets can be distinguished from generated assets.

5. Ensure unknown or unverified source assets can be flagged.

6. Add tests for source metadata validation.

**Acceptance criteria:**

- Assets can be identified as generated, uploaded, externally sourced, derived, or package outputs.
- The system can store external URL/source/provider metadata where available.
- Licence and attribution metadata can be recorded.
- Assets with unclear usage rights can be flagged.
- This metadata can later feed provenance and QA.

**Tests:**

- `cd packages/assets && poetry run pytest`
- `cd apps/api && poetry run pytest`

---

## CAR-5A-003 — Add operator-uploaded asset registration path

**Objective:**  
Allow operators to register their own PNGs, images, videos, audio, and other reusable assets into the Asset Registry and asset packs.

**Why:**  
The system should not rely only on generated assets. User-provided high-quality assets can become reusable capital for future videos.

**Supported upload/register asset types:**

- `background_image`
- `background_video`
- `object_image`
- `object_video`
- `subject_image`
- `subject_video`
- `prop_image`
- `prop_video`
- `transparent_cutout_png`
- `effect_image`
- `effect_video`
- `audio_track`
- `sound_effect`
- `voiceover`
- `design_template`

**Likely files:**

- `apps/api/src/content_lab_api/routes/assets.py`
- `apps/api/src/content_lab_api/schemas/assets.py`
- `apps/api/src/content_lab_api/services/`
- `packages/storage/src/content_lab_storage/`
- `packages/assets/src/content_lab_assets/store.py`
- `packages/assets/tests/`
- `apps/api/tests/`

**Implementation steps:**

1. Add a registration service for operator-provided assets.

2. Accept asset metadata such as:
   - asset kind
   - media type
   - niche
   - tags
   - intended use
   - source/licence notes
   - transparency/compositing metadata if known

3. Upload the asset bytes to canonical object storage.

4. Compute and store content hash.

5. Store dimensions/duration/fps metadata where possible.

6. Add the asset to an asset pack if requested.

7. Mark the asset as ready only after storage and metadata persistence succeeds.

**Acceptance criteria:**

- Operators can add reusable assets without generation.
- Uploaded assets are stored in MinIO/S3-compatible storage.
- Uploaded assets have content hashes and source metadata.
- Uploaded assets can be attached to asset packs.
- Uploaded PNGs/images/videos are first-class registry assets.

**Tests:**

- `cd packages/assets && poetry run pytest`
- `cd packages/storage && poetry run pytest`
- `cd apps/api && poetry run pytest`

---

## CAR-5A-004 — Add approved external asset import path

**Objective:**  
Add a controlled path for importing externally sourced assets from approved/licensed sources.

**Important boundary:**  
This is not a general internet scraper. The system must not blindly download random unlicensed images or videos.

The first implementation should support manually provided, operator-approved external asset references and metadata.

**Approved import examples:**

- operator provides URL + licence metadata
- operator provides source provider + asset reference
- operator confirms usage rights
- system downloads/imports only after approval
- system stores imported asset in canonical object storage

**Likely files:**

- `apps/api/src/content_lab_api/routes/assets.py`
- `apps/api/src/content_lab_api/schemas/assets.py`
- `apps/api/src/content_lab_api/services/`
- `packages/assets/src/content_lab_assets/importer.py`
- `packages/storage/src/content_lab_storage/`
- `packages/assets/tests/`
- `apps/api/tests/`

**Implementation steps:**

1. Add external asset import request schema.

2. Require source metadata:
   - external source URL or reference
   - source provider
   - licence type or usage confirmation
   - attribution requirement if known
   - intended asset kind
   - intended media type
   - intended asset pack if applicable

3. Validate that usage metadata has been provided.

4. Download/import only through approved service logic.

5. Store bytes in canonical object storage.

6. Compute content hash.

7. Persist source/provenance metadata.

8. Attach to asset pack if requested.

9. Flag asset if licence/usage data is incomplete.

**Acceptance criteria:**

- Externally sourced assets can be imported safely and intentionally.
- Random untracked online assets are not treated as safe by default.
- Imported assets are copied into canonical object storage.
- Original source and licence metadata are preserved.
- Imported assets can be reused like any other registry asset.
- Imported assets can be included in asset packs.

**Tests:**

- `cd packages/assets && poetry run pytest`
- `cd apps/api && poetry run pytest`

---

## CAR-5A-005 — Add static-vs-motion suitability decision

**Objective:**  
Add a decision rule that determines whether a planned asset can be satisfied by a static image/PNG, needs a video asset, or needs generation.

**Why:**  
Using existing PNGs/images is useful, but not every visual need can be satisfied by a static asset. Some assets require true motion or physical interaction to look realistic.

**Decision rule:**

If the planned asset is a prop, object, background, texture, simple visual symbol, or compositable foreground element, allow high-quality static image/PNG if suitable.

If the planned asset requires true motion, physical interaction, human action, liquid movement, complex camera movement, or dynamic realism, prefer source video, generated video, or layered video asset.

If a static image can be animated convincingly with transforms, allow static image plus motion transform.

If static animation would look fake or low-quality, require video/generation or replace the asset spec.

**Examples where static assets may be suitable:**

- watch PNG
- phone PNG
- frying pan PNG
- money stack PNG
- dumbbell PNG
- car cut-out
- city skyline background
- luxury room background
- product/prop image
- texture/effect still

**Examples where motion/video may be required:**

- hand stirring food
- person walking
- car driving through street
- steam rising realistically
- gym lift movement
- liquid pouring
- facial expression changing
- complex physical interaction

**Likely files:**

- `packages/assets/src/content_lab_assets/acquisition.py`
- `packages/assets/src/content_lab_assets/types.py`
- `packages/assets/tests/`

**Implementation steps:**

1. Add motion suitability fields to planned asset specs or acquisition decisions:
   - `requires_true_motion`
   - `static_asset_allowed`
   - `static_with_motion_transform_allowed`
   - `preferred_media_type`
   - `motion_reason`

2. Add simple rule-based evaluation for static/image/video/generation suitability.

3. Connect this evaluation to the acquisition ladder.

4. Add tests for common examples.

**Acceptance criteria:**

- The system does not use static PNGs where true motion is required.
- The system can use static PNGs/images where they are appropriate.
- The system can recommend video/generation for dynamic assets.
- The decision is recorded and explainable.

**Tests:**

- `cd packages/assets && poetry run pytest`

---

## CAR-5A-006 — Connect source-first acquisition to Asset Pack creation

**Objective:**  
Modify Asset Pack creation so planned assets are fulfilled through the acquisition ladder before new generation is requested.

**Why:**  
Asset packs should be intentional and cost-efficient. If an asset can be reused, uploaded, or imported, the system should not generate it unnecessarily.

**Flow:**

asset_pack_plan  
→ planned_asset_specs  
→ acquisition decision per planned asset  
→ reuse/import/upload/generate/block  
→ registered pack assets

**Implementation steps:**

1. For each planned asset spec, run source-first acquisition.

2. Search existing Asset Registry first.

3. Check user-provided/uploaded assets if available.

4. Allow approved external source import where provided.

5. Generate only if reuse/import/upload is not suitable.

6. Record the decision and rationale.

7. Add selected/generated/imported asset to the asset pack.

8. Keep pack creation observable through runs/tasks where applicable.

**Acceptance criteria:**

- Asset Pack creation no longer assumes all assets need generation.
- Reuse/import/upload decisions are visible and explainable.
- New generation is reduced where suitable existing/source assets exist.
- Pack assets still end up as normal ready assets in the registry.
- The system remains compatible with later component-aware AssetKey work.

**Tests:**

- `cd packages/assets && poetry run pytest`
- `cd apps/api && poetry run pytest`

---

## CAR-5A-007 — Add source-first provenance requirements

**Objective:**  
Ensure all reused, uploaded, imported, and generated assets can be explained in provenance.

**Why:**  
If the system uses external or uploaded assets, the final package must still be traceable and trustworthy.

**Provenance must record:**

- `asset_id`
- `asset_kind`
- `media_type`
- `source_type`
- `source_provider`
- `external_source_url` or reference if available
- `licence_type`
- `usage_allowed`
- `attribution_required`
- `attribution_text`
- `original_content_hash`
- `stored_content_hash`
- `derived_from_asset_id` if applicable
- `imported_at`
- generation/provider params if generated
- transform recipe if transformed
- `used_in_reel_id`
- `used_as_component_role`

**Implementation steps:**

1. Extend asset provenance payloads to include source-first metadata.

2. Ensure uploaded/imported assets are included in final package provenance.

3. Ensure externally sourced assets include attribution data where required.

4. Ensure missing/unclear licence metadata can be surfaced as QA warning/failure later.

5. Add tests for provenance payloads across generated, uploaded, imported, and derived assets.

**Acceptance criteria:**

- Provenance works for generated assets.
- Provenance works for uploaded assets.
- Provenance works for approved external source assets.
- Provenance works for derived/transformed assets.
- Final package provenance can explain where every component came from.

**Tests:**

- `cd packages/assets && poetry run pytest`
- `cd packages/qa && poetry run pytest`

---

## CAR-5A-008 — Add licence/source QA gate placeholder

**Objective:**  
Add a basic QA gate or placeholder decision surface for checking whether sourced/imported assets have sufficient usage metadata before packaging.

**Why:**  
The system should not package outputs using unverified external assets without at least warning or blocking depending on policy.

**Phase-1 behaviour:**

- generated asset → pass
- operator uploaded with usage confirmation → pass or warn
- approved external asset with licence metadata → pass
- external asset missing usage metadata → warn or fail depending on policy
- unknown source → warn or fail depending on policy

**Likely files:**

- `packages/qa/src/content_lab_qa/source_rights.py`
- `packages/qa/tests/`
- `packages/assets/src/content_lab_assets/types.py`

**Implementation steps:**

1. Add a source-rights QA result type.

2. Check source_type and licence metadata.

3. Return pass/warn/fail.

4. Keep the first implementation simple and policy-driven.

5. Do not attempt full legal interpretation.

6. Add tests for generated, uploaded, approved external, and unknown source assets.

**Acceptance criteria:**

- Unknown/unverified external assets do not silently pass.
- Source/licence metadata can be surfaced before package readiness.
- QA remains simple and extensible.
- The system does not pretend to provide legal clearance.

**Tests:**

- `cd packages/qa && poetry run pytest`

---

## Final outcome of EPIC 5A

After this epic, the system has a source-first acquisition layer.

Asset Pack creation can now fulfil planned assets through:

- reuse existing asset
- reuse with transform
- operator upload
- approved external source import
- new generation
- block/replace

This means the system no longer wastes generation budget on assets that can be safely reused, uploaded, or imported.

The system can now support high-quality existing PNGs/images/videos as reusable assets while still choosing generated video when motion, specificity, style consistency, or realism requires it.

This epic must be completed before finalising component-level AssetKey and registry resolution in EPIC 6, because AssetKey, provenance, and lineage need to understand whether an asset is generated, uploaded, imported, reused, or derived.

---

# EPIC 6 — Component-aware AssetKey and registry resolution

## KEY-001 — Extend AssetKey payload with asset kind and media type
**Agent:** `codex-high`

**Objective:** Prevent different asset types from colliding.

**Rule:**

```text
background_image ≠ object_image ≠ final_render ≠ hook_text
```

Even if some text or prompts are similar.

**Implementation steps:**

1. Include `asset_kind` in canonical payload.
2. Include `media_type` in canonical payload.
3. Include source/generation/transform context.
4. Serialize in stable order.
5. Compute deterministic SHA-256 hash.
6. Add tests.

**Acceptance criteria:**

- Equivalent component requests hash identically.
- Different component roles do not collide.
- Full video and component assets are distinguishable.

---

## KEY-002 — Add generated visual asset canonicalisation
**Agent:** `codex-high`

**Objective:** Define AssetKey payloads for generated images/videos/objects/backgrounds.

**Payload should include:**

```text
asset_kind
media_type
provider
model
canonical_prompt
canonical_negative_prompt
seed
duration if video
fps if video
aspect_ratio
motion_params if video
init_image_hash if present
reference_asset_ids or hashes if present
```

**Acceptance criteria:**

- Generated background videos, object images, and full generated clips have deterministic keys.
- Different output roles do not collide.

---

## KEY-003 — Add derived/transformed asset canonicalisation
**Agent:** `codex-high`

**Objective:** Define AssetKeys for derived assets such as cut-outs, resized assets, reframed videos, and colour-treated assets.

**Payload should include:**

```text
asset_kind
media_type
source_asset_id or source_content_hash
transform_recipe
transform_recipe_version
output_parameters
```

**Acceptance criteria:**

- A transparent cut-out derived from a source image has its own key.
- A resized/reframed asset has its own key.
- Transform outputs are reproducible.

---

## KEY-004 — Add text, overlay, audio, and final-render canonicalisation
**Agent:** `codex-high`

**Objective:** Make non-video creative components reusable and deterministic.

**Overlay/text payload:**

```text
asset_kind
canonical_text
timing
layout
safe_area
template_version
style
```

**Audio payload:**

```text
asset_kind
audio_identity
trim_range
volume
normalisation
looping
```

**Final render payload:**

```text
asset_kind
ordered_source_asset_ids_or_hashes
composition_manifest_hash
edit_template_version
export_preset
render_parameters
```

**Acceptance criteria:**

- Hook/text assets can be reused.
- Audio assets can be reused.
- Final renders are deterministic derived outputs.

---

## REG-001 — Resolve assets per component requirement
**Agent:** `codex-high`

**Objective:** Registry resolution should operate on each required component, not only the final video.

**Example:**

```text
resolve background_video
resolve object_png
resolve hook_text
resolve audio_track
resolve effect_layer
```

**Implementation steps:**

1. Accept component requirement payload.
2. Canonicalise to AssetKey.
3. Return registry decision.
4. Create staged asset intent if no reusable asset exists.
5. Preserve decision metadata.

**Acceptance criteria:**

- The registry can resolve individual scene parts.
- Full-video generation is not the only path.
- Missing components are staged/generated individually.

---

## REG-002 — Add future-safe decision model
**Agent:** `codex-medium`

**Objective:** Support the four intended registry decisions.

**Decision types:**

```text
reuse_exact
reuse_with_transform
generate
blocked
```

**Phase 1:**

- `reuse_exact` mandatory
- `generate` mandatory
- `reuse_with_transform` typed/future-safe
- `blocked` typed/future-safe or policy-only

**Acceptance criteria:**

- API/worker/flow contracts will not need to break later.
- Mutation and blocking can be added progressively.

---

## REG-003 — Add component-level asset_usage lineage
**Agent:** `codex-high`

**Objective:** Track which assets/components were used in each reel.

**Suggested fields:**

```text
asset_usage_id
org_id
reel_id
asset_id
component_role
layer_role
sequence_index
z_index
start_time
end_time
transform_recipe
transform_version
metadata_json
created_at
```

**Implementation steps:**

1. Add or extend `asset_usage` as authoritative lineage table.
2. Keep `run_assets` as compatibility-only if still present.
3. Record every component used in final composition.
4. Include transform metadata.
5. Add tests.

**Acceptance criteria:**

- The system can answer: which assets made this reel?
- Provenance can be generated from component lineage.
- Asset-level performance attribution becomes possible.

---

# EPIC 7 — Compatibility and Asset Combinator Engine

## COMBO-001 — Add asset compatibility metadata
**Agent:** `codex-high`

**Objective:** Store what each asset works well with.

**Compatibility dimensions:**

```text
niche
topic
theme
emotion
visual_style
pace
format_type
works_as_background_for
works_with_object_types
works_with_audio_moods
works_with_hook_types
requires_transparency
requires_safe_area
```

**Implementation steps:**

1. Add compatibility metadata model.
2. Add metadata to pack-planned assets.
3. Add filters for compatible asset combinations.
4. Add tests with sample asset packs.

**Acceptance criteria:**

- The system can avoid nonsensical combinations.
- Asset packs become more useful for reel generation.

---

## COMBO-002 — Implement simple filtered Asset Combinator
**Agent:** `codex-high`

**Objective:** Generate possible reel combinations from existing asset packs.

**Input:**

```text
asset_pack_id
target_reel_count
optional format filters
optional style filters
```

**Output:**

```text
candidate_compositions[]
```

Each candidate may include:

```text
background
foreground/object/subject assets
hook
caption/overlay plan
audio
effect/transition
format/template
```

**Implementation steps:**

1. Load asset pack.
2. Filter by compatibility metadata.
3. Create valid combinations.
4. Rank initially by simple heuristics.
5. Avoid duplicates.

**Acceptance criteria:**

- One asset pack can produce many candidate reels.
- Combinations are not purely random.
- Output can feed the composition manifest.

---

## COMBO-003 — Add output potential estimation
**Agent:** `codex-high`

**Objective:** Estimate how many useful reels an asset pack can support.

**Implementation steps:**

1. Count valid combinations under compatibility rules.
2. Estimate diversity across backgrounds/hooks/audio/formats.
3. Identify bottlenecks, such as too few backgrounds or too few hooks.
4. Suggest additional assets if output potential is weak.

**Acceptance criteria:**

- The system can say whether an asset pack is useful enough.
- Initial asset choices can be improved before generation spend.

---

## COMBO-004 — Add performance-weighted combination selection
**Agent:** `codex-high`

**Objective:** Upgrade from filtered/random combinations to performance-informed combinations.

**Phase:** Later phase, after asset-level metrics exist.

**Implementation steps:**

1. Load historical performance for hooks, backgrounds, objects, audio, and formats.
2. Score combinations.
3. Balance exploit/explore/mutation/chaos modes.
4. Avoid overusing the same winning asset.

**Acceptance criteria:**

- Strong assets get reused intelligently.
- Overused assets can cool down.
- Performance weighting does not remove novelty entirely.

---

# EPIC 8 — Reverse Idea Generator

## REV-001 — Generate ideas from existing assets
**Agent:** `codex-high`

**Objective:** Create video ideas from the asset bank, not only from external trends or briefs.

**Example:**

```text
background: Lamborghini at night
object/subject: person working alone
hook: Nobody sees this part...
audio: dark piano
format: success sacrifice POV
→ idea: Nobody sees this part of success
```

**Implementation steps:**

1. Take selected assets or an asset pack as input.
2. Identify compatible hooks, formats, and emotional angles.
3. Produce candidate reel concepts.
4. Link concept candidates back to source assets.
5. Return structured briefs.

**Acceptance criteria:**

- The system can create ideas from assets.
- Asset packs actively drive future content creation.

---

## REV-002 — Add asset-led brief generation
**Agent:** `codex-high`

**Objective:** Convert an asset combination into a structured reel brief.

**Brief should include:**

```text
concept_title
hook
visual_sequence
selected_asset_ids
composition_intent
overlay_plan
audio_direction
caption_angle
posting_plan_seed
```

**Acceptance criteria:**

- Existing assets can create actionable briefs.
- The brief can feed the existing process_reel flow later.

---

# EPIC 9 — Composition manifest and layered reel assembly

## COMP-001 — Define CompositionManifest schema
**Agent:** `codex-high`

**Objective:** Define the structured instructions for layering assets into a final reel.

**Manifest fields:**

```text
canvas_width: 1080
canvas_height: 1920
duration
fps
background_layer
layers[]
audio_layers[]
export_preset
```

**Layer fields:**

```text
layer_id
asset_id
asset_kind
media_type
z_index
start_time
end_time
x
y
width
height
scale
opacity
crop
rotation
mask_mode
blend_mode
animation
motion_transform
safe_area_constraints
```

**Implementation steps:**

1. Add schema in `packages/editing` or shared domain types.
2. Validate layer timing and z-index ordering.
3. Validate asset type compatibility.
4. Add tests.

**Acceptance criteria:**

- Layered reel composition has a concrete contract.
- The registry does not own composition logic.
- Editing can consume the manifest.

---

## COMP-002 — Implement first layered FFmpeg compositor
**Agent:** `codex-xhigh`

**Objective:** Compose images/videos/text/audio into a vertical reel.

**Phase 1 scope:**

- one background image/video
- one or more foreground image layers
- basic text overlay
- one audio track
- final 1080x1920 MP4

**Implementation steps:**

1. Download/stage assets from object storage.
2. Build FFmpeg filter graph from manifest.
3. Handle image duration.
4. Handle video scaling/cropping.
5. Handle PNG alpha where available.
6. Add audio track.
7. Export final render.
8. Store final render as derived asset/package artifact.

**Acceptance criteria:**

- A reel can be produced from layered assets.
- PNG object layering works.
- Background + foreground + text + audio can render.

---

## COMP-003 — Add motion transforms for static assets
**Agent:** `codex-xhigh`

**Objective:** Make PNG/static assets feel like real video.

**Motion transforms:**

```text
slow_zoom
pan_left
pan_right
float
scale_in
scale_out
shake_light
parallax_basic
```

**Implementation steps:**

1. Define transform presets.
2. Add transform parameters to manifest.
3. Implement basic FFmpeg expressions.
4. Add tests/render fixtures.

**Acceptance criteria:**

- Static image assets can contribute to realistic motion.
- Object PNGs can feel intentionally animated rather than pasted.

---

## COMP-004 — Add composition realism constraints
**Agent:** `codex-high`

**Objective:** Avoid obvious fake-looking layered outputs.

**Checks/constraints:**

- foreground object not too large/small
- object stays within frame
- text does not cover critical object area
- background/object style compatibility
- duration and motion not awkward
- safe-area respected
- alpha/edge issues flagged where detectable

**Acceptance criteria:**

- The system has early safeguards against AI-slop/pasted-object outputs.
- Realism checks can fail or warn before package readiness.

---

# EPIC 10 — Provenance and package graph

## PROV-001 — Generate provenance from component graph
**Agent:** `codex-high`

**Objective:** Provenance must explain the layered asset graph, not just the final video.

**Provenance should include:**

```text
reel_id
asset_pack_id if used
composition_manifest_hash
source_assets[]
derived_assets[]
final_render_asset_id
package_artifacts[]
transforms[]
provider_jobs[]
prompts/params where applicable
editor_version
render_timestamp
```

**Implementation steps:**

1. Read `asset_usage` records.
2. Read generation params/provider jobs.
3. Read transform recipes.
4. Read composition manifest.
5. Write provenance JSON.

**Acceptance criteria:**

- Operators can see how a reel was made.
- Every component asset is traceable.
- Final output is explainable.

---

## PROV-002 — Store composition manifest as package artifact
**Agent:** `codex-medium`

**Objective:** Preserve exact composition instructions alongside the final package.

**Implementation steps:**

1. Write `composition_manifest.json` as optional package artifact.
2. Hash it.
3. Reference it from provenance.
4. Include it in package manifest if present.

**Acceptance criteria:**

- The final render can be audited/reproduced more easily.
- Provenance is tied to actual composition instructions.

---

# EPIC 11 — QA for layered assets and realism

## QA-LAYER-001 — Validate source asset availability
**Agent:** `codex-medium`

**Objective:** Ensure all assets needed for a layered composition exist before rendering.

**Checks:**

- storage URI exists
- object exists in MinIO/S3
- content hash present where required
- media type matches expected type
- asset status is ready

**Acceptance criteria:**

- Missing component assets cannot create ghost renders.
- Composition fails clearly before render if assets are unavailable.

---

## QA-LAYER-002 — Validate composition manifest
**Agent:** `codex-medium`

**Objective:** Ensure manifest is structurally valid before FFmpeg execution.

**Checks:**

- canvas dimensions valid
- layer start/end within duration
- no negative times
- z-index order valid
- image/video/audio layer types valid
- required background exists
- export preset valid

**Acceptance criteria:**

- Bad manifests fail before expensive rendering.
- Errors are operator-readable.

---

## QA-LAYER-003 — Validate layered output format
**Agent:** `codex-high`

**Objective:** Check rendered output meets reel requirements.

**Checks:**

- 1080x1920 output
- valid MP4
- valid duration
- audio track present or intentional silence
- cover image generated
- package artifacts complete

**Acceptance criteria:**

- Layered composition output meets package requirements.
- Broken renders cannot become ready packages.

---

## QA-LAYER-004 — Add first realism/AI-slop QA warnings
**Agent:** `codex-high`

**Objective:** Catch obvious low-quality layered outputs.

**Checks may include:**

- text too small or off-frame
- object layer clipped unintentionally
- foreground object lacks transparency when transparency expected
- missing background
- too many layers cluttering frame
- visual style mismatch warning

**Acceptance criteria:**

- The system can warn or fail obviously bad compositions.
- This supports the goal of realistic outputs.

---

# EPIC 12 — Asset-level performance tracking

## MET-001 — Track asset usage counts
**Agent:** `codex-medium`

**Objective:** Track how often each asset is used.

**Metrics:**

```text
reuse_count
last_used_at
used_in_reel_count
used_in_pack_count
used_as_component_role counts
```

**Acceptance criteria:**

- The system can avoid overusing the same assets.
- Cooldown/repetition policies have data.

---

## MET-002 — Track performance per component asset
**Agent:** `codex-high`

**Objective:** Attribute reel performance back to component assets.

**Track by:**

- hook asset
- background asset
- object/prop asset
- subject asset
- audio asset
- format/template
- effect/transition
- composition pattern

**Implementation steps:**

1. Join reel performance to asset_usage.
2. Aggregate by component role.
3. Store asset-level performance summaries.
4. Avoid claiming causal certainty too early.

**Acceptance criteria:**

- The system can learn which assets perform well.
- Future packs can prioritise high-performing asset types.

---

## MET-003 — Add combination performance tracking
**Agent:** `codex-high`

**Objective:** Track which groups of assets work together.

**Examples:**

```text
background + hook
audio + format
object + emotional angle
background + object + hook + audio
```

**Acceptance criteria:**

- The system can learn winning combinations.
- The combinator can become performance-weighted later.

---

# EPIC 13 — API control plane additions

## API-PACK-001 — Add Asset Pack API routes
**Agent:** `codex-medium`

**Objective:** Allow operators/web UI to create and manage asset packs.

**Routes may include:**

```text
POST /asset-packs
GET /asset-packs
GET /asset-packs/{id}
POST /asset-packs/{id}/plan
POST /asset-packs/{id}/approve
POST /asset-packs/{id}/generate
GET /asset-packs/{id}/items
```

**Acceptance criteria:**

- Operators can create packs with user-defined asset counts.
- Pack planning and approval are API-visible.

---

## API-ASSET-001 — Add component-aware asset routes
**Agent:** `codex-medium`

**Objective:** Support browsing/querying image, video, object, background, audio, and text assets.

**Filters:**

```text
asset_kind
media_type
niche
tags
asset_pack_id
has_transparency
ready_status
performance_score
reuse_count
```

**Acceptance criteria:**

- Operators can inspect assets by type and role.
- Asset library is not just a list of videos.

---

## API-COMBO-001 — Add asset combinator endpoint
**Agent:** `codex-high`

**Objective:** Generate possible reel combinations from an asset pack.

**Input:**

```text
asset_pack_id
target_reel_count
filters
mode
```

**Output:**

```text
candidate_compositions[]
```

**Acceptance criteria:**

- API can return asset-led reel candidates.
- Candidates can later feed process_reel/composition flows.

---

## API-COMP-001 — Add composition preview/submit route
**Agent:** `codex-medium`

**Objective:** Allow a selected asset combination/composition manifest to be rendered.

**Acceptance criteria:**

- API can trigger composition work through orchestrator/worker.
- The API does not render inline.

---

# EPIC 14 — Web/operator surface additions

## WEB-PACK-001 — Add Asset Library view
**Agent:** `composer2`

**Objective:** Let operators view reusable assets beyond full videos.

**View should show:**

- asset thumbnail/preview
- asset kind
- media type
- pack membership
- tags
- transparency/layer suitability
- reuse count
- performance score

**Acceptance criteria:**

- Operator can browse backgrounds, PNG objects, videos, hooks, audio, and final outputs separately.

---

## WEB-PACK-002 — Add Asset Pack Planner UI
**Agent:** `composer2`

**Objective:** Let operator create user-defined asset packs.

**Inputs:**

- niche
- total asset count
- optional asset split
- target reel types
- style constraints
- generation budget/quality level if available

**Acceptance criteria:**

- Operator controls pack size.
- UI shows proposed plan before generation.

---

## WEB-PACK-003 — Add Asset Pack Review UI
**Agent:** `composer2`

**Objective:** Let operator approve or refine the asset pack plan.

**View should show:**

- planned asset specs
- reason for each category
- expected reel formats
- estimated output potential
- mix summary
- warnings/bottlenecks

**Acceptance criteria:**

- Asset packs are intentional and reviewable.
- Operator can stop poor pack plans before generation.

---

## WEB-COMBO-001 — Add Asset Combinator view
**Agent:** `composer2`

**Objective:** Let operator see possible reel combinations from a pack.

**View should show:**

- selected background
- selected foreground/object/subject assets
- hook
- audio
- format/template
- estimated output score
- render/queue action

**Acceptance criteria:**

- Operator can create reels from existing assets.
- The asset-led production loop is visible.

---

# EPIC 15 — Workflow and worker additions

## FLOW-PACK-001 — Add generate_asset_pack flow
**Agent:** `codex-high`

**Objective:** Orchestrate asset pack planning and generation.

**Flow:**

```text
validate request
→ create pack
→ create plan
→ approve or auto-approve if configured
→ resolve existing assets
→ generate missing assets
→ register assets
→ mark pack ready
→ emit notification
```

**Acceptance criteria:**

- Asset pack generation is observable through runs/tasks.
- Batch generation is not hidden inside API calls.

---

## FLOW-COMBO-001 — Add asset_pack_to_reels flow
**Agent:** `codex-high`

**Objective:** Create reel candidates from an asset pack.

**Flow:**

```text
load pack
→ generate/retrieve candidate combinations
→ create composition manifests
→ optionally render selected candidates
→ package outputs
```

**Acceptance criteria:**

- The system can create reels from the asset bank.
- The flow is separate from but compatible with process_reel.

---

## WORKER-COMP-001 — Add layered composition worker actor
**Agent:** `codex-xhigh`

**Objective:** Render a composition manifest into final media.

**Steps:**

1. Load manifest.
2. Fetch source assets.
3. Validate availability.
4. Render with FFmpeg.
5. Store final render.
6. Extract cover.
7. Update asset/reel/package state.

**Acceptance criteria:**

- Layered composition runs asynchronously.
- Failures are retry-safe and visible.

---

# EPIC 16 — End-to-end tests and regression protection

## E2E-CAR-001 — Add component AssetKey regression test
**Agent:** `codex-medium`

**Objective:** Prove assets of different component roles do not collide.

**Test cases:**

- same text as hook_text and caption_text should differ
- same prompt as background_image and object_image should differ
- generated_clip and final_render should differ
- transparent_cutout_png and source_image should differ

**Acceptance criteria:**

- AssetKey canonicalisation is component-aware.

---

## E2E-PACK-001 — Add asset pack planning smoke test
**Agent:** `codex-medium`

**Objective:** Prove a user-defined asset count creates a valid plan.

**Test:**

```text
niche = luxury mindset
requested_asset_count = 30
```

Expected:

- pack created
- plan created
- exactly 30 planned asset specs
- rationale exists
- mix is valid

---

## E2E-PACK-002 — Add asset pack generation/registration smoke test
**Agent:** `codex-high`

**Objective:** Prove assets can be generated or registered into a pack.

**Acceptance criteria:**

- pack moves to ready
- asset records created
- storage URIs exist
- pack items link to assets

---

## E2E-COMP-001 — Add layered composition smoke test
**Agent:** `codex-xhigh`

**Objective:** Prove a reel can be built from layered assets.

**Fixture composition:**

```text
background image/video
+ transparent PNG object
+ hook overlay
+ audio
→ final_video.mp4
```

**Acceptance criteria:**

- final video renders
- output is 1080x1920
- cover exists
- provenance lists all source assets

---

## E2E-COMP-002 — Add asset pack to multiple reels smoke test
**Agent:** `codex-high`

**Objective:** Prove one asset pack can create multiple different reel candidates.

**Test:**

```text
create pack with backgrounds, objects, hooks, audio
run combinator for 5 candidates
render at least 2 candidates
```

**Acceptance criteria:**

- candidates use overlapping reusable assets
- final renders differ
- asset_usage records component lineage

---

## E2E-NO-FULL-VIDEO-ONLY — Regression test against full-video-only design
**Agent:** `codex-high`

**Objective:** Ensure the system never regresses to treating only complete generated videos as assets.

**Test assertions:**

- image assets can be registered
- transparent PNG assets can be registered
- background assets can be registered
- hook/text assets can be registered
- audio assets can be registered
- final render is derived from component assets
- asset_usage records component roles

**Acceptance criteria:**

- Component assets are first-class.
- Full video clip is not the only asset pathway.

---

# 17. Definition of Done for this backlog stream

This backlog stream is complete when:

1. Assets are no longer modelled only as full video clips.
2. PNG/image assets are first-class.
3. Transparent cut-out/object assets are first-class.
4. Background images/videos are first-class.
5. Object, prop, subject, foreground, audio, text, effect, and transition assets are representable.
6. Final render is distinct from reusable component assets.
7. Asset packs can be created for a niche.
8. Asset pack size is operator-defined.
9. Asset pack choices are intentional and plan-led.
10. Asset packs are reusable but not exhaustive.
11. Initial asset choices are optimised for future reel output potential.
12. Existing assets can generate ideas through reverse idea generation.
13. Asset combinator can create valid reel candidates from an asset pack.
14. Composition manifest can describe layered visual/audio/text assets.
15. FFmpeg compositor can render at least a basic layered reel.
16. Provenance includes the component graph.
17. QA validates layered source assets, composition manifests, and package outputs.
18. Asset-level usage and performance can be tracked.
19. Operators can inspect asset packs and asset library contents.
20. End-to-end tests prove a pack can become multiple reels.

---

# 18. Things this backlog explicitly does not do

This backlog does not:

- replace the current scaffold
- create a new repo layout
- introduce a new video provider
- replace Runway `gen4.5` as v1 provider
- replace FastAPI, Prefect, Dramatiq, Redis, Postgres, MinIO, or FFmpeg
- make autonomous posting part of MVP
- turn the Asset Registry into an editor
- treat local temp folders as authoritative storage
- pretend advanced similarity/performance learning exists before data is available
- require a perfect complete asset universe before reels can be created

---

# 19. Recommended first implementation slice

The safest first implementation slice is:

```text
CAR-000 Audit current asset implementation
CAR-001 Add AssetKind taxonomy
CAR-002 Add MediaType taxonomy
CAR-003 Add transparency/alpha metadata
KEY-001 Extend AssetKey with asset kind and media type
E2E-CAR-001 Add component AssetKey regression test
```

This first slice gives the system the basic vocabulary needed to stop treating assets as only full videos.

After that, move to:

```text
PACK-001 AssetPack entity
PACK-003 PlannedAssetSpec model
PLAN-001 Asset Pack Plan generator
PLAN-002 User-defined count/mix validation
PLAN-003 Output-potential scoring
```

Then:

```text
REG-003 Component-level asset_usage lineage
COMP-001 CompositionManifest schema
COMP-002 Basic layered FFmpeg compositor
PROV-001 Provenance from component graph
E2E-COMP-001 Layered composition smoke test
```

---

# 20. Key product statement

The target system is not just a content generator.

It is a content factory with memory.

Assets are reusable building blocks.

Asset packs are intentional starter libraries for a niche.

Ideas can create assets, but assets can also create ideas.

Final reels are composed from layered, reusable parts, and every component is tracked for reuse, provenance, QA, and performance learning.
