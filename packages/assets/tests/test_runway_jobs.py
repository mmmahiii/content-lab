from __future__ import annotations

from content_lab_assets.providers import runway as runway_provider
from content_lab_assets.providers.runway.jobs import (
    RunwayJobStatus,
    build_runway_job_external_ref,
    build_runway_result_snapshot,
    build_runway_submission_snapshot,
    is_runway_registry_external_ref,
    normalize_runway_job_status,
    runway_provider_api_task_id_from_metadata,
    sanitize_provider_payload,
)


def test_build_runway_job_external_ref_is_stable_for_asset_key_hash() -> None:
    asset_key_hash = "ABCDEF1234567890ABCDEF1234567890ABCDEF1234567890ABCDEF1234567890"

    assert build_runway_job_external_ref(asset_key_hash=asset_key_hash) == (
        "runway-gen45:abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
    )


def test_is_runway_registry_external_ref_detects_stable_registry_key() -> None:
    ref = build_runway_job_external_ref(asset_key_hash="a" * 64)
    assert is_runway_registry_external_ref(ref) is True
    assert is_runway_registry_external_ref("b7c2f0a1-1234-5678-9abc-def012345678") is False


def test_runway_error_body_indicates_insufficient_credits() -> None:
    assert runway_provider._runway_error_body_indicates_insufficient_credits(
        '{"error":"You do not have enough credits to run this task."}'
    )
    assert not runway_provider._runway_error_body_indicates_insufficient_credits(
        '{"error":"Validation of body failed","issues":[]}'
    )


def test_build_submit_body_clamps_duration_to_runway_api_max() -> None:
    body = runway_provider._build_submit_body(
        task_payload={"request": {}},
        canonical_params={
            "model": "gen4.5",
            "prompt": "test",
            "duration_seconds": 15,
        },
    )
    assert body["duration"] == runway_provider.RUNWAY_GEN45_MAX_DURATION_SECONDS


def test_runway_provider_api_task_id_from_metadata_reads_submission_block() -> None:
    tid = "a00b1b44-3b3f-4831-a2ba-c4ca71e29999"
    assert runway_provider_api_task_id_from_metadata({"submission": {"task_id": tid}}) == tid
    assert runway_provider_api_task_id_from_metadata({"submission": {"task_id": "not-a-uuid"}}) is None


def test_sanitize_provider_payload_redacts_nested_secrets() -> None:
    payload = {
        "api_key": "super-secret",
        "headers": {
            "Authorization": "Bearer top-secret-token",
            "x-request-id": "req-123",
        },
        "nested": [
            {"access_token": "tok-123"},
            "api_key=still-secret",
        ],
    }

    sanitized = sanitize_provider_payload(payload)

    assert sanitized == {
        "api_key": "***REDACTED***",
        "headers": {
            "Authorization": "***REDACTED***",
            "x-request-id": "req-123",
        },
        "nested": [
            {"access_token": "***REDACTED***"},
            "***REDACTED***",
        ],
    }


def test_build_runway_submission_snapshot_keeps_links_and_redacts_request_payload() -> None:
    snapshot = build_runway_submission_snapshot(
        asset_id="asset-1",
        asset_key="asset-key-1",
        asset_key_hash="hash-1",
        task_id="task-1",
        task_status="queued",
        asset_status="staged",
        request_payload={
            "prompt": "hero shot",
            "metadata": {"api_token": "secret-token"},
        },
        provider_payload={
            "provider": "runway",
            "model": "gen4.5",
            "external_ref": "runway-gen45:hash-1",
        },
    )

    assert snapshot["status"] == "submitted"
    assert snapshot["asset_id"] == "asset-1"
    assert snapshot["task_id"] == "task-1"
    assert snapshot["request_payload"]["metadata"]["api_token"] == "***REDACTED***"
    assert snapshot["provider_payload"]["external_ref"] == "runway-gen45:hash-1"


def test_build_runway_result_snapshot_normalizes_terminal_status() -> None:
    snapshot = build_runway_result_snapshot(
        status="SUCCEEDED",
        payload={"status": "complete", "download_url": "https://example.test/file.mp4"},
    )

    assert snapshot["status"] == "succeeded"
    assert normalize_runway_job_status("FAILED") is RunwayJobStatus.FAILED
