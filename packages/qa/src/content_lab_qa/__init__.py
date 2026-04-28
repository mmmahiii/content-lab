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
from content_lab_qa.gate import QAGate, QAResult
from content_lab_qa.package import PackageQAResult, evaluate_package, validate_package_completeness
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
from content_lab_qa.timing import (
    TIMELINE_TIMING_GATE_NAME,
    TimelineTimingConstraints,
    evaluate_timeline_timing_qa,
)

__all__ = [
    "AlignmentFinding",
    "AlignmentQAConstraints",
    "AlignmentQAReport",
    "PackageQAResult",
    "QAGate",
    "QAResult",
    "FormatQAConstraints",
    "FormatQAReport",
    "RepetitionGate",
    "RepetitionGateRequest",
    "RepetitionHistory",
    "RepetitionHistoryStore",
    "RepetitionPolicy",
    "RepetitionSignal",
    "SEMANTIC_SCRIPT_GATE_NAME",
    "SemanticScriptFinding",
    "SemanticScriptQARequest",
    "SemanticScriptQAReport",
    "TIMELINE_TIMING_GATE_NAME",
    "TimelineTimingConstraints",
    "evaluate_alignment_qa",
    "evaluate_format_qa",
    "evaluate_package",
    "evaluate_repetition",
    "evaluate_reel_package_format",
    "evaluate_semantic_script",
    "evaluate_timeline_timing_qa",
    "validate_package_completeness",
    "validate_package_provenance",
]
