"""Video/image editing pipeline and Runway adapter integration."""

from content_lab_editing.canonical_timeline import (
    CanonicalTimeline,
    TimelineAudioTrack,
    TimelineEditSegment,
    TimelineOverlay,
    TimelineScene,
    TimelineSourceClip,
    build_canonical_timeline,
)
from content_lab_editing.composition_manifest import (
    CompositionAnimation,
    CompositionCrop,
    CompositionExportPreset,
    CompositionLayer,
    CompositionManifest,
    LayerHarmonisationPass,
    MotionPreset,
    MotionTransform,
    SafeAreaConstraints,
)
from content_lab_editing.harmonisation import (
    HarmonisationParams,
    default_harmonisation_for_layer,
    effective_harmonisation,
)
from content_lab_editing.composition_preflight import (
    CompositionPreflightError,
    CompositionPreflightIssue,
    SourceAssetReference,
    ensure_composition_preflight,
    validate_composition_manifest,
    validate_source_asset_availability,
)
from content_lab_editing.composition_realism import (
    CompositionRealismFinding,
    CompositionRealismReport,
    validate_composition_realism,
)
from content_lab_editing.compositor import CompositorPreflightReport, preflight_compositor_timeline
from content_lab_editing.edit_plan import (
    SceneAwareEditPlan,
    SceneEditPlanSegment,
    build_scene_aware_edit_plan,
    build_single_clip_edit_plan,
)
from content_lab_editing.editor_basic import (
    BasicEditorArtifact,
    render_basic_vertical_edit,
)
from content_lab_editing.instructions import EditInstruction, EditOperation, EditPlan
from content_lab_editing.layered_ffmpeg import (
    LayeredCompositionResult,
    StoredLayeredCompositionResult,
    build_layered_ffmpeg_args,
    build_layered_filter_graph,
    compose_and_store_layered_reel,
    compose_layered_reel,
    stage_composition_assets,
)
from content_lab_editing.media_timeline import (
    build_timeline_render_trace,
    validate_media_timeline,
)
from content_lab_editing.motion_transforms import (
    MOTION_TRANSFORM_PRESETS,
    MotionPresetSpec,
    layer_has_motion,
    motion_preset_for_layer,
    motion_spec_for_layer,
)
from content_lab_editing.overlay_layout import (
    build_overlay_render_manifest_for_qa,
    default_overlay_safe_area,
)
from content_lab_editing.package_builder import (
    BuiltReelPackage,
    LocalReelPackage,
    build_package_directory,
    build_ready_to_post_package,
)
from content_lab_editing.reel_timeline_schema import ReelTimeline, ReelTimelineObject
from content_lab_editing.relationship_layout import (
    RelationshipLayoutFinding,
    RelationshipLayoutReport,
    enforce_relationship_layout,
    object_bounds,
)
from content_lab_editing.render_strategy import (
    DOWNGRADED_RENDER_STRATEGIES,
    REALISTIC_RENDER_STRATEGIES,
    downgrade_render_strategy_for_environment_quality,
)
from content_lab_editing.templates import (
    CALM_EXPLAINER_V1,
    DEFAULT_EDITORIAL_TEMPLATE,
    EDITORIAL_TEMPLATES,
    FAST_CUTS_V1,
    HOOK_FIRST_V1,
    HOOK_PLUS_PAYOFF_V1,
    EditorialTemplate,
    apply_editorial_template,
    apply_overlay_density_cap,
    get_editorial_template,
    select_and_apply_editorial_template,
    select_editorial_template,
)
from content_lab_editing.timeline_validator import (
    ReelTimelineFinding,
    ReelTimelineValidationReport,
    validate_reel_timeline_artifact,
)
from content_lab_editing.types import RenderedOverlayManifest, RenderedOverlayManifestEntry

__all__ = [
    "BasicEditorArtifact",
    "CanonicalTimeline",
    "CompositionAnimation",
    "CompositionCrop",
    "CompositionExportPreset",
    "CompositionLayer",
    "CompositionManifest",
    "CompositorPreflightReport",
    "CompositionPreflightError",
    "CompositionPreflightIssue",
    "CompositionRealismFinding",
    "CompositionRealismReport",
    "DOWNGRADED_RENDER_STRATEGIES",
    "BuiltReelPackage",
    "CALM_EXPLAINER_V1",
    "DEFAULT_EDITORIAL_TEMPLATE",
    "default_overlay_safe_area",
    "EDITORIAL_TEMPLATES",
    "EditInstruction",
    "EditOperation",
    "EditPlan",
    "EditorialTemplate",
    "FAST_CUTS_V1",
    "HOOK_FIRST_V1",
    "HOOK_PLUS_PAYOFF_V1",
    "HarmonisationParams",
    "LayerHarmonisationPass",
    "LayeredCompositionResult",
    "LocalReelPackage",
    "MOTION_TRANSFORM_PRESETS",
    "MotionPreset",
    "MotionPresetSpec",
    "MotionTransform",
    "RenderedOverlayManifest",
    "RenderedOverlayManifestEntry",
    "ReelTimeline",
    "ReelTimelineFinding",
    "ReelTimelineObject",
    "REALISTIC_RENDER_STRATEGIES",
    "ReelTimelineValidationReport",
    "RelationshipLayoutFinding",
    "RelationshipLayoutReport",
    "SafeAreaConstraints",
    "SceneAwareEditPlan",
    "SceneEditPlanSegment",
    "SourceAssetReference",
    "StoredLayeredCompositionResult",
    "TimelineAudioTrack",
    "TimelineEditSegment",
    "TimelineOverlay",
    "TimelineScene",
    "TimelineSourceClip",
    "apply_editorial_template",
    "apply_overlay_density_cap",
    "build_overlay_render_manifest_for_qa",
    "build_package_directory",
    "build_canonical_timeline",
    "build_layered_ffmpeg_args",
    "build_layered_filter_graph",
    "build_ready_to_post_package",
    "default_harmonisation_for_layer",
    "downgrade_render_strategy_for_environment_quality",
    "effective_harmonisation",
    "enforce_relationship_layout",
    "build_scene_aware_edit_plan",
    "build_single_clip_edit_plan",
    "build_timeline_render_trace",
    "compose_and_store_layered_reel",
    "compose_layered_reel",
    "ensure_composition_preflight",
    "get_editorial_template",
    "layer_has_motion",
    "motion_preset_for_layer",
    "motion_spec_for_layer",
    "object_bounds",
    "preflight_compositor_timeline",
    "render_basic_vertical_edit",
    "select_and_apply_editorial_template",
    "select_editorial_template",
    "stage_composition_assets",
    "validate_composition_realism",
    "validate_composition_manifest",
    "validate_media_timeline",
    "validate_reel_timeline_artifact",
    "validate_source_asset_availability",
]
