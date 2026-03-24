from __future__ import annotations

from content_lab_assets.providers.runway.jobs import (
    RunwayJobStatus,
    build_runway_job_external_ref,
    build_runway_result_snapshot,
    build_runway_submission_snapshot,
    normalize_runway_job_status,
    sanitize_provider_payload,
)


def test_build_runway_job_external_ref_is_stable_for_asset_key_hash() -> None:
    asset_key_hash = "ABCDEF1234567890ABCDEF1234567890ABCDEF1234567890ABCDEF1234567890"

    assert build_runway_job_external_ref(asset_key_hash=asset_key_hash) == (
        "runway-gen45:abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
    )


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
