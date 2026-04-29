"""TEST-G004: caption meta-language blocked in semantic QA and package QA (no creative dependency)."""

from __future__ import annotations

from typing import Any

from content_lab_core.types import QAVerdict
from content_lab_qa import SemanticScriptQARequest, evaluate_package, evaluate_semantic_script
from content_lab_qa.package import validate_package_script_semantics

BAD_CAPTION_G004 = (
    "Create a explore reel for Smoke Test Page focused on operations for Busy founders."
)
GOOD_CAPTION_G004 = (
    "Founders batch vendor comms into one weekly block so approvals stay in one thread."
)


def _phase1_script(standard_caption: str) -> dict[str, Any]:
    hook = "Founders can tighten weekly operations without hiring another ops lead."
    return {
        "schema_version": "phase_1",
        "provider_name": "fixture",
        "generator_path": "fixture",
        "brief_title": "Operations",
        "duration_seconds": 12,
        "hook_text": hook,
        "spoken_script": [
            {
                "start_seconds": 0,
                "end_seconds": 6,
                "narration": "Block two hours for batching vendor email on Mondays.",
            },
            {
                "start_seconds": 6,
                "end_seconds": 12,
                "narration": "Reuse the checklist so approvals stop bouncing between Slack threads.",
            },
        ],
        "overlay_timeline": [
            {"start_seconds": 0, "end_seconds": 3, "text": "Batch vendor mail", "emphasis": "hook"},
            {"start_seconds": 3, "end_seconds": 9, "text": "Same checklist", "emphasis": "value"},
            {"start_seconds": 9, "end_seconds": 12, "text": "Try it Monday", "emphasis": "cta"},
        ],
        "caption_variants": [
            {"variant": "short", "text": "One ops habit that compounds."},
            {"variant": "standard", "text": standard_caption},
        ],
        "hashtags": ["#operations"],
    }


def test_g004_semantic_script_fails_on_exact_bad_standard_caption() -> None:
    report = evaluate_semantic_script(SemanticScriptQARequest(script=_phase1_script(BAD_CAPTION_G004)))
    assert report.verdict == QAVerdict.FAIL
    assert any(f.code == "internal_qa_copy" for f in report.findings)


def test_g004_package_script_semantics_fails_when_payload_embeds_bad_script() -> None:
    from tests.test_package import _valid_package_payload

    payload = _valid_package_payload()
    payload["script"] = _phase1_script(BAD_CAPTION_G004)
    gate = validate_package_script_semantics(payload)
    assert gate.gate_name == "package_script_semantics"
    assert gate.verdict == QAVerdict.FAIL

    agg = evaluate_package(payload)
    assert not agg.passed
    assert any(c.gate_name == "package_script_semantics" and not c.passed for c in agg.checks)


def test_g004_semantic_and_package_pass_viewer_ready_standard_caption() -> None:
    script = _phase1_script(GOOD_CAPTION_G004)
    semantic = evaluate_semantic_script(SemanticScriptQARequest(script=script))
    assert semantic.verdict in (QAVerdict.PASS, QAVerdict.WARN)

    from tests.test_package import _valid_package_payload

    payload = _valid_package_payload()
    payload["script"] = script
    assert validate_package_script_semantics(payload).verdict in (QAVerdict.PASS, QAVerdict.WARN)
    assert evaluate_package(payload).passed
