# Graph Report - content-lab  (2026-08-21)

## Corpus Check
- 616 files · ~3,726,371 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 7797 nodes · 20104 edges · 369 communities (288 shown, 81 thin omitted)
- Extraction: 92% EXTRACTED · 8% INFERRED · 0% AMBIGUOUS · INFERRED: 1648 edges (avg confidence: 0.93)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `761626db`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- routes/asset_packs.py
- models/__init__.py
- planner.py
- combinator.py
- overlays.py
- routes/policy.py
- types.ts
- flows/process_reel.py
- content_lab_assets/registry.py
- MediaType
- templates.py
- services/asset_packs.py
- routes/reels.py
- schemas/__init__.py
- routes/runs.py
- AssetKind
- _components/page-workspace.tsx
- deps/__init__.py
- ProcessReelExecution
- app/page-workspace.tsx
- TextOverlay
- routes/assets.py
- lint_script_output
- flows/storage_integrity_check.py
- package.py
- ffmpeg.py
- daily_reel_factory.py
- posting_plan.py
- Any
- Page
- Settings
- provider_job_sweeper.py
- content_lab_assets/provenance.py
- StoredRunwayGeneration
- content_lab_outbox/store.py
- planning_schema.py
- test_flow.py
- operator-dashboard.ts
- script_generator.py
- persist_asset_content
- Any
- AssetPackGenerationWorkspace
- runway/__init__.py
- test_operational_models.py
- director.py
- Any
- RunwayGen45Client
- single_prompt_reel_planner.py
- overlay.py
- DomainModel
- prompt_compiler.py
- editor_basic.py
- ReelFamily
- evaluate_user_facing_text
- content_lab_creative/__init__.py
- composition_preflight.py
- outbox_dispatcher.py
- CompositionManifest
- repetition.py
- FakeRunwayStore
- package_builder.py
- SmokeRunner
- 8ac8e82f-d112-4e08-b77a-b4e07dddb798/package.json
- layout.py
- support_surface_overlap.py
- QAResult
- content_lab_assets/__init__.py
- build_phase_one_process_reel_executor
- HookImageCreator
- harmonisation.py
- PersonaProfile
- test_layered_ffmpeg.py
- content_lab_storage/__init__.py
- devDependencies
- editing.py
- layered_ffmpeg.py
- format.py
- _plan
- budget.py
- test_editing_actor.py
- content_lab_storage/assets.py
- TimelineObject
- findings.py
- scripts/open-console.ps1
- content_lab_storage/integrity.py
- operator-page-workspace.ts
- provider.py
- base.py
- content_lab_qa/__init__.py
- repair_prompt.py
- PromptPathEligibilityGate
- schemas/asset_packs.py
- PageWorkspace
- runway.py
- validate_environment_quality
- alignment.py
- E2EComposableAssetRegistryRunner
- runtime_db_snapshot.py
- build_process_reel_runtime
- policy-editor.tsx
- relationship_layout.py
- content_lab_editing/__init__.py
- CompositionLayer
- provider_jobs.py
- S3StorageClient
- flows/__init__.py
- generate_script_output
- jobs.py
- content_lab_creative/types.py
- overlay_layout.py
- routes/packages.py
- timeline_validation.py
- validate_cinematic_plan_realism
- plan_repair.py
- qa-failure-triage.ts
- planner_prompt.py
- evaluate_semantic_script
- NoRegenRunner
- asRecord
- test_editor_basic.py
- Any
- content-lab-shared
- role_assignment.py
- validate_reel_timeline_artifact
- expected_outcome
- settings.py
- Any
- OutboxEntry
- AssetRecord
- content_lab_assets/types.py
- enforce_relationship_layout
- SQLAlchemyPhase1AssetRegistryStore
- test_asset_registry_schema.py
- Run
- LayeredCompositionRequest
- CinematicReelPlan
- build_asset_key
- build_timeline_render_trace
- Task
- compose_layered_reel
- validate_perspective_compatibility
- content_lab_runs/__init__.py
- ContentLabError
- seed_faceless_cooking_asset_pack.py
- validate_source_rights
- ts/package.json
- seed_steakpagetest_reel_pack.py
- RunwayHttpResponse
- test_asset_persistence_service.py
- content_lab_outbox/__init__.py
- S3StorageConfig
- run_tasks.py
- normalized_bounds
- semantic_script.py
- RunRecord
- test_media_timeline.py
- test_assets_resolve_routes.py
- Q: has everything been mapped
- compilerOptions
- EditInstruction
- clear_correlation_id
- configure_logging
- scripts
- validate_phase1_creative_duration_alignment
- test_cinematic_plan_routes.py
- operator-context.ts
- build_overlap_validation_context
- bootstrap-cloud-env.sh
- test_db_0008.py
- test_metrics_audio_features_migration.py
- Q: just to confirm has the whole repo been graphed and mapped
- build_provider_submission_task
- durable.py
- compilerOptions
- ApprovedImportValidationError
- idempotency_key_from_payload
- .dispatch
- test_reels_routes.py
- validate_package_provenance
- build_task_idempotency_key
- e2e_content_quality.py
- task_status_for_run_status
- TaskRowSpec
- .from_uri
- content_lab_core/types.py
- test_composition_realism.py
- _download_package
- e2e_single_prompt_plan_smoke.py
- unhandled_exception_handler
- test_reel_families_routes.py
- test_process_reel_bad_reel_regression.py
- CreativeBrief
- resolve_asset_request
- test_asset_import_approved.py
- test_overlay_render_trace_qa.py
- db_engine
- test_cli_runs_selected_named_flow
- stepOutput
- logging.py
- page-create-panel.tsx
- ._call
- ts/tsconfig.json
- worktree-cleanup.sh
- worktree-spawn.sh
- local-artifact/route.ts
- manual_reel_demo.sh
- e2e_mvp_smoke.sh
- py_check.sh script
- worktree-cleanup.ps1
- Production Architecture
- env.py
- preflight_revision_check.py
- schemas/run.py
- pytest_configure
- submitValidatedCinematicPreview
- Local Runtime Guide
- editing/tests/test_latest_trace_golden_fixture.py
- dev-stack.ps1
- e2e_no_regen.sh
- scripts/stop-console.ps1
- Continuous Integration
- Contribution Rules
- asset-packs/route.ts
- file/route.ts
- pages/route.ts
- page/[pageId]/route.ts
- Process Reel Execution
- Manual Reel Process
- Reel Package Manifest
- Reel Package Metadata
- asset_pack_to_reels.py
- build_process_reel_kwargs
- artifact-proxy/route.ts
- approve/route.ts
- [assetId]/route.ts
- cinematic-plan-prompt/route.ts
- cinematic-plan-validate/route.ts
- combinations/route.ts
- composition-renders/route.ts
- generate/route.ts
- items/route.ts
- reject/route.ts
- source-assets/route.ts
- plan/route.ts
- assets/route.ts
- [runId]/route.ts
- cinematic-plans/[runId]/generate-package/route.ts
- idea-plans/route.ts
- discard/route.ts
- idea-plans/[runId]/generate-package/route.ts
- pages/[pageId]/route.ts
- [pageId]/runs/route.ts
- [orgId]/runs/route.ts
- hook-cover/route.ts
- orgs/route.ts
- layout.tsx
- .eslintrc.json
- process_layered_composition
- Ratatouille
- Content Lab Smoke Test
- Page Policy Configuration
- Reel Trigger Request
- Golden Bad Reel Regression
- run_step
- repositories/__init__.py
- next.config.js
- next-env.d.ts
- First Three Seconds Hook
- Scroll Setup Hook
- Visual First Hook
- Operations Reset Cover
- Operations Reset Cover
- Operations
- Worktree Agent Prompts
- creative/tests/fixtures/bad_reels/__init__.py
- creative/tests/fixtures/__init__.py
- content_lab_features/__init__.py
- content_lab_ingestion/__init__.py
- content_lab_intelligence/__init__.py
- qa/tests/fixtures/__init__.py
- eslint.config.mjs
- e2e_content_quality.sh script
- ensure-scaffold-compat.sh script
- verify-bad-reel-regression.sh script
- Cooked Chicken and Mixed Vegetable Dish
- Chopped Fresh Mixed Vegetables
- Ratatouille Ingredients and Prepared Dish Infographic
- Tomato Vertical and Horizontal Cut Diagram
- Potted Fresh Basil Plant
- Cross-Section of Yellow Bell Pepper
- Bowl of Chopped Almonds
- Fresh Broccoli Head
- Cooked Chicken and Mixed Vegetable Dish
- White Chicken Egg
- Cut Eggplant Showing Interior
- Chopped Fresh Mixed Vegetables
- Block of Fresh Yeast
- Whole Ginger Root
- Wedge of Rind-Covered Goat Cheese
- Whole Red Habanero Pepper
- Lengthwise-Cut Red Jalapeno Pepper
- Ratatouille Ingredients and Prepared Dish Infographic
- Tomato Vertical and Horizontal Cut Diagram
- Cooked Chicken and Mixed Vegetable Dish
- Chopped Fresh Mixed Vegetables
- Blue Gradient Background
- Green Gradient Background
- Coral Circle
- Gold Circle
- Purple Gradient Reference
- Blue Gradient Background
- Green Gradient Background
- Coral Circle
- Gold Circle
- Purple Gradient Reference
- Black Reel Frame

## God Nodes (most connected - your core abstractions)
1. `AssetKind` - 85 edges
2. `TextOverlay` - 80 edges
3. `CinematicReelPlan` - 78 edges
4. `CompositionLayer` - 76 edges
5. `ProcessReelExecution` - 67 edges
6. `Task` - 66 edges
7. `QAResult` - 64 edges
8. `Asset` - 63 edges
9. `Org` - 63 edges
10. `Base` - 62 edges

## Surprising Connections (you probably didn't know these)
- `_seed_fixtures()` --uses--> `Org`  [INFERRED]
  scripts/demo_reel.py → apps/api/src/content_lab_api/models/org.py
- `_seed_fixtures()` --uses--> `PageKind`  [INFERRED]
  scripts/demo_reel.py → apps/api/src/content_lab_api/models/page.py
- `_seed_fixtures()` --uses--> `Page`  [INFERRED]
  scripts/demo_reel.py → apps/api/src/content_lab_api/models/page.py
- `_seed_fixtures()` --uses--> `ReelFamily`  [INFERRED]
  scripts/demo_reel.py → apps/api/src/content_lab_api/models/reel_family.py
- `build_signed_download()` --uses--> `Settings`  [INFERRED]
  apps/api/src/content_lab_api/routes/_storage.py → packages/shared/py/src/content_lab_shared/settings.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Reel Package Artifacts** — artifacts_screenshots_process_step_7_final_video, artifacts_screenshots_process_step_7_cover_image, artifacts_screenshots_process_step_7_caption_variants [EXTRACTED 1.00]
- **Composable Hook Variants** — artifacts_e2e_composable_asset_registry_20260507_214834_hook_a_first_three_seconds, artifacts_e2e_composable_asset_registry_20260507_214834_hook_b_scroll_setup, artifacts_e2e_composable_asset_registry_20260507_214834_hook_c_visual_first, artifacts_e2e_composable_asset_registry_20260507_214917_hook_a_first_three_seconds, artifacts_e2e_composable_asset_registry_20260507_214917_hook_b_scroll_setup, artifacts_e2e_composable_asset_registry_20260507_214917_hook_c_visual_first [EXTRACTED 1.00]
- **Local Runtime Operations** — docs_run_local_local_runtime_guide, docs_runtime_db_inspect_runtime_database_inspection, infra_docker_compose_local_service_stack [INFERRED 0.85]
- **Content Laboratory Architecture Documents** — readme_content_laboratory, docs_content_lab_comprehensive_stack_v2_0_scaffold_aligned_comprehensive_stack, docs_content_lab_prod_architecture_v2_0_scaffold_aligned_production_architecture, docs_content_laboratory_project_charter_v2_0_scaffold_aligned_project_charter [INFERRED 0.95]
- **Semantic Reel Regression Assets** — docs_semantic_reel_regression_lane_semantic_regression_lane, packages_creative_tests_fixtures_bad_reels_readme_shared_bad_reel_fixtures, packages_qa_tests_fixtures_bad_reels_readme_golden_bad_reel_regression [INFERRED 0.95]

## Communities (369 total, 81 thin omitted)

### Community 0 - "routes/asset_packs.py"
Cohesion: 0.12
Nodes (55): _actor_info(), _actual_asset_count_for_pack(), approve_asset_pack(), _asset_detail_out(), _asset_pack_out(), _candidate_out(), _cinematic_plan_package_payload(), _cinematic_planner_input() (+47 more)

### Community 1 - "models/__init__.py"
Cohesion: 0.04
Nodes (91): Base, ApiKey, API key metadata; store only hashes at rest (enforced in auth layer later)., Asset, AssetCombinationPerformance, Performance rollups for reusable asset combinations., Metric aggregates for a deterministic group of assets used together., AssetFamily (+83 more)

### Community 2 - "planner.py"
Cohesion: 0.07
Nodes (56): _asset_category_split(), _asset_mix_guidance(), _asset_mix_key_to_kind(), AssetPackPlanInput, AssetPackPlannedSpec, _build_pack_strategy(), _build_planned_specs(), _build_strategy_summary() (+48 more)

### Community 3 - "combinator.py"
Cohesion: 0.05
Nodes (94): AssetPerformanceSummary, Metric aggregates for an asset used in a specific component role., AssetLedConceptOut, AssetLedIdeasOut, AssetLedReelBriefOut, Structured reel brief derived from one compatible asset combination., Ranked candidate concept with source asset lineage., Asset-led concept generation result for one pack. (+86 more)

### Community 4 - "overlays.py"
Cohesion: 0.04
Nodes (84): HorizontalAlign, OverlayPosition, OverlayRole, _alpha_fade_expression(), _apply_non_overlapping_primary_track(), bottom_overlay_has_vertical_safe_area(), build_overlay_render_diagnostics(), build_rendered_overlay_manifest() (+76 more)

### Community 5 - "routes/policy.py"
Cohesion: 0.06
Nodes (79): PolicyState, get_global_policy(), get_niche_policy(), _get_org_or_404(), _get_page_or_404(), get_page_policy(), _get_policy_or_404(), _load_policy_document() (+71 more)

### Community 6 - "types.ts"
Cohesion: 0.05
Nodes (81): baseDebug, minimalReel, ApiErrorDetail, ApiErrorResponse, ApiValidationIssue, CreativeTraceSurfaceOut, FlowTrigger, GeneratedReelStatus (+73 more)

### Community 7 - "flows/process_reel.py"
Cohesion: 0.07
Nodes (86): _as_uuid(), _asset_ids(), _bounded_float(), _brief_payload_from_source_plan(), _build_package_provenance(), _build_primary_asset_prompt(), _build_timeline_render_trace(), _cinematic_composition_duration_seconds() (+78 more)

### Community 8 - "content_lab_assets/registry.py"
Cohesion: 0.06
Nodes (63): AssetResolutionDecision, AssetKey, BaseModel, Deterministic exact-match key material for a generation request., AssetReusePolicyHooks, build_decision_policy_metadata(), build_repetition_gate_payload(), CooldownPolicy (+55 more)

### Community 9 - "MediaType"
Cohesion: 0.07
Nodes (62): AssetKey models and hashing for phase-1 Runway gen4.5 generation., AudioAssetKeyPayload, canonicalise_audio(), canonicalise_derived_transform(), canonicalise_final_render(), canonicalise_overlay_text(), canonicalise_runway_gen45_generation(), _canonicalize_mapping() (+54 more)

### Community 10 - "templates.py"
Cohesion: 0.05
Nodes (63): build_scene_aware_edit_plan(), build_single_clip_edit_plan(), _ordered_scenes(), Any, BaseModel, model_validator, Scene-aware edit plan models and deterministic compilers., Compile scene-plan nodes and source assets into a deterministic edit timeline. (+55 more)

### Community 11 - "services/asset_packs.py"
Cohesion: 0.10
Nodes (78): AssetPack, AssetPackItem, PlannedAssetSpec, AssetPackBatchOut, AssetPackPlanOut, PlannedAssetSpecPlanOut, Result of batch asset-pack planning and resolution., _annotate_acquisition_for_pre_fulfilled_items() (+70 more)

### Community 12 - "routes/reels.py"
Cohesion: 0.07
Nodes (74): GeneratedReelStatus, ObservedReelStatus, str, Reel ORM model (generated variants vs observed external reels)., Canonical generated-reel lifecycle (architecture: draft through ready/posted)., Terminal states for ingested/observed reels only (no factory pipeline)., Application-level invariant aligned with DB CHECK on ``reels``., Reel (+66 more)

### Community 13 - "schemas/__init__.py"
Cohesion: 0.05
Nodes (68): Pydantic schemas for API request/response payloads., build_process_reel_operator_debug(), _coerce_mapping(), _creative_trace_surface(), CreativeTraceSurfaceOut, _merge_qa_from_tasks(), ProcessReelOperatorDebugOut, ProcessReelQASurfaceOut (+60 more)

### Community 14 - "routes/runs.py"
Cohesion: 0.09
Nodes (66): _actor_info(), _build_run_metadata(), _cinematic_composition_manifest(), _cinematic_duration_seconds(), _cinematic_narrative_text(), _cinematic_plan_artifacts(), _cinematic_plan_payload(), _cinematic_render_source_plan() (+58 more)

### Community 15 - "AssetKind"
Cohesion: 0.06
Nodes (66): AlphaQuality, AssetCompatibilityMetadata, AssetPairCompatibilityScore, AssetResolutionClass, compatibility_score(), _dedupe(), LightingDirection, LightingQuality (+58 more)

### Community 16 - "_components/page-workspace.tsx"
Cohesion: 0.08
Nodes (61): asRecord(), CreativeReviewPanel(), CreativeReviewPanelProps, formatVerdictLabel(), TabId, TABS, verdictTone(), BreadcrumbItem (+53 more)

### Community 17 - "deps/__init__.py"
Cohesion: 0.04
Nodes (47): get_db(), Session, Database session dependency for FastAPI route injection., Dependency injection providers., lifespan(), health(), get, Health-check endpoint. (+39 more)

### Community 18 - "ProcessReelExecution"
Cohesion: 0.07
Nodes (21): _assert_package_ready_for_publish(), ProcessReelExecution, ProcessReelPersistenceService, ProcessReelQAResult, ProcessReelStep, ProcessReelStepDefinition, StrEnum, Applies run/task/reel updates for each process-reel step the orchestrator runs. (+13 more)

### Community 19 - "app/page-workspace.tsx"
Cohesion: 0.04
Nodes (64): arrayBufferFromBytes(), artifactIsAvailable(), artifactSummary(), ArtifactTab, ArtifactViewer(), assertPngBlob(), AssetLibraryItem, AssetLibraryItemOut (+56 more)

### Community 20 - "TextOverlay"
Cohesion: 0.07
Nodes (55): build_drawtext_filters(), _canonicalize_overlay_role(), normalize_overlay_timeline(), overlay_opaque_plateau_interval(), OverlayLayoutError, OverlayTextPolicyError, Raised when overlay text/box is outside the frame or 9:16 safe area (no silent…, Raise :class:`OverlayLayoutError` when the estimated text+box is outside the… (+47 more)

### Community 21 - "routes/assets.py"
Cohesion: 0.06
Nodes (51): _asset_component_metadata(), _asset_detail_out(), _asset_library_item_out(), get_asset(), get_asset_download(), _get_asset_or_404(), _get_org_or_404(), import_approved_external() (+43 more)

### Community 22 - "lint_script_output"
Cohesion: 0.12
Nodes (29): computed_field, CreativeLintOutcome, _caption_only_rules_applicable(), CreativeLintFinding, CreativeLintResult, _is_cta_or_disclosure(), _lint_hook(), lint_script_output() (+21 more)

### Community 23 - "flows/storage_integrity_check.py"
Cohesion: 0.07
Nodes (42): _as_uuid(), AssetIntegrityCandidate, _build_storage_integrity_alert_payload(), build_storage_integrity_check_kwargs(), build_storage_integrity_runtime(), _combined_integrity_status(), find_recent_assets(), find_recent_reel_packages() (+34 more)

### Community 24 - "package.py"
Cohesion: 0.06
Nodes (62): _artifact_filename(), _artifact_index(), evaluate_package(), _expected_package_duration(), _finding(), _first_stream(), _has_payload(), _layered_output_metadata() (+54 more)

### Community 25 - "ffmpeg.py"
Cohesion: 0.06
Nodes (51): CommandArg, build_ffconcat_manifest(), _coerce_output(), escape_ffconcat_path(), FFmpegBinaryNotFoundError, FFmpegError, FFmpegProcessError, FFmpegRunner (+43 more)

### Community 26 - "daily_reel_factory.py"
Cohesion: 0.04
Nodes (81): orchestrator_service_context(), Defaults for shared run/task correlation in orchestration flows., AppliedPolicy, _approved_reel_count(), BudgetGuardrailChecker, build_daily_reel_factory_kwargs(), _build_run_summary_payload(), choose_target_owned_pages() (+73 more)

### Community 27 - "posting_plan.py"
Cohesion: 0.07
Nodes (46): Platform, Social-media platforms supported for reel publishing., build_posting_plan(), _clean_optional_text(), _clean_text(), _coerce_policy_document(), PostingPlanArtifact, PostingPlanCompliance (+38 more)

### Community 28 - "Any"
Cohesion: 0.09
Nodes (25): AssetPackCompositionSubmitRequest, Submit a selected composition manifest for asynchronous process_reel work., _as_uuid(), AssetPackToReelsRuntime, _candidate_payload(), _composition_manifest(), _list_of_mappings(), _list_or_none() (+17 more)

### Community 29 - "Page"
Cohesion: 0.08
Nodes (51): Page, PageKind, str, Social page ORM model (owned portfolio accounts vs competitors)., create_page(), delete_page(), _get_org_or_404(), get_page() (+43 more)

### Community 30 - "Settings"
Cohesion: 0.10
Nodes (50): Register user-provided bytes as a reusable asset pack member., SourceAssetRegisterRequest, _build_storage_client(), _create_staged_source_asset(), _decode_source_asset_data(), import_approved_external_asset(), Persist user-provided source bytes and attach the ready asset to a pack., Persist imported bytes without an asset pack (registry-only). (+42 more)

### Community 31 - "provider_job_sweeper.py"
Cohesion: 0.09
Nodes (36): _as_uuid(), build_provider_job_sweeper_kwargs(), build_provider_job_sweeper_runtime(), _expected_runway_status(), find_stale_provider_jobs(), _linked_asset_id(), _mapping(), _optional_text() (+28 more)

### Community 32 - "content_lab_assets/provenance.py"
Cohesion: 0.09
Nodes (40): build_provenance(), _clean_optional_text(), _clean_text(), _coerce_package_timestamps(), _final_render_asset_id(), _is_derived_asset(), _is_source_asset(), _normalize_asset_subset() (+32 more)

### Community 33 - "StoredRunwayGeneration"
Cohesion: 0.08
Nodes (25): FakeProcessReelAssetResolver, FakeRunwayStore, _merge_dicts(), Any, build_generation_idempotency_key(), Build the canonical phase-1 idempotency key for generated-asset intents., _mapping(), _merge_dicts() (+17 more)

### Community 34 - "content_lab_outbox/store.py"
Cohesion: 0.11
Nodes (38): compute_next_attempt_at(), emit_flow_failure(), emit_outbox_event(), emit_package_ready(), _entry_from_row(), _mapping(), _optional_datetime(), Any (+30 more)

### Community 35 - "planning_schema.py"
Cohesion: 0.08
Nodes (42): _alias_key(), AudioLayer, AudioPlan, AudioSyncPoint, BlurSpec, CameraMove, _canonicalize_raw_light_references(), _canonicalize_raw_shadow_light_id() (+34 more)

### Community 36 - "test_flow.py"
Cohesion: 0.11
Nodes (41): PhaseOneProcessReelExecutor, process_reel(), flow, Concrete phase-1 executor that keeps orchestration boundaries narrow., Run the full phase-1 ``process_reel`` package-generation workflow., _build_fixture_clip_bytes(), _build_qa_execution(), _dispatch_payloads() (+33 more)

### Community 37 - "operator-dashboard.ts"
Cohesion: 0.08
Nodes (46): ApiPage, ApiReel, ApiRunDetail, ApiRunOutbox, ApiRunTask, asRecord(), buildPackageReviewQueue(), buildTaskSummary() (+38 more)

### Community 38 - "script_generator.py"
Cohesion: 0.10
Nodes (43): BriefLike, _attach_lint_result(), _base_caption(), _build_caption_variants(), _build_hashtags(), _build_hook(), _build_overlay_timeline(), _build_pinned_comments() (+35 more)

### Community 39 - "persist_asset_content"
Cohesion: 0.13
Nodes (26): _apply_ready_state(), AssetPersistenceStateError, _build_storage_client(), _ensure_persistable(), _get_asset_or_raise(), _mark_asset_failed(), _mark_pack_items_failed(), _mark_pack_items_ready() (+18 more)

### Community 40 - "Any"
Cohesion: 0.11
Nodes (21): _as_uuid(), _asset_pack_id(), AssetPackGenerationRuntime, _list_of_text(), _load_pack(), _load_run(), _mapping(), _mapping_or_none() (+13 more)

### Community 41 - "AssetPackGenerationWorkspace"
Cohesion: 0.09
Nodes (45): activeOrgId(), apiErrorMessage(), apiErrorMessageFromText(), assetFromCandidateRole(), AssetPackGenerationWorkspace(), appendPackPasteImages(), approveSavedPack(), collectImageBlobsFromClipboard() (+37 more)

### Community 42 - "runway/__init__.py"
Cohesion: 0.05
Nodes (35): FakeRunwayClient, _build_submit_body(), _clamp_runway_duration_seconds(), clamp_runway_gen45_clip_duration_seconds(), classify_failure(), _extension_from_content_type(), HTTPRunwayClient, _int_or_default() (+27 more)

### Community 43 - "test_operational_models.py"
Cohesion: 0.10
Nodes (18): _partial_unique_index_names(), parametrize, Tests for phase-1 operational ORM tables and Alembic revision chain., Ensure the new migration file is syntactically valid and exposes revision ids., Migration smoke: revision graph loads and head is 0015., test_alembic_single_head_is_0015(), test_asset_combination_performance_default_field_values(), test_asset_default_field_values() (+10 more)

### Community 44 - "director.py"
Cohesion: 0.09
Nodes (36): _brief_tags(), _brief_tone(), _content_pillars(), _deep_merge_state(), _description(), _indefinite_article(), plan_creative_brief(), Any (+28 more)

### Community 45 - "Any"
Cohesion: 0.05
Nodes (39): _asset_usage_specs_from_package(), build_process_reel_persistence_service(), _collect_reference_values(), _first_text(), InMemoryProcessReelRepository, _looks_like_package_payload(), _merge_dicts(), _optional_dict() (+31 more)

### Community 46 - "RunwayGen45Client"
Cohesion: 0.10
Nodes (28): ensure_phase1_provider_model(), ProviderAuthenticationError, ProviderError, ProviderTaskFailedError, ProviderTransientError, RuntimeError, Provider rejected or was missing credentials., Provider failure that is safe to retry. (+20 more)

### Community 47 - "single_prompt_reel_planner.py"
Cohesion: 0.06
Nodes (73): build_master_planning_prompt(), build_plan_artifacts(), _clamp_numeric_field(), _compact_prompt_asset(), compute_plan_hash(), _is_pan_cookware_slug_token(), _iter_dicts(), MasterPromptPackage (+65 more)

### Community 48 - "overlay.py"
Cohesion: 0.11
Nodes (44): _as_int_for_json(), _authored_overlay_rows(), _coalesce_float(), default_overlay_stack_policy_for_template(), evaluate_overlay_text_fidelity_qa(), _is_valid_overlay_safe_area(), _optional_float(), _optional_int_for_area() (+36 more)

### Community 49 - "DomainModel"
Cohesion: 0.07
Nodes (25): api_key_prefix(), APIKeyRecord, hash_api_key(), Identity, _normalize_api_key(), Identity and API-key models for Content Lab authentication., Represents a hashed API key issued to a tenant or service account., Return whether ``raw_key`` matches this stored hash. (+17 more)

### Community 50 - "prompt_compiler.py"
Cohesion: 0.09
Nodes (39): compile_provider_prompt(), _compile_scene_fragment(), CompiledProviderPrompt, CompiledScenePromptFragment, _contains_meta_language(), _hash_text(), _join_prompt(), _no_legible_text_instruction() (+31 more)

### Community 51 - "editor_basic.py"
Cohesion: 0.07
Nodes (57): extract_cover_frame(), Path, Cover frame extraction helpers for rendered editing outputs., Choose a stable timestamp that stays inside the available media duration., Extract a PNG cover frame from a rendered clip., resolve_cover_frame_timestamp(), BasicEditorArtifact, _concat_segments() (+49 more)

### Community 52 - "ReelFamily"
Cohesion: 0.10
Nodes (40): ReelFamily, create_reel_family(), _get_org_or_404(), _get_page_or_404(), get_reel_family(), _get_reel_family_or_404(), list_reel_families(), Any (+32 more)

### Community 53 - "evaluate_user_facing_text"
Cohesion: 0.08
Nodes (37): CaptionPackagingResult, apply_caption_packaging(), caption_copy_has_severity_fail(), _clip(), _copy_match_to_json(), lint_caption_for_packaging(), prefilter_caption_lint_table(), Any (+29 more)

### Community 54 - "content_lab_creative/__init__.py"
Cohesion: 0.09
Nodes (33): Creative brief generation, planning, and packaging-facing artifacts., compile_scene_prompt(), Build a compact provider-facing prompt from the structured scene plan., build_alignment_context(), build_creative_trace(), CreativeTraceArtifact, CreativeTraceGeneratorSelection, _first_present() (+25 more)

### Community 55 - "composition_preflight.py"
Cohesion: 0.09
Nodes (38): coerce_source_asset_reference(), CompositionPreflightError, CompositionPreflightIssue, ensure_composition_preflight(), _format_preflight_error(), _normalize_media_type(), _optional_text(), Protocol (+30 more)

### Community 56 - "outbox_dispatcher.py"
Cohesion: 0.07
Nodes (33): outbox_drain(), Any, flow, Deliver pending outbox events using the same logic as the Dramatiq worker actor., build_dispatch_sink(), build_dispatch_store(), CompositeOutboxSink, dispatch_outbox() (+25 more)

### Community 57 - "CompositionManifest"
Cohesion: 0.13
Nodes (37): CompositionManifest, Concrete contract for rendering layered assets into one final reel., _allows_clipping(), _as_float(), _as_list(), _check_alpha_edges(), _check_background_presence(), _check_foreground_size() (+29 more)

### Community 58 - "repetition.py"
Cohesion: 0.12
Nodes (28): _aggregate_verdict(), _build_cooldown_signal(), _build_exact_reuse_signal(), _build_family_reuse_signal(), _phase1_signals(), BaseModel, datetime, model_validator (+20 more)

### Community 59 - "FakeRunwayStore"
Cohesion: 0.22
Nodes (16): _base_generation(), FakeRunwayClient, FakeRunwayStore, FakeStorageClient, _merge_dicts(), Any, StoredObject, API-created provider_jobs rows use runway-gen45:… keys; Runway GET /v1/tasks… (+8 more)

### Community 60 - "package_builder.py"
Cohesion: 0.11
Nodes (39): _asset_subset(), _build_manifest(), build_package_directory(), build_ready_to_post_package(), BuiltReelPackage, _caption_variants_for_package_payload(), _composition_layers(), _composition_transforms() (+31 more)

### Community 61 - "SmokeRunner"
Cohesion: 0.14
Nodes (11): build_parser(), main(), Any, ArgumentParser, CompletedProcess, Namespace, Path, RuntimeError (+3 more)

### Community 62 - "8ac8e82f-d112-4e08-b77a-b4e07dddb798/package.json"
Cohesion: 0.05
Nodes (40): artifacts, created_at, manifest_download, expires_at, storage_uri, url, manifest_metadata, artifact_count (+32 more)

### Community 63 - "layout.py"
Cohesion: 0.11
Nodes (36): autofit_hook_overlay(), autofit_standard_overlay(), available_text_max_width(), compute_overlay_outer_rect(), estimate_text_block(), _greedy_wrap_tokens(), HookAutofitResult, line_width_estimate_px() (+28 more)

### Community 64 - "support_surface_overlap.py"
Cohesion: 0.10
Nodes (36): _canvas_to_mask_uv(), check_on_surface_support_region(), decode_support_surface_mask(), evaluate_on_surface_support_region(), _letterbox_uv(), _mask_uv_to_canvas(), OnSurfaceSupportRegionResult, overlap_artifacts_for_support() (+28 more)

### Community 65 - "QAResult"
Cohesion: 0.10
Nodes (15): Serialize into the shared QA result envelope., _details_include_blocking_code(), Any, Protocol, qa_result_blocks_readiness(), QAGate, QAResult, QA gate models and protocol for content validation checks. (+7 more)

### Community 66 - "content_lab_assets/__init__.py"
Cohesion: 0.08
Nodes (46): acquisition_decision_for_compatible_registry_reuse(), acquisition_decision_for_operator_upload(), _acquisition_traits(), AcquisitionDecision, _all_high(), AssetAcquisitionPath, default_generated_source_metadata(), evaluate_acquisition_before_generation() (+38 more)

### Community 67 - "build_phase_one_process_reel_executor"
Cohesion: 0.07
Nodes (29): build_phase_one_process_reel_executor(), build_process_reel_event_sink(), _build_storage_client(), emit_process_reel_terminal_event(), ProcessReelAssetResolver, ProcessReelEventSink, ProcessReelPlanningContextLoader, ProcessReelStorageClient (+21 more)

### Community 68 - "HookImageCreator"
Cohesion: 0.07
Nodes (35): assetPackCountLabel(), bestAsset(), clamp(), commaSeparatedValues(), downloadJsonArtifact(), editableHookGenerationForId(), formatAssetPackOption(), formatJson() (+27 more)

### Community 69 - "harmonisation.py"
Cohesion: 0.11
Nodes (33): LayerHarmonisationPass, Per-layer colour and edge harmonisation applied during FFmpeg composition., analyse_foreground_layer(), analyse_scene_region(), build_harmonisation_filter_segments(), build_harmonisation_params_for_layer(), _channel_gain(), default_harmonisation_for_layer() (+25 more)

### Community 70 - "PersonaProfile"
Cohesion: 0.11
Nodes (24): Persona and page-constraint models for creative planning., Backward-compatible imports for persona schema models., _clean_extension_key(), _clean_list(), _clean_text(), PageConstraints, PageMetadata, PersonaProfile (+16 more)

### Community 71 - "test_layered_ffmpeg.py"
Cohesion: 0.16
Nodes (16): CompletedProcess, run_command(), _DownloadedObject, _FakeAssetStorageClient, _FakeRunner, _FakeStorageClient, _manifest(), Path (+8 more)

### Community 72 - "content_lab_storage/__init__.py"
Cohesion: 0.06
Nodes (46): StoredObject, Canonical S3-compatible storage client for Content Lab., Configuration models shared across S3-compatible storage helpers., MinIO/S3 object storage client and helpers., CanonicalStorageLayout, _normalize_id(), Canonical S3 object paths for phase-1 assets and reel packages., Stable object refs for the canonical reel package outputs. (+38 more)

### Community 73 - "devDependencies"
Cohesion: 0.05
Nodes (37): dependencies, @content-lab/shared-ts, next, react, react-dom, devDependencies, eslint, eslint-config-next (+29 more)

### Community 74 - "editing.py"
Cohesion: 0.10
Nodes (32): _artifact_metadata(), _artifact_payload(), _asset_usage_specs(), CoverExtractor, _json_bytes(), _layer_role(), LayeredCompositionRenderer, LayeredCompositionStorageClient (+24 more)

### Community 75 - "layered_ffmpeg.py"
Cohesion: 0.11
Nodes (38): MotionPreset, _between(), build_layered_ffmpeg_args(), build_layered_filter_graph(), _crop_filter(), _drawtext_filter(), _escape_drawtext(), _expr_number() (+30 more)

### Community 76 - "format.py"
Cohesion: 0.15
Nodes (35): _audio_check(), _audio_video_sync_check(), _build_report(), _coerce_float(), _coerce_int(), _cover_exists_check(), _duration_check(), _duration_seconds() (+27 more)

### Community 77 - "_plan"
Cohesion: 0.11
Nodes (45): Validate scene coherence with the default deterministic validator., validate_scene_coherence(), _failure_codes(), test_background_reveal_stays_behind_hero(), test_duplicate_role_asset_must_be_rejected_or_fails(), test_failed_plan_emits_structured_failure_codes(), test_floating_collage_plan_fails(), test_hero_remains_visually_dominant() (+37 more)

### Community 78 - "budget.py"
Cohesion: 0.13
Nodes (27): _provider_submission_budget_guardrail(), _budget_mapping(), budget_policy_from_mapping(), budget_usage_from_mapping(), BudgetGuardrailDecision, BudgetPolicy, BudgetUsage, _coerce_money() (+19 more)

### Community 79 - "test_editing_actor.py"
Cohesion: 0.15
Nodes (25): fake_cover_extractor(), FakeLayeredCompositionStore, FakeRenderer, FakeStorageClient, _manifest_from_candidate(), _overlapping_distinct_candidate_pair(), _pack_asset(), _probe_media() (+17 more)

### Community 80 - "content_lab_storage/assets.py"
Cohesion: 0.08
Nodes (34): BinaryIO, memoryview, _asset_filename(), canonical_asset_filename(), persist_asset_bytes(), persist_source_asset_bytes(), Helpers for persisting asset bytes to canonical object-storage locations., Upload user/source asset bytes to the canonical raw-asset location. (+26 more)

### Community 81 - "TimelineObject"
Cohesion: 0.13
Nodes (25): _bounds(), _is_inside_bounds(), _overlap_ratio(), Nudge supported objects toward their support footprint and relax overlap…, _repair_support_overlap_for_scene(), TimelineObject, _validate_scene_relationship_geometry(), _visual_priority() (+17 more)

### Community 82 - "findings.py"
Cohesion: 0.10
Nodes (40): AlignmentQAReport, Structured alignment QA for flows, APIs, and package traces., _alignment_field_path(), collect_structured_qa_findings(), _field_path_from_qa_result(), _finding_from_alignment(), _finding_from_qa_result(), _finding_from_semantic() (+32 more)

### Community 83 - "scripts/open-console.ps1"
Cohesion: 0.11
Nodes (29): Clear-ConsoleState(), Ensure-Command(), Ensure-DockerDaemon(), Get-ComposeContainerId(), Get-ConsolePort(), Get-ConsoleState(), Get-DockerDesktopExeWindows(), Get-PortListeners() (+21 more)

### Community 84 - "content_lab_storage/integrity.py"
Cohesion: 0.09
Nodes (21): _build_storage_client(), Session, sessionmaker, IntegrityTestStorageClient, Exception, StoredObject, test_storage_object_integrity_verifier_detects_checksum_mismatch(), test_storage_object_integrity_verifier_marks_missing_objects() (+13 more)

### Community 85 - "operator-page-workspace.ts"
Cohesion: 0.11
Nodes (31): PageOverviewRouteView(), PageReelsRouteView(), PageRunsRouteView(), DEFAULT_API_BASE_URL, apiRequestError(), asRecord(), buildApiHref(), buildPageWorkspaceReels() (+23 more)

### Community 86 - "provider.py"
Cohesion: 0.09
Nodes (29): ActorRegistration, _collect_registered_actors(), discover_actor_module_names(), ModuleType, Actor discovery and registration for the worker entrypoint., register_actor_modules(), ping(), actor (+21 more)

### Community 87 - "base.py"
Cohesion: 0.10
Nodes (25): get_phase1_video_provider(), _is_sensitive_key(), ProviderRetryPolicy, ProviderVideoDownloadResult, ProviderVideoPollResult, ProviderVideoSubmitRequest, ProviderVideoSubmitResult, Any (+17 more)

### Community 88 - "content_lab_qa/__init__.py"
Cohesion: 0.15
Nodes (23): Quality assurance gates and content validation., _as_float(), evaluate_media_sync_qa(), evaluate_timeline_timing_qa(), _exceeds_tolerance(), _findings_from_media_timeline_trace(), Any, BaseModel (+15 more)

### Community 89 - "repair_prompt.py"
Cohesion: 0.11
Nodes (27): ScenePlan, analyze_cinematic_plan_validation(), build_repair_prompt(), _contract_fix_hint(), _finding(), _findings_from_regulation(), PlannerValidationFinding, PlannerValidationReport (+19 more)

### Community 90 - "PromptPathEligibilityGate"
Cohesion: 0.10
Nodes (34): aggregate_prompt_path_capabilities(), AggregatedPromptPathCapabilities, AssetPromptPathCapabilityFlags, _bool_override(), _compat(), infer_asset_prompt_path_capabilities(), _norm(), PromptPathEligibilityGate (+26 more)

### Community 91 - "schemas/asset_packs.py"
Cohesion: 0.06
Nodes (43): _candidate_asset_out(), ApprovedAssetPackGenerateRequest, AssetLedIdeasRequest, AssetPackBatchRequest, AssetPackCombinationsOut, AssetPackCombinationsRequest, AssetPackCompositionSubmitOut, AssetPackCreate (+35 more)

### Community 92 - "PageWorkspace"
Cohesion: 0.09
Nodes (27): HomePage(), extraDownloadForTab(), formatOrgOption(), formatPolicySource(), hookImageStorageKey(), isAssetCompositionRun(), isCinematicPackageRun(), isGeneratedOutputRun() (+19 more)

### Community 93 - "runway.py"
Cohesion: 0.13
Nodes (30): _build_storage_client(), _content_type_for_extension(), _existing_external_ref(), _existing_summary(), finalize_runway_asset(), _finalize_success(), _handle_failed_task(), _persist_download() (+22 more)

### Community 94 - "validate_environment_quality"
Cohesion: 0.11
Nodes (20): EnvironmentQualitySeverity, downgrade_render_strategy_for_environment_quality(), Render strategy decisions for cinematic reel plans., Choose a safer render strategy when a filmed-scene base is unavailable., _can_use_as_sharp_full_frame(), environment_base_full_frame_eligible(), EnvironmentQualityFinding, EnvironmentQualityReport (+12 more)

### Community 95 - "alignment.py"
Cohesion: 0.14
Nodes (27): AlignmentFinding, AlignmentQAConstraints, _content_tokens(), _coverage(), evaluate_alignment_qa(), _first_hook_scene(), _hook_overlay_texts(), _hook_window_end_seconds() (+19 more)

### Community 96 - "E2EComposableAssetRegistryRunner"
Cohesion: 0.16
Nodes (11): ComposableAssetRegistryFailure, E2EComposableAssetRegistryRunner, main(), parse_args(), Any, AssetKind, Namespace, Path (+3 more)

### Community 97 - "runtime_db_snapshot.py"
Cohesion: 0.15
Nodes (16): Read-only runtime diagnostics helpers (no mutations)., build_runtime_db_snapshot(), _json_safe(), _package_hints(), Any, Session, Schema-aligned, read-only snapshot of operational Postgres rows. Column…, Return a JSON-serialisable dict of recent operational rows (read-only). (+8 more)

### Community 98 - "build_process_reel_runtime"
Cohesion: 0.08
Nodes (31): build_process_reel_runtime(), execute_asset_resolution(), execute_creative_planning(), execute_editing(), execute_packaging(), execute_qa(), _execution_from_payload(), _execution_to_payload() (+23 more)

### Community 99 - "policy-editor.tsx"
Cohesion: 0.11
Nodes (28): formatTimestamp(), PolicyEditor(), handleNumberChange(), handleSubmit(), resetSelectedDraft(), updateSelectedDraft(), PolicyEditorRecord, clonePolicyDocument() (+20 more)

### Community 100 - "relationship_layout.py"
Cohesion: 0.15
Nodes (23): Renderer preflight entrypoints for timeline composition., Renderer-oriented timeline projection for cinematic reel plans., ReelTimelineObject, _background_reveal_forbidden_region_hit(), _background_reveal_max_hero_overlap(), _background_reveal_region_problem(), _check_contact_shadow(), _check_hero_relationship() (+15 more)

### Community 101 - "content_lab_editing/__init__.py"
Cohesion: 0.12
Nodes (23): build_canonical_timeline(), CanonicalTimeline, _deterministic_audio_fades(), infer_edit_mode(), Any, BaseModel, model_validator, Canonical timeline contract for MED-001 timing authority. (+15 more)

### Community 102 - "CompositionLayer"
Cohesion: 0.11
Nodes (27): CompositionAnimation, CompositionCrop, CompositionExportPreset, CompositionLayer, MotionTransform, BaseModel, model_validator, Structured manifest for layered reel composition. (+19 more)

### Community 103 - "provider_jobs.py"
Cohesion: 0.15
Nodes (29): ProviderJob, _apply_provider_job_update(), _as_optional_uuid(), _as_uuid(), _build_metadata(), _error_message(), _external_ref_from_payload(), get_provider_job_by_external_ref() (+21 more)

### Community 104 - "S3StorageClient"
Cohesion: 0.19
Nodes (11): _clean_etag(), _coerce_int(), Any, datetime, Metadata returned by storage operations., Thin, S3-compatible wrapper used by API and worker services., Build a ref from a key plus either an explicit or default bucket., S3StorageClient (+3 more)

### Community 105 - "flows/__init__.py"
Cohesion: 0.12
Nodes (27): _build_parser(), _list_flows(), ArgumentParser, Namespace, _run_selected_flow(), Named Prefect flows exposed by the orchestrator package., build_outbox_drain_kwargs(), Namespace (+19 more)

### Community 106 - "generate_script_output"
Cohesion: 0.15
Nodes (29): BriefSceneContext, PhaseOneDirector, Deterministic planner for phase-1 persona- and policy-aware briefs., _brief_value(), compile_scene_plan(), Compile a deterministic scene plan from a brief and generated script., _segment_boundaries(), generate_script_output() (+21 more)

### Community 107 - "jobs.py"
Cohesion: 0.10
Nodes (26): Provider integrations for asset generation workflows., build_runway_poll_snapshot(), build_runway_result_snapshot(), build_runway_submission_snapshot(), is_runway_registry_external_ref(), _is_sensitive_key(), normalize_runway_job_status(), _optional_uuid_string() (+18 more)

### Community 108 - "content_lab_creative/types.py"
Cohesion: 0.06
Nodes (57): _build_scene(), _is_operations(), _narration_refs(), _nearest_beat(), _overlay_for_scene(), _overlay_role(), Deterministic scene-plan compilation for generated reel scripts., _shot_guidance() (+49 more)

### Community 109 - "overlay_layout.py"
Cohesion: 0.18
Nodes (16): build_overlay_render_manifest_for_qa(), compute_overlay_layout_payload(), default_overlay_safe_area(), _logical_rendered_text(), _max_line_width(), minimum_readable_font_size(), Any, Heuristic overlay layout / safe-area metrics for QA (phase-1 drawtext… (+8 more)

### Community 110 - "routes/packages.py"
Cohesion: 0.14
Nodes (29): _artifact_uri_by_name(), _coerce_mapping(), _extract_package_payload(), _get_org_or_404(), get_package(), _get_run_or_404(), _invalid_package_metadata(), _normalized_artifacts() (+21 more)

### Community 111 - "timeline_validation.py"
Cohesion: 0.07
Nodes (38): NamedTuple, _collect_sorted_overlay_items(), list_pre_handoff_overlay_slots(), OverlayTimelineSlot, OverlayTransitionSettings, OverlayTimeline, One overlay cue after timing normalization and fade merge, before primary-track…, Defaults for text overlay fades and handoff behavior. (+30 more)

### Community 112 - "validate_cinematic_plan_realism"
Cohesion: 0.11
Nodes (32): _check_depth(), _check_shadows(), _environment_quality_findings(), _finding(), _has_equal_priority_foreground_clutter(), _perspective_findings(), PlanRealismFinding, PlanRealismReport (+24 more)

### Community 113 - "plan_repair.py"
Cohesion: 0.16
Nodes (27): _caption_height(), _caption_hero_overlap_ratio(), _clamp(), _iter_dicts(), _move_caption_away_from_hero(), _object_bounds(), _payload_blur_sharpness(), _payload_visual_priority() (+19 more)

### Community 114 - "qa-failure-triage.ts"
Cohesion: 0.12
Nodes (22): FilterChip(), filterHref(), QaWorkbenchRow, QaFailureClassBadge(), QaFailureGatesSummary(), asRecord(), buildNextAction(), collectOperatorDebug() (+14 more)

### Community 115 - "planner_prompt.py"
Cohesion: 0.11
Nodes (27): default_narrative_arc(), narrative_arc_prompt_text(), NarrativeBeat, BaseModel, model_validator, Narrative guidance for cinematic reel planning prompts., Return deterministic narrative beat guidance for a short vertical reel., Format the default arc as prompt-readable guidance. (+19 more)

### Community 116 - "evaluate_semantic_script"
Cohesion: 0.20
Nodes (28): evaluate_semantic_script(), Input envelope for the semantic script QA gate. All fields are accepted as…, Evaluate semantic quality of a script/overlay/scene plan bundle. The returned…, SemanticScriptQARequest, _empty_hook_script(), semantic_reel_regression, Regression for the common 'nonsense reel' class: structurally presentable,…, _strong_viewer_script() (+20 more)

### Community 117 - "NoRegenRunner"
Cohesion: 0.15
Nodes (10): build_parser(), main(), NoRegenFailure, NoRegenRunner, Any, ArgumentParser, CompletedProcess, Namespace (+2 more)

### Community 118 - "asRecord"
Cohesion: 0.17
Nodes (29): asAssetLibraryItem(), asHookCanvasItem(), asRecord(), asSavedHookGeneration(), assetFromCoverRole(), assetImageUrl(), assetKindToLibraryKind(), assetPreviewTone() (+21 more)

### Community 119 - "test_editor_basic.py"
Cohesion: 0.16
Nodes (23): Protocol, Minimal object payload needed for local staging., RetrievedStorageObject, build_fixture_clip(), extract_png_bytes(), probe_media(), Path, Path (+15 more)

### Community 120 - "Any"
Cohesion: 0.16
Nodes (16): _asset_media_type(), _mapping(), _merge_dicts(), _optional_mapping(), _optional_text(), _package_artifact_uris(), _parse_uuid(), Any (+8 more)

### Community 121 - "content-lab-shared"
Cohesion: 0.08
Nodes (28): content-lab-assets, content-lab-assets, content-lab-auth, content-lab-auth, content-lab-core, content-lab-core, content-lab-creative, content-lab-creative (+20 more)

### Community 122 - "role_assignment.py"
Cohesion: 0.15
Nodes (25): cinematic_roles_for_asset(), CinematicAssetDescriptor, _dedupe(), _first_text(), _has_transparency(), _mapping(), _metadata_hints(), _normalize() (+17 more)

### Community 123 - "validate_reel_timeline_artifact"
Cohesion: 0.14
Nodes (18): BaseModel, model_validator, ReelTimeline, Any, Validation helpers for cinematic reel timeline artifacts., Validate a flattened reel timeline artifact before renderer handoff., ReelTimelineFinding, ReelTimelineValidationReport (+10 more)

### Community 124 - "expected_outcome"
Cohesion: 0.12
Nodes (23): Golden bad-reel bundles for semantic QA regression., expected_outcome(), list_case_ids(), list_semantic_script_regression_case_ids(), load_bad_reel_case(), load_expected_outcomes(), Any, Load deterministic bad-reel JSON fixtures and expected semantic outcomes. (+15 more)

### Community 125 - "settings.py"
Cohesion: 0.13
Nodes (9): _find_dotenv(), Walk up from this file to find the repo-root .env. Looks for common repo-root…, load_default_settings(), Env vars override defaults (pydantic-settings contract)., Secret-bearing fields must use SecretStr so they don't leak in repr/str., Declared field defaults (no repo .env); use _env_file=None so local .env cannot…, TestSecretStrFields, TestSettingsDefaults (+1 more)

### Community 126 - "Any"
Cohesion: 0.13
Nodes (6): Any, MonkeyPatch, RecordingAssetPackGenerationRuntime, RecordingAssetPackToReelsRuntime, test_asset_pack_to_reels_flow_creates_manifests_without_rendering(), test_generate_asset_pack_flow_orchestrates_reviewed_generation()

### Community 127 - "OutboxEntry"
Cohesion: 0.15
Nodes (14): _entry(), _FailingSink, _OkSink, datetime, MonkeyPatch, In-memory outbox store for dispatcher unit tests., _RecordingStore, test_dispatch_marks_failed_when_sink_raises() (+6 more)

### Community 128 - "AssetRecord"
Cohesion: 0.12
Nodes (17): AssetRecord, AssetRegistry, Protocol, Metadata record for a catalogued asset., Interface for asset catalogue operations., InMemoryPhase1Store, TypedDict, _resolve_request() (+9 more)

### Community 129 - "content_lab_assets/types.py"
Cohesion: 0.06
Nodes (46): AlphaMode, aspect_ratio_from_dimensions(), AssetPlacementOverlapMetadata, AssetPromptTrace, AssetRegion, AssetTransparencyMetadata, AssetVisualMetadata, detect_png_transparency() (+38 more)

### Community 130 - "enforce_relationship_layout"
Cohesion: 0.18
Nodes (26): CompositorPreflightReport, preflight_compositor_timeline(), Any, Validate renderer-side physical relationships before composition starts., enforce_relationship_layout(), Return render-blocking findings for physically invalid object relationships., _mask(), _Support (+18 more)

### Community 131 - "SQLAlchemyPhase1AssetRegistryStore"
Cohesion: 0.15
Nodes (12): Any, AssetKind, SQLAlchemy adapter for the shared phase-1 asset registry resolver., SQLAlchemyPhase1AssetRegistryStore, BaseModel, Canonical parameter history fields required by the shared resolver., Persisted staged-asset intent state returned by store adapters., Asset row fields required by the shared phase-1 resolver. (+4 more)

### Community 132 - "test_asset_registry_schema.py"
Cohesion: 0.14
Nodes (25): org_id(), fixture, Session, Schema-level checks for asset registry tables (requires migrated PostgreSQL)., test_asset_family_fk_on_asset(), test_asset_gen_params_cascade_when_asset_deleted(), test_asset_gen_params_ordered_history_per_asset(), test_asset_gen_params_unique_asset_seq() (+17 more)

### Community 133 - "Run"
Cohesion: 0.12
Nodes (38): OutboxEvent, Run, OrchestrationTriggerResult, OutboxOrchestrationBackend, Outcome returned by the orchestration adapter., Persist orchestration intent into the transactional outbox., package_client(), fixture (+30 more)

### Community 134 - "LayeredCompositionRequest"
Cohesion: 0.15
Nodes (8): _asset_key(), _asset_key_hash(), AssetUsageSpec, LayeredCompositionRequest, LayeredCompositionStore, Materialized run/task/reel state needed for one composition render., Asset lineage row to persist for a rendered composition., Persistence boundary consumed by the layered composition actor.

### Community 135 - "CinematicReelPlan"
Cohesion: 0.18
Nodes (21): CinematicReelPlan, _repair_model_light_references(), _repair_model_render_strategy_notes(), _repair_model_subject_footprints(), _require_contiguous(), _validate_light_references(), _validate_no_generation_instructions(), _motion() (+13 more)

### Community 136 - "build_asset_key"
Cohesion: 0.10
Nodes (41): build_asset_key(), build_audio_asset_key(), build_derived_asset_key(), build_final_render_asset_key(), _build_key_from_canonical_params(), build_overlay_text_asset_key(), Phase1ProviderLockError, Any (+33 more)

### Community 137 - "build_timeline_render_trace"
Cohesion: 0.40
Nodes (12): _as_float(), build_timeline_render_trace(), _check(), _copy_timing_rows(), _failure_codes(), _legacy_duration_mismatch_checks(), _master_audio_fades(), Any (+4 more)

### Community 138 - "Task"
Cohesion: 0.19
Nodes (24): Task, approve_asset_pack_step(), build_asset_pack_generation_runtime(), build_generate_asset_pack_kwargs(), create_asset_pack_plan_step(), create_asset_pack_step(), emit_asset_pack_generation_notification_step(), generate_asset_pack() (+16 more)

### Community 139 - "compose_layered_reel"
Cohesion: 0.16
Nodes (17): _build_harmonisation_params(), compose_and_store_layered_reel(), compose_layered_reel(), Path, Protocol, SourceAssetInput, Render a layered reel and persist the MP4 as a derived asset., Resolve manifest asset IDs to local files, downloading S3 objects when needed. (+9 more)

### Community 140 - "validate_perspective_compatibility"
Cohesion: 0.16
Nodes (19): _finding(), PerspectiveFinding, PerspectiveReport, Any, Perspective and surface-plane compatibility QA for cinematic plans., Validate view angle, support plane, scale, and lighting compatibility., _scene_light_direction(), _severe_view_mismatch() (+11 more)

### Community 141 - "content_lab_runs/__init__.py"
Cohesion: 0.20
Nodes (20): correlation_dict(), current_run_context(), merge_run_context(), Run/task correlation context shared across worker and orchestrator., Correlation identifiers for a unit of work (run, task, HTTP request, service)., Return a new context; non-None fields from ``overlay`` override ``self``., Merge two contexts; overlay wins for fields that are not None., Flatten to string key/values for structured logs or trace headers (omit unset… (+12 more)

### Community 142 - "ContentLabError"
Cohesion: 0.11
Nodes (13): BudgetExceededError, ConfigurationError, ContentLabError, ExternalServiceError, Exception, Base exception for all Content Lab services., A required configuration value is missing or invalid., The monthly spend budget has been exhausted. (+5 more)

### Community 143 - "seed_faceless_cooking_asset_pack.py"
Cohesion: 0.20
Nodes (23): attribution_text(), by_kind(), CommonsAssetSeed, compatibility_for_seed(), create_pack(), create_planned_spec(), download_assets(), download_with_retry() (+15 more)

### Community 144 - "validate_source_rights"
Cohesion: 0.21
Nodes (20): _asset_source_rights_finding(), _asset_value(), _extract_assets(), _finding(), _normalized(), _optional_bool(), Any, BaseModel (+12 more)

### Community 145 - "ts/package.json"
Cohesion: 0.09
Nodes (21): devDependencies, eslint, prettier, typescript, typescript-eslint, vitest, exports, eslint (+13 more)

### Community 146 - "seed_steakpagetest_reel_pack.py"
Cohesion: 0.21
Nodes (21): build_saved_generation(), commons_wiki_url(), compatibility_for_seed(), create_pack(), create_planned_spec(), download_with_retry(), ensure_org(), ensure_page() (+13 more)

### Community 147 - "RunwayHttpResponse"
Cohesion: 0.23
Nodes (14): Provider HTTP response wrapper used for transport injection., RunwayHttpResponse, Any, RecordingLogger, RecordingTransport, _submit_request(), test_download_retries_transient_errors_and_returns_bytes(), test_poll_raises_non_retryable_error_for_failed_task() (+6 more)

### Community 148 - "test_asset_persistence_service.py"
Cohesion: 0.26
Nodes (13): persisted_org(), Exception, fixture, MonkeyPatch, Session, StoredObject, RecordingStorageClient, _staged_asset() (+5 more)

### Community 149 - "content_lab_outbox/__init__.py"
Cohesion: 0.11
Nodes (32): build_flow_failure_event(), build_package_ready_event(), _compact_payload(), DeliveryStatus, _mapping(), _optional_text(), OutboxEventSpec, OutboxPublisher (+24 more)

### Community 150 - "S3StorageConfig"
Cohesion: 0.11
Nodes (21): Connection settings for an S3-compatible object store., S3StorageConfig, _canonical_uri(), datetime, Helpers for generating S3-compatible presigned download URLs., Configuration required to sign S3-compatible URLs., Generate SigV4 query-authenticated download URLs., S3Presigner (+13 more)

### Community 151 - "run_tasks.py"
Cohesion: 0.19
Nodes (17): apply_task_row_spec(), _as_optional_uuid(), _as_uuid(), create_run_row(), create_task_row(), ensure_task_row(), _error_message(), get_run_by_idempotency_key() (+9 more)

### Community 152 - "normalized_bounds"
Cohesion: 0.21
Nodes (8): normalized_bounds(), NormalizedBounds, NormalizedObject, overlap_ratio(), Protocol, Normalized bounds helpers for renderer timeline objects., Compute clamped normalized bounds from center coordinates and scale., Return overlap area as a ratio of the first object's area.

### Community 153 - "semantic_script.py"
Cohesion: 0.28
Nodes (19): _aggregate_verdict(), _evaluate_cta_balance(), _evaluate_hook(), _evaluate_meta_language(), _evaluate_overlay_usefulness(), _evaluate_scene_coherence(), _is_cta(), _is_disclosure() (+11 more)

### Community 154 - "RunRecord"
Cohesion: 0.15
Nodes (9): InvalidTransitionError, Exception, RunStatus, Pipeline run lifecycle model and state transition logic., Raised when a run status transition is not allowed., Represents a single pipeline run through its lifecycle., Move the run to *target* status, raising on illegal transitions., RunRecord (+1 more)

### Community 155 - "test_media_timeline.py"
Cohesion: 0.35
Nodes (12): _failure_codes(), Any, Path, test_12_second_plan_10_second_video_fails_validation(), test_audio_longer_than_video_fails_or_is_trimmed_and_logged(), test_audio_shorter_than_video_fails_or_is_padded_and_logged(), test_cover_timestamp_outside_duration_fails(), test_missing_audio_fails_timeline_validation() (+4 more)

### Community 156 - "test_assets_resolve_routes.py"
Cohesion: 0.26
Nodes (18): assets_client(), org_id(), Any, fixture, parametrize, Session, TestClient, _resolve_payload() (+10 more)

### Community 157 - "Q: has everything been mapped"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: has everything been mapped, Source Nodes

### Community 158 - "compilerOptions"
Cohesion: 0.11
Nodes (18): compilerOptions, allowJs, baseUrl, esModuleInterop, incremental, paths, plugins, exclude (+10 more)

### Community 159 - "EditInstruction"
Cohesion: 0.17
Nodes (12): EditInstruction, EditOperation, EditPlan, Enum, str, Edit instruction models for the video/image editing pipeline., Supported editing operations., A single editing instruction within a pipeline. (+4 more)

### Community 160 - "clear_correlation_id"
Cohesion: 0.17
Nodes (9): clear_correlation_id(), get_correlation_id(), Store a correlation ID for the current async/thread context., Return the current correlation ID (or *None*)., Reset the correlation ID for the current context., set_correlation_id(), Verify the structlog processor injects correlation_id into output., TestCorrelationId (+1 more)

### Community 161 - "configure_logging"
Cohesion: 0.14
Nodes (10): Application-wide constants (bootstrap IDs, etc.)., Any, fixture, _reset_logging_context(), test_logs_include_request_correlation_fields(), test_unhandled_error_response_and_logs_redact_secrets(), configure_logging(), Configure stdlib + structlog for consistent JSON logging across services.… (+2 more)

### Community 162 - "scripts"
Cohesion: 0.11
Nodes (17): engines, node, name, packageManager, private, scripts, console:open, console:open:docker (+9 more)

### Community 163 - "validate_phase1_creative_duration_alignment"
Cohesion: 0.22
Nodes (16): assert_rendered_media_matches_plan_duration(), _mapping_or_empty(), Any, Phase-1 duration consistency checks for creative planning and editing., Fail fast when the edited output length drifts from the planned timeline., Ensure brief, script, scene plan, posting variant, and asset request agree on…, _require_int(), validate_phase1_creative_duration_alignment() (+8 more)

### Community 164 - "test_cinematic_plan_routes.py"
Cohesion: 0.37
Nodes (16): cinematic_client(), _motion(), _plan(), _prompt_body(), fixture, Session, TestClient, _seed_pack() (+8 more)

### Community 165 - "operator-context.ts"
Cohesion: 0.22
Nodes (12): POST(), WorkspaceOrgSwitcher(), handleClear(), handleSave(), refreshWorkspace(), WorkspaceOrgSwitcherProps, describeOperatorContextSource(), normalizeOrgId() (+4 more)

### Community 166 - "build_overlap_validation_context"
Cohesion: 0.16
Nodes (16): build_cinematic_overlap_context(), Session, Resolve support-surface masks for cinematic plan validation., _storage_client(), FetchMaskBytes, _artifacts_for_uri(), build_overlap_validation_context(), collect_mask_uris_from_plan() (+8 more)

### Community 167 - "bootstrap-cloud-env.sh"
Cohesion: 0.28
Nodes (15): apt_has_package(), configure_default_node_shims(), configure_nested_docker(), DEBIAN_FRONTEND, ensure_base_packages(), ensure_node24_with_nvm(), ensure_poetry(), ensure_python311() (+7 more)

### Community 168 - "test_db_0008.py"
Cohesion: 0.17
Nodes (9): _integration_database_url(), _integration_engine_or_skip(), Engine, DB-007: migration revision metadata, ORM constraints, and optional live DB…, Prefer dedicated integration URL; otherwise use the same DB as the rest of the…, Return an engine to the integration DB, or skip if Postgres is unreachable…, test_migration_smoke_tables_exist_after_upgrade(), test_provider_job_external_ref_unique_per_provider() (+1 more)

### Community 169 - "test_metrics_audio_features_migration.py"
Cohesion: 0.21
Nodes (11): _alembic_config(), _default_database_url(), _load_migration_0006(), _postgres_ready(), Config, ModuleType, MonkeyPatch, Migration smoke and DB round-trips for intelligence-phase tables (DB-005). (+3 more)

### Community 170 - "Q: just to confirm has the whole repo been graphed and mapped"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: just to confirm has the whole repo been graphed and mapped, Source Nodes

### Community 171 - "build_provider_submission_task"
Cohesion: 0.16
Nodes (14): build_provider_submission_task(), get_provider_sweep_threshold(), is_terminal_provider_job_status(), ProviderSweepThreshold, Any, Build a durable task envelope for a provider submission/polling cycle., Sweep threshold attached to a provider-job status., Return whether a provider-job status should be excluded from sweeping. (+6 more)

### Community 172 - "durable.py"
Cohesion: 0.26
Nodes (11): _copy_mapping(), _copy_optional_mapping(), _normalize_optional_record_id(), _normalize_optional_text(), _normalize_record_id(), _normalize_required_text(), Reusable durable run/task row specs and idempotency helpers., Portable run-row values shared across API, worker, and orchestrator. (+3 more)

### Community 173 - "compilerOptions"
Cohesion: 0.13
Nodes (14): dom, dom.iterable, es2022, compilerOptions, isolatedModules, jsx, lib, module (+6 more)

### Community 174 - "ApprovedImportValidationError"
Cohesion: 0.20
Nodes (13): _download_approved_external_url(), ApprovedImportValidationError, assert_safe_http_url_for_fetch(), ValueError, Validated helpers for approved external asset import (no blind scraping)., Raised when operator import prerequisites are not met., Reject non-HTTP(S) schemes and obvious loopback/private literal hosts. Full…, Return (is_complete, warning_codes) for licence / usage documentation. (+5 more)

### Community 175 - "idempotency_key_from_payload"
Cohesion: 0.22
Nodes (12): canonical_json_bytes(), idempotency_key_from_payload(), JSONValue, Deterministic idempotency keys from canonical JSON payloads., Return UTF-8 bytes of a minified JSON document with stable key ordering., Derive a stable idempotency key from scope + payload. Equivalent payloads…, test_canonical_json_bytes_matches_key_body_shape(), test_idempotency_key_differs_for_payload() (+4 more)

### Community 176 - ".dispatch"
Cohesion: 0.25
Nodes (8): HTTP middleware for the Content Lab API., _actor_from_request(), _normalize_request_id(), Request, Response, Generate or propagate ``X-Request-Id`` and bind HTTP context for structured…, RequestContextMiddleware, BaseHTTPMiddleware

### Community 178 - "test_reels_routes.py"
Cohesion: 0.33
Nodes (12): _make_page(), fixture, Session, TestClient, reels_client(), seeded_reel_scope(), test_get_reel_detail_includes_operator_debug_from_process_reel_metadata(), test_reel_create_get_and_list_are_scoped_and_audited() (+4 more)

### Community 180 - "validate_package_provenance"
Cohesion: 0.32
Nodes (11): _asset_provenance_value(), _is_blank(), Any, Reusable provenance validation for ready-to-post reel packages., Validate the provenance payload needed for package auditability., validate_package_provenance(), _asset_lineage(), test_validate_package_provenance_fails_for_invalid_asset_entry() (+3 more)

### Community 181 - "build_task_idempotency_key"
Cohesion: 0.18
Nodes (11): build_task_idempotency_key(), IdempotentResult, JSONValue, Result of an idempotent create-or-fetch operation., Build a deterministic task idempotency key. ``payload`` produces a stable…, test_build_task_idempotency_key_is_stable_for_equivalent_payloads(), test_build_task_idempotency_key_requires_single_strategy(), test_build_task_idempotency_key_supports_readable_token_shape() (+3 more)

### Community 182 - "e2e_content_quality.py"
Cohesion: 0.31
Nodes (12): _assert_fail(), _assert_pass(), _build_phase_one_service(), _build_weak_semantic_fail_service(), _load_orchestrator_test_harness(), main(), Any, Path (+4 more)

### Community 183 - "task_status_for_run_status"
Cohesion: 0.20
Nodes (11): _task_spec_for_run_status(), RunStatus, Translate a run-level status into the closest task-level state., task_status_for_run_status(), StrEnum, Typed lifecycle statuses for pipeline runs and tasks., Fine-grained state for an individual task/step within a run., High-level state of a pipeline run (persisted run row / orchestration). (+3 more)

### Community 184 - "TaskRowSpec"
Cohesion: 0.35
Nodes (3): Any, Portable task-row values plus canonical task-state transitions., TaskRowSpec

### Community 185 - ".from_uri"
Cohesion: 0.25
Nodes (3): StoredObject, Parse an ``s3://bucket/key`` URI into a StorageRef., TestStorageRef

### Community 186 - "content_lab_core/types.py"
Cohesion: 0.12
Nodes (13): AssetKind, Enum, str, QAVerdict, Shared domain enumerations and type aliases used across Content Lab packages., Classification of media assets managed by the asset registry., Outcome of a quality-assurance gate check., Lifecycle states for a pipeline run. (+5 more)

### Community 187 - "test_composition_realism.py"
Cohesion: 0.53
Nodes (10): _codes(), _manifest(), _object_layer(), test_realism_report_fails_when_expected_transparency_is_missing(), test_realism_report_flags_bad_object_size_and_frame_bounds(), test_realism_report_flags_text_covering_object_and_safe_area_violation(), test_realism_report_passes_intentional_layered_composition(), test_realism_report_warns_on_static_cutout_style_and_edge_risks() (+2 more)

### Community 188 - "_download_package"
Cohesion: 0.25
Nodes (10): _download_package(), _ensure_pythonpath(), main(), Any, Path, End-to-end demo: seed DB rows, run the `process_reel` flow, download artifacts.…, Run the Prefect `process_reel` flow synchronously., Download every canonical package artifact from MinIO into ``output_dir``. (+2 more)

### Community 189 - "e2e_single_prompt_plan_smoke.py"
Cohesion: 0.44
Nodes (10): _fixture_input(), _load_planner_input(), main(), _mock_plan(), _motion(), Any, Path, _shadow() (+2 more)

### Community 190 - "unhandled_exception_handler"
Cohesion: 0.22
Nodes (10): Exception, Request, unhandled_exception_handler(), exception_handler, JSONResponse, ErrorDetail, ErrorResponse, BaseModel (+2 more)

### Community 191 - "test_reel_families_routes.py"
Cohesion: 0.36
Nodes (9): _make_page(), fixture, Session, TestClient, reel_families_client(), seeded_pages(), test_reel_families_create_list_get_are_page_scoped_and_include_variant_summaries(), test_reel_family_create_rejects_unknown_mode() (+1 more)

### Community 192 - "test_process_reel_bad_reel_regression.py"
Cohesion: 0.38
Nodes (9): _dummy_passing_format_report(), _dummy_passing_overlay(), _execution_for_bundle(), _load_bad_reel_case(), Any, MonkeyPatch, Semantic drift must remain visible without killing an otherwise usable package., test_process_reel_qa_passes_baseline_with_technical_format_patched() (+1 more)

### Community 193 - "CreativeBrief"
Cohesion: 0.29
Nodes (4): CreativeBrief, Creative brief model for reel content generation., A creative brief describing a single reel to produce., TestCreativeBrief

### Community 194 - "resolve_asset_request"
Cohesion: 0.33
Nodes (8): _actor_info(), _get_org_or_404(), AssetResolveDecision, Request, Session, Resolve an asset request through the shared phase-1 registry path., _record_generation_audit(), resolve_asset_request()

### Community 195 - "test_asset_import_approved.py"
Cohesion: 0.36
Nodes (9): assets_client(), _fake_persist_source(), org_id(), fixture, Session, TestClient, test_import_approved_external_persists_registry_asset(), test_import_rejects_blocked_url() (+1 more)

### Community 198 - "test_overlay_render_trace_qa.py"
Cohesion: 0.61
Nodes (8): _codes(), _package_with_overlay(), Any, test_overlay_clipping_fails_qa(), test_overlay_collision_fails_qa(), test_overlay_readability_too_fast_fails_qa(), test_overlay_text_mismatch_fails_qa(), _trace_row()

### Community 200 - "db_engine"
Cohesion: 0.36
Nodes (7): _database_url(), db_engine(), db_session(), Engine, fixture, Session, Shared fixtures (PostgreSQL schema tests).

### Community 201 - "test_cli_runs_selected_named_flow"
Cohesion: 0.43
Nodes (7): main(), MonkeyPatch, test_cli_lists_registered_flows(), test_cli_rejects_unknown_flow(), test_cli_runs_default_flow(), test_cli_runs_selected_named_flow(), CaptureFixture

### Community 202 - "stepOutput"
Cohesion: 0.16
Nodes (18): artifactByName(), artifactForTab(), availableArtifactTabs(), CinematicReelOutputPanel(), fallbackArtifactForTab(), formatDate(), generationMode(), LifecycleSteps() (+10 more)

### Community 204 - "logging.py"
Cohesion: 0.18
Nodes (12): _inject_correlation_id(), _is_sensitive_key(), Any, Redact common secret patterns embedded in free-form strings (e.g. exception…, Structlog processor that adds ``correlation_id`` when available., Structlog processor that replaces values of secret-bearing keys., Recursively redact secret-bearing values inside nested payloads., redact_event_dict() (+4 more)

### Community 206 - "page-create-panel.tsx"
Cohesion: 0.33
Nodes (6): DEFAULT_FORM, FeedbackState, normalizeOptional(), PageCreatePanel(), handleSubmit(), PageCreatePanelProps

### Community 208 - "ts/tsconfig.json"
Cohesion: 0.29
Nodes (6): exclude, extends, include, node_modules, ../../../tsconfig.base.json, src/**/*.ts

### Community 209 - "worktree-cleanup.sh"
Cohesion: 0.38
Nodes (5): branches, is_registered_worktree(), remove_worktree_path(), worktree-cleanup.sh script, tasks

### Community 210 - "worktree-spawn.sh"
Cohesion: 0.43
Nodes (6): action_create(), created, die(), worktree-spawn.sh script, slugify(), tasks

### Community 211 - "local-artifact/route.ts"
Cohesion: 0.40
Nodes (5): allowedRoot, contentTypes, GET(), parseRange(), runtime

### Community 212 - "manual_reel_demo.sh"
Cohesion: 0.53
Nodes (4): hdr(), pp(), manual_reel_demo.sh script, val()

### Community 214 - "e2e_mvp_smoke.sh"
Cohesion: 0.47
Nodes (4): run_infra(), run_migrate(), RUNWAY_API_MODE, e2e_mvp_smoke.sh script

### Community 215 - "py_check.sh script"
Cohesion: 0.60
Nodes (5): has_pytest_targets(), is_truthy(), run_api_health_smoke(), run_orchestrator_smoke(), py_check.sh script

### Community 216 - "worktree-cleanup.ps1"
Cohesion: 0.47
Nodes (3): Get-NormalizedFullPath(), Invoke-GitCaptured(), Test-PathIsRegisteredWorktree()

### Community 217 - "Production Architecture"
Cohesion: 0.40
Nodes (5): Repository Operating Guide, Comprehensive Platform Stack, Production Architecture, Project Charter, Content Laboratory

### Community 218 - "env.py"
Cohesion: 0.60
Nodes (4): _get_url(), Prefer DATABASE_URL env var over the hardcoded alembic.ini value. This lets…, run_migrations_offline(), run_migrations_online()

### Community 219 - "preflight_revision_check.py"
Cohesion: 0.50
Nodes (4): _api_root(), main(), Path, Emit one JSON line on stdout: DB alembic versions vs known script revisions.…

### Community 220 - "schemas/run.py"
Cohesion: 0.50
Nodes (4): BaseModel, Run request/response schemas., RunCreate, RunOut

### Community 221 - "pytest_configure"
Cohesion: 0.40
Nodes (4): Config, pytest_configure(), Orchestrator test session setup. Prefect's ephemeral API client uses…, Patch Prefect client lifespan timeouts before any tests import flows.

### Community 222 - "submitValidatedCinematicPreview"
Cohesion: 0.50
Nodes (5): buildCompositionManifest(), cinematicCompositionRolesFromPlan(), clientRequestId(), submitValidatedCinematicPreview(), localAssetForManifest()

### Community 224 - "Local Runtime Guide"
Cohesion: 0.40
Nodes (5): Composable Asset Registry, Local Runtime Guide, Runtime Database Inspection, Local Service Stack, PNPM Workspace Packages

### Community 225 - "editing/tests/test_latest_trace_golden_fixture.py"
Cohesion: 0.60
Nodes (4): _load_latest_trace_smoke_bundle(), Golden latest-trace fixture: caption + overlays used in editing/QA/creative…, test_latest_trace_overlays_round_trip_through_normalize(), test_latest_trace_scene_plan_duplicates_repeatable_move_overlay()

### Community 227 - "e2e_no_regen.sh"
Cohesion: 0.60
Nodes (3): run_infra(), run_migrate(), e2e_no_regen.sh script

### Community 229 - "scripts/stop-console.ps1"
Cohesion: 0.70
Nodes (4): Clear-ConsoleState(), Get-ConsoleState(), Stop-ProcessTree(), Stop-TrackedLocalWeb()

### Community 230 - "Continuous Integration"
Cohesion: 1.00
Nodes (3): Continuous Integration, End-to-End Content Quality, Regression Guardrails

### Community 231 - "Contribution Rules"
Cohesion: 0.50
Nodes (4): Pre-commit Quality Hooks, Contribution Rules, AI Agent Guardrails, Phase One Security Checklist

### Community 233 - "asset-packs/route.ts"
Cohesion: 0.83
Nodes (3): GET(), POST(), resolveApiBaseUrl()

### Community 235 - "pages/route.ts"
Cohesion: 0.83
Nodes (3): GET(), POST(), resolveApiBaseUrl()

### Community 236 - "page/[pageId]/route.ts"
Cohesion: 0.83
Nodes (3): GET(), PATCH(), resolveApiBaseUrl()

### Community 237 - "Process Reel Execution"
Cohesion: 0.50
Nodes (4): Process Reel Execution, Operations Caption Variants, Manual Reel Demo, Runtime Database Snapshot

### Community 238 - "Manual Reel Process"
Cohesion: 0.50
Nodes (4): Content Lab API Health Check, Manual Reel Process, Smoke-test Organization Provisioning, Owned Page Creation

### Community 239 - "Reel Package Manifest"
Cohesion: 0.50
Nodes (4): Caption Variants Artifact, Cover Image Artifact, Final Video Artifact, Reel Package Manifest

### Community 240 - "Reel Package Metadata"
Cohesion: 0.50
Nodes (4): Reel Package Metadata, Posting Plan, Package Provenance, Reel Package Download

### Community 258 - "asset_pack_to_reels.py"
Cohesion: 0.18
Nodes (21): asset_pack_to_reels(), build_asset_pack_to_reels_kwargs(), build_asset_pack_to_reels_runtime(), create_composition_manifests_step(), emit_asset_pack_to_reels_notification_step(), generate_candidate_combinations_step(), load_asset_pack_step(), mark_asset_pack_to_reels_failed_step() (+13 more)

### Community 260 - "build_process_reel_kwargs"
Cohesion: 0.67
Nodes (3): build_process_reel_kwargs(), Namespace, Map CLI arguments onto the flow signature.

### Community 288 - "process_layered_composition"
Cohesion: 0.17
Nodes (13): _build_storage_client(), _failure_payload(), process_layered_composition(), actor, RuntimeError, Render a persisted layered composition request., Raised when the actor persisted retry state and Dramatiq should retry later., Raised when a composition request is invalid or cannot become renderable by… (+5 more)

### Community 289 - "Ratatouille"
Cohesion: 0.67
Nodes (3): Ratatouille, Ratatouille Ingredient Poster, Vegetable Ingredients

### Community 290 - "Content Lab Smoke Test"
Cohesion: 0.67
Nodes (3): API Health Check, Content Lab Smoke Test, Smoke-test Organization Provisioning

### Community 291 - "Page Policy Configuration"
Cohesion: 0.67
Nodes (3): Budget and Quality Thresholds, Page Policy Configuration, Reel Family Creation

### Community 292 - "Reel Trigger Request"
Cohesion: 0.67
Nodes (3): API Submission, Outbox Orchestration, Reel Trigger Request

### Community 293 - "Golden Bad Reel Regression"
Cohesion: 0.67
Nodes (3): Semantic Reel Regression Lane, Shared Bad Reel Fixtures, Golden Bad Reel Regression

## Knowledge Gaps
- **321 isolated node(s):** `extends`, `next/core-web-vitals`, `baseDebug`, `TabId`, `CreativeReviewPanelProps` (+316 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **81 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `CompositionManifest` connect `CompositionManifest` to `process_layered_composition`, `content_lab_editing/__init__.py`, `CompositionLayer`, `flows/process_reel.py`, `harmonisation.py`, `test_layered_ffmpeg.py`, `editing.py`, `layered_ffmpeg.py`, `compose_layered_reel`, `test_editing_actor.py`, `composition_preflight.py`, `test_composition_realism.py`?**
  _High betweenness centrality (0.017) - this node is a cross-community bridge._
- **Why does `Settings` connect `Settings` to `SQLAlchemyPhase1AssetRegistryStore`, `flows/process_reel.py`, `seed_faceless_cooking_asset_pack.py`, `seed_steakpagetest_reel_pack.py`, `routes/assets.py`, `flows/storage_integrity_check.py`, `provider_job_sweeper.py`, `process_layered_composition`, `StoredRunwayGeneration`, `content_lab_outbox/store.py`, `build_overlap_validation_context`, `persist_asset_content`, `runway/__init__.py`, `DomainModel`, `outbox_dispatcher.py`, `_download_package`, `resolve_asset_request`, `build_phase_one_process_reel_executor`, `content_lab_storage/integrity.py`, `runway.py`, `routes/packages.py`, `Any`, `settings.py`?**
  _High betweenness centrality (0.016) - this node is a cross-community bridge._
- **Why does `TextOverlay` connect `TextOverlay` to `overlays.py`, `overlay_layout.py`, `timeline_validation.py`, `overlay.py`, `editor_basic.py`, `layout.py`?**
  _High betweenness centrality (0.012) - this node is a cross-community bridge._
- **Are the 60 inferred relationships involving `AssetKind` (e.g. with `_pack_asset()` and `build_asset_key()`) actually correct?**
  _`AssetKind` has 60 INFERRED edges - model-reasoned connections that need verification._
- **Are the 44 inferred relationships involving `TextOverlay` (e.g. with `BasicEditorArtifact` and `build_overlay_render_manifest_for_qa()`) actually correct?**
  _`TextOverlay` has 44 INFERRED edges - model-reasoned connections that need verification._
- **Are the 59 inferred relationships involving `CinematicReelPlan` (e.g. with `build_cinematic_overlap_context()` and `build_master_planning_prompt_document()`) actually correct?**
  _`CinematicReelPlan` has 59 INFERRED edges - model-reasoned connections that need verification._
- **Are the 53 inferred relationships involving `CompositionLayer` (e.g. with `_composition_manifest_from_cinematic_plan()` and `._resolve_composition_manifest_asset()`) actually correct?**
  _`CompositionLayer` has 53 INFERRED edges - model-reasoned connections that need verification._