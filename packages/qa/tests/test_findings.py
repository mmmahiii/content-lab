"""Tests for structured QA finding aggregation."""

from __future__ import annotations

from content_lab_core.types import QAVerdict
from content_lab_qa.alignment import AlignmentQAReport
from content_lab_qa.findings import collect_structured_qa_findings
from content_lab_qa.format import FormatQAReport, ProbedMedia
from content_lab_qa.gate import QAResult
from content_lab_qa.repetition import RepetitionGateRequest, evaluate_repetition
from content_lab_qa.semantic_script import (
    SemanticScriptQARequest,
    SemanticScriptQAReport,
    evaluate_semantic_script,
)


def test_collect_structured_findings_tags_duration_mismatch() -> None:
    duration_fail = QAResult(
        gate_name="final_video_duration",
        verdict=QAVerdict.FAIL,
        message="duration bad",
        details={"path": "/v.mp4", "actual_duration_seconds": 99.0},
    )
    dim_pass = QAResult(
        gate_name="final_video_dimensions",
        verdict=QAVerdict.PASS,
        message="ok",
        details={},
    )
    fmt = FormatQAReport(
        verdict=QAVerdict.FAIL,
        message="fail",
        checks=(dim_pass, duration_fail),
        failure_reasons=("duration bad",),
        final_video=ProbedMedia(path="/v.mp4", exists=True, duration_seconds=99.0),
        cover=ProbedMedia(path="/c.png", exists=True),
    )
    repetition = evaluate_repetition(RepetitionGateRequest(candidate_key="k"))
    semantic = SemanticScriptQAReport(
        verdict=QAVerdict.PASS, message="ok", findings=[], failure_reasons=[]
    )
    alignment = AlignmentQAReport(verdict=QAVerdict.PASS, message="ok")

    rows = collect_structured_qa_findings(
        format_report=fmt,
        repetition_result=repetition,
        semantic_report=semantic,
        alignment_report=alignment,
    )
    duration_rows = [r for r in rows if r.finding_type == "duration_mismatch"]
    assert len(duration_rows) == 1
    assert duration_rows[0].passed is False
    assert duration_rows[0].field_path == "editing.final_video"


def test_collect_structured_findings_maps_caption_meta_language() -> None:
    fmt = FormatQAReport(
        verdict=QAVerdict.PASS,
        message="ok",
        checks=(
            QAResult(gate_name="final_video_dimensions", verdict=QAVerdict.PASS, message="", details={}),
        ),
        final_video=ProbedMedia(path="/v.mp4", exists=True),
        cover=ProbedMedia(path="/c.png", exists=True),
    )
    repetition = evaluate_repetition(RepetitionGateRequest(candidate_key="k"))
    semantic = evaluate_semantic_script(
        SemanticScriptQARequest(
            script={
                "caption_variants": [{"text": "Insert the hook here please"}],
                "hook_text": "A real hook line for the reel.",
                "spoken_script": [{"narration": "Enough words to avoid unrelated thin failures."}],
            }
        )
    )
    alignment = AlignmentQAReport(verdict=QAVerdict.PASS, message="ok")

    rows = collect_structured_qa_findings(
        format_report=fmt,
        repetition_result=repetition,
        semantic_report=semantic,
        alignment_report=alignment,
    )
    caption_meta = [r for r in rows if r.finding_type == "caption_meta_language"]
    assert caption_meta
    assert all("caption_variants" in r.field_path for r in caption_meta)


def test_collect_structured_findings_detects_overlay_text_mismatch() -> None:
    fmt = FormatQAReport(
        verdict=QAVerdict.PASS,
        message="ok",
        checks=(
            QAResult(gate_name="final_video_dimensions", verdict=QAVerdict.PASS, message="", details={}),
        ),
        final_video=ProbedMedia(path="/v.mp4", exists=True),
        cover=ProbedMedia(path="/c.png", exists=True),
    )
    repetition = evaluate_repetition(RepetitionGateRequest(candidate_key="k"))
    semantic = SemanticScriptQAReport(
        verdict=QAVerdict.PASS, message="ok", findings=[], failure_reasons=[]
    )
    alignment = AlignmentQAReport(verdict=QAVerdict.PASS, message="ok")

    rows = collect_structured_qa_findings(
        format_report=fmt,
        repetition_result=repetition,
        semantic_report=semantic,
        alignment_report=alignment,
        editing_output={
            "overlay_render_trace": {
                "normalized_overlays": [{"text": "Rendered copy", "start_seconds": 0.0, "end_seconds": 1.0}],
            }
        },
        creative_script={"overlay_timeline": [{"text": "Planned copy"}]},
    )
    mismatch = [r for r in rows if r.finding_type == "overlay_text_mismatch"]
    assert len(mismatch) == 1
    assert mismatch[0].passed is False


def test_collect_structured_findings_warns_on_long_overlay_text() -> None:
    long_text = "x" * 120
    fmt = FormatQAReport(
        verdict=QAVerdict.PASS,
        message="ok",
        checks=(
            QAResult(gate_name="final_video_dimensions", verdict=QAVerdict.PASS, message="", details={}),
        ),
        final_video=ProbedMedia(path="/v.mp4", exists=True),
        cover=ProbedMedia(path="/c.png", exists=True),
    )
    repetition = evaluate_repetition(RepetitionGateRequest(candidate_key="k"))
    semantic = SemanticScriptQAReport(
        verdict=QAVerdict.PASS, message="ok", findings=[], failure_reasons=[]
    )
    alignment = AlignmentQAReport(verdict=QAVerdict.PASS, message="ok")

    rows = collect_structured_qa_findings(
        format_report=fmt,
        repetition_result=repetition,
        semantic_report=semantic,
        alignment_report=alignment,
        editing_output={
            "overlay_render_trace": {
                "normalized_overlays": [
                    {"text": long_text, "start_seconds": 0.0, "end_seconds": 1.0},
                ],
            }
        },
    )
    clipped = [r for r in rows if r.finding_type == "overlay_text_clipped"]
    assert clipped
    assert clipped[0].severity == "warn"


def test_collect_structured_findings_detects_temporal_overlay_overlap() -> None:
    fmt = FormatQAReport(
        verdict=QAVerdict.PASS,
        message="ok",
        checks=(
            QAResult(gate_name="final_video_dimensions", verdict=QAVerdict.PASS, message="", details={}),
        ),
        final_video=ProbedMedia(path="/v.mp4", exists=True),
        cover=ProbedMedia(path="/c.png", exists=True),
    )
    repetition = evaluate_repetition(RepetitionGateRequest(candidate_key="k"))
    semantic = SemanticScriptQAReport(
        verdict=QAVerdict.PASS, message="ok", findings=[], failure_reasons=[]
    )
    alignment = AlignmentQAReport(verdict=QAVerdict.PASS, message="ok")

    rows = collect_structured_qa_findings(
        format_report=fmt,
        repetition_result=repetition,
        semantic_report=semantic,
        alignment_report=alignment,
        editing_output={
            "overlay_render_trace": {
                "normalized_overlays": [
                    {"text": "A", "start_seconds": 0.0, "end_seconds": 2.0},
                    {"text": "B", "start_seconds": 1.0, "end_seconds": 3.0},
                ],
            }
        },
    )
    overlap = [r for r in rows if r.finding_type == "overlay_overlap_detected"]
    assert overlap
    assert overlap[0].gate_name == "overlay_render"
