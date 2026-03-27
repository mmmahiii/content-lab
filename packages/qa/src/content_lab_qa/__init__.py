"""Quality assurance gates and content validation."""

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

__all__ = [
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
    "evaluate_format_qa",
    "evaluate_package",
    "evaluate_repetition",
    "evaluate_reel_package_format",
    "validate_package_completeness",
    "validate_package_provenance",
]
