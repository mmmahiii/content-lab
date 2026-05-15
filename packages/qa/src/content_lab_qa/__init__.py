"""Quality assurance gates and content validation."""

from content_lab_qa.alignment import (
    AlignmentFinding,
    AlignmentQAConstraints,
    AlignmentQAReport,
    evaluate_alignment_qa,
)
from content_lab_qa.format import (
    FormatQAConstraints,
    FormatQAReport,
    evaluate_format_qa,
    evaluate_reel_package_format,
)
from content_lab_qa.gate import QAGate, QAResult, qa_result_blocks_readiness
from content_lab_qa.overlay import (
    OverlayTextFidelityFinding,
    OverlayTextFidelityReport,
    default_overlay_stack_policy_for_template,
    evaluate_overlay_text_fidelity_qa,
)
from content_lab_qa.package import (
    PackageQAResult,
    PackageQualityAssuranceError,
    evaluate_package,
    validate_layered_output_format,
    validate_package_completeness,
    validate_package_script_semantics,
)
from content_lab_qa.plan_realism import (
    PlanRealismFinding,
    PlanRealismReport,
    validate_cinematic_plan_realism,
)
from content_lab_qa.provenance import validate_package_provenance
from content_lab_qa.repetition import (
    RepetitionGate,
    RepetitionGateRequest,
    RepetitionHistory,
    RepetitionHistoryStore,
    RepetitionPolicy,
    RepetitionSignal,
    evaluate_repetition,
)
from content_lab_qa.semantic_script import (
    SEMANTIC_SCRIPT_GATE_NAME,
    SemanticScriptFinding,
    SemanticScriptQAReport,
    SemanticScriptQARequest,
    evaluate_semantic_script,
)
from content_lab_qa.source_rights import SourceRightsPolicy, validate_source_rights
from content_lab_qa.text import (
    USER_FACING_COPY_RULE_DEFS,
    CopyLintCategory,
    CopyLintMatch,
    CopyRuleDef,
    evaluate_user_facing_text,
    validate_caption_meta_language,
)
from content_lab_qa.timing import (
    MEDIA_SYNC_GATE_NAME,
    TIMELINE_TIMING_GATE_NAME,
    TimelineTimingConstraints,
    evaluate_media_sync_qa,
    evaluate_timeline_timing_qa,
)

__all__ = [
    "AlignmentFinding",
    "AlignmentQAConstraints",
    "AlignmentQAReport",
    "PackageQAResult",
    "PackageQualityAssuranceError",
    "PlanRealismFinding",
    "PlanRealismReport",
    "QAGate",
    "QAResult",
    "qa_result_blocks_readiness",
    "FormatQAConstraints",
    "FormatQAReport",
    "RepetitionGate",
    "RepetitionGateRequest",
    "RepetitionHistory",
    "RepetitionHistoryStore",
    "RepetitionPolicy",
    "RepetitionSignal",
    "SEMANTIC_SCRIPT_GATE_NAME",
    "USER_FACING_COPY_RULE_DEFS",
    "CopyLintCategory",
    "CopyLintMatch",
    "CopyRuleDef",
    "SemanticScriptFinding",
    "SemanticScriptQARequest",
    "SemanticScriptQAReport",
    "SourceRightsPolicy",
    "OverlayTextFidelityFinding",
    "OverlayTextFidelityReport",
    "TIMELINE_TIMING_GATE_NAME",
    "MEDIA_SYNC_GATE_NAME",
    "TimelineTimingConstraints",
    "default_overlay_stack_policy_for_template",
    "evaluate_alignment_qa",
    "evaluate_format_qa",
    "evaluate_overlay_text_fidelity_qa",
    "evaluate_package",
    "evaluate_repetition",
    "evaluate_reel_package_format",
    "evaluate_semantic_script",
    "validate_source_rights",
    "evaluate_media_sync_qa",
    "evaluate_timeline_timing_qa",
    "evaluate_user_facing_text",
    "validate_package_completeness",
    "validate_layered_output_format",
    "validate_package_script_semantics",
    "validate_package_provenance",
    "validate_caption_meta_language",
    "validate_cinematic_plan_realism",
]
