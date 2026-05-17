from __future__ import annotations

import uuid
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import insert, text
from sqlalchemy.orm import Session

from content_lab_api.deps import get_db
from content_lab_api.main import app
from content_lab_api.models import (
    AuditLog,
    Org,
    OutboxEvent,
    Page,
    PageKind,
    Reel,
    ReelFamily,
    Run,
    Task,
)
from content_lab_api.routes import runs as runs_route
from content_lab_api.routes.runs import OrchestrationTriggerResult, get_orchestration_backend
from content_lab_outbox import PROCESS_REEL_PACKAGE_READY_EVENT


def _make_page(
    org_id: uuid.UUID, *, platform: str, display_name: str, external_page_id: str
) -> Page:
    return Page(
        org_id=org_id,
        platform=platform,
        display_name=display_name,
        external_page_id=external_page_id,
        kind=PageKind.OWNED.value,
        metadata_={},
    )


class RecordingOrchestrationBackend:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def trigger_flow(
        self,
        *,
        db: Session,
        run: Run,
        request: object,
    ) -> OrchestrationTriggerResult:
        self.calls.append(
            {
                "run_id": str(run.id),
                "org_id": str(run.org_id),
                "workflow_key": run.workflow_key,
                "flow_trigger": run.flow_trigger,
                "status": run.status,
                "input_params": dict(run.input_params or {}),
                "run_metadata": dict(run.run_metadata or {}),
                "request_id": getattr(getattr(request, "state", None), "request_id", None),
            }
        )
        return OrchestrationTriggerResult(
            external_ref="prefect-flow-run-123",
            status="queued",
            backend_name="mock",
            metadata={"submission_id": "sub-001"},
        )


@pytest.fixture
def orchestration_backend() -> RecordingOrchestrationBackend:
    return RecordingOrchestrationBackend()


@pytest.fixture
def runs_client(
    db_session: Session,
    orchestration_backend: RecordingOrchestrationBackend,
) -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_orchestration_backend] = lambda: orchestration_backend
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
def seeded_run_scope(db_session: Session) -> dict[str, uuid.UUID]:
    org_one = Org(name="Primary Org", slug=f"primary-{uuid.uuid4().hex[:8]}")
    org_two = Org(name="Secondary Org", slug=f"secondary-{uuid.uuid4().hex[:8]}")
    db_session.add_all([org_one, org_two])
    db_session.flush()

    primary_page = _make_page(
        org_one.id,
        platform="instagram",
        display_name="Primary Page",
        external_page_id="ig-primary-001",
    )
    sibling_page = _make_page(
        org_one.id,
        platform="instagram",
        display_name="Sibling Page",
        external_page_id="ig-primary-002",
    )
    other_page = _make_page(
        org_two.id,
        platform="instagram",
        display_name="Other Page",
        external_page_id="ig-other-001",
    )
    db_session.add_all([primary_page, sibling_page, other_page])
    db_session.flush()

    primary_family = ReelFamily(
        org_id=org_one.id,
        page_id=primary_page.id,
        name="Primary family",
        metadata_={"mode": "explore"},
    )
    sibling_family = ReelFamily(
        org_id=org_one.id,
        page_id=sibling_page.id,
        name="Sibling family",
        metadata_={"mode": "exploit"},
    )
    other_family = ReelFamily(
        org_id=org_two.id,
        page_id=other_page.id,
        name="Other family",
        metadata_={"mode": "exploit"},
    )
    db_session.add_all([primary_family, sibling_family, other_family])
    db_session.flush()

    primary_reel = Reel(
        org_id=org_one.id,
        reel_family_id=primary_family.id,
        variant_label="A",
        metadata_={},
    )
    sibling_reel = Reel(
        org_id=org_one.id,
        reel_family_id=sibling_family.id,
        variant_label="Sibling",
        metadata_={},
    )
    other_reel = Reel(
        org_id=org_two.id,
        reel_family_id=other_family.id,
        variant_label="B",
        metadata_={},
    )
    db_session.add_all([primary_reel, sibling_reel, other_reel])
    db_session.flush()

    return {
        "org_id": org_one.id,
        "other_org_id": org_two.id,
        "page_id": primary_page.id,
        "reel_id": primary_reel.id,
        "reel_family_id": primary_family.id,
        "sibling_page_id": sibling_page.id,
        "sibling_reel_id": sibling_reel.id,
        "other_page_id": other_page.id,
        "other_reel_id": other_reel.id,
    }


def test_create_run_triggers_workflow_and_persists_debug_metadata(
    runs_client: TestClient,
    db_session: Session,
    orchestration_backend: RecordingOrchestrationBackend,
    seeded_run_scope: dict[str, uuid.UUID],
) -> None:
    org_id = seeded_run_scope["org_id"]

    response = runs_client.post(
        f"/orgs/{org_id}/runs",
        json={
            "workflow_key": "daily_reel_factory",
            "input_params": {"page_limit": 3},
            "idempotency_key": "factory-batch-001",
            "metadata": {"operator_note": "morning batch"},
        },
        headers={
            "X-Actor-Id": "operator:test-user",
            "X-Request-Id": "run-create-001",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["org_id"] == str(org_id)
    assert payload["workflow_key"] == "daily_reel_factory"
    assert payload["flow_trigger"] == "manual"
    assert payload["status"] == "queued"
    assert payload["external_ref"] == "prefect-flow-run-123"
    assert payload["idempotency_key"] == "factory-batch-001"
    assert payload["input_params"] == {"page_limit": 3}
    assert payload["run_metadata"]["submitted_via"] == "api"
    assert payload["run_metadata"]["flow_trigger"] == "manual"
    assert payload["run_metadata"]["actor"] == {
        "id": "operator:test-user",
        "type": "request_header",
    }
    assert payload["run_metadata"]["request"] == {
        "request_id": "run-create-001",
        "method": "POST",
        "path": f"/orgs/{org_id}/runs",
    }
    assert payload["run_metadata"]["client"] == {"operator_note": "morning batch"}
    assert payload["run_metadata"]["orchestration"] == {
        "backend": "mock",
        "submission_id": "sub-001",
    }

    assert len(orchestration_backend.calls) == 1
    assert orchestration_backend.calls[0]["workflow_key"] == "daily_reel_factory"
    assert orchestration_backend.calls[0]["flow_trigger"] == "manual"
    assert orchestration_backend.calls[0]["request_id"] == "run-create-001"

    run_row = db_session.get(Run, uuid.UUID(payload["id"]))
    assert run_row is not None
    assert run_row.external_ref == "prefect-flow-run-123"
    assert run_row.status == "queued"

    audit_rows = (
        db_session.query(AuditLog)
        .filter(AuditLog.org_id == org_id, AuditLog.resource_id == payload["id"])
        .all()
    )
    assert [row.action for row in audit_rows] == ["run.created"]


def test_create_run_rejects_duplicate_idempotency_key(
    runs_client: TestClient,
    orchestration_backend: RecordingOrchestrationBackend,
    seeded_run_scope: dict[str, uuid.UUID],
) -> None:
    org_id = seeded_run_scope["org_id"]
    body = {
        "workflow_key": "daily_reel_factory",
        "input_params": {"page_limit": 2},
        "idempotency_key": "factory-batch-dup",
    }

    first = runs_client.post(f"/orgs/{org_id}/runs", json=body)
    second = runs_client.post(f"/orgs/{org_id}/runs", json=body)

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["detail"] == "A run with this idempotency_key already exists for the org"
    assert len(orchestration_backend.calls) == 1


def test_reel_trigger_launches_process_reel_and_creates_bootstrap_task(
    runs_client: TestClient,
    db_session: Session,
    orchestration_backend: RecordingOrchestrationBackend,
    seeded_run_scope: dict[str, uuid.UUID],
) -> None:
    org_id = seeded_run_scope["org_id"]
    page_id = seeded_run_scope["page_id"]
    reel_id = seeded_run_scope["reel_id"]
    reel_family_id = seeded_run_scope["reel_family_id"]

    response = runs_client.post(
        f"/orgs/{org_id}/pages/{page_id}/reels/{reel_id}/trigger",
        json={
            "input_params": {"priority": "high"},
            "metadata": {"source": "operator-console"},
        },
        headers={
            "X-Actor-Id": "operator:queue-manager",
            "X-Request-Id": "reel-trigger-001",
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["workflow_key"] == "process_reel"
    assert payload["flow_trigger"] == "reel_trigger"
    assert payload["status"] == "queued"
    assert payload["external_ref"] == "prefect-flow-run-123"
    assert payload["input_params"] == {
        "priority": "high",
        "org_id": str(org_id),
        "page_id": str(page_id),
        "reel_id": str(reel_id),
        "reel_family_id": str(reel_family_id),
    }
    assert payload["run_metadata"]["target"] == {
        "org_id": str(org_id),
        "page_id": str(page_id),
        "reel_id": str(reel_id),
        "reel_family_id": str(reel_family_id),
    }
    assert payload["run_metadata"]["client"] == {"source": "operator-console"}
    assert payload["run_metadata"]["orchestration"] == {
        "backend": "mock",
        "submission_id": "sub-001",
    }

    assert len(orchestration_backend.calls) == 1
    assert orchestration_backend.calls[0]["workflow_key"] == "process_reel"
    assert orchestration_backend.calls[0]["flow_trigger"] == "reel_trigger"
    assert orchestration_backend.calls[0]["input_params"] == {
        "priority": "high",
        "org_id": str(org_id),
        "page_id": str(page_id),
        "reel_id": str(reel_id),
        "reel_family_id": str(reel_family_id),
    }

    run_id = uuid.UUID(payload["id"])
    task_rows = db_session.query(Task).filter(Task.run_id == run_id).all()
    assert len(task_rows) == 1
    assert task_rows[0].task_type == "process_reel"
    assert task_rows[0].status == "queued"
    assert task_rows[0].payload == payload["input_params"]

    audit_rows = (
        db_session.query(AuditLog)
        .filter(AuditLog.org_id == org_id, AuditLog.resource_id == str(reel_id))
        .all()
    )
    assert [row.action for row in audit_rows] == ["reel.triggered"]


def test_run_detail_includes_operator_debug_for_process_reel_summary(
    runs_client: TestClient,
    db_session: Session,
    seeded_run_scope: dict[str, uuid.UUID],
) -> None:
    org_id = seeded_run_scope["org_id"]
    reel_id = str(seeded_run_scope["reel_id"])

    run = Run(
        org_id=org_id,
        workflow_key="process_reel",
        flow_trigger="reel_trigger",
        status="succeeded",
        input_params={"reel_id": reel_id},
        run_metadata={},
        output_payload={
            "step_outputs": {
                "creative_planning": {
                    "scene_plan": {
                        "title": "Operator debug",
                        "beats": [{"id": "beat-1"}],
                        "duration_seconds": 12,
                    },
                    "compiled_prompt": {
                        "trace": {"steps": [{"n": 1}], "summary": "short prompt trace"}
                    },
                },
                "qa": {
                    "passed": True,
                    "verdict": "pass",
                    "semantic_script": {
                        "verdict": "pass",
                        "findings": [{"code": "semantic_smoke", "outcome": "warn"}],
                    },
                    "format": {"verdict": "pass"},
                    "repetition": {"gate_name": "repetition", "passed": True},
                    "alignment": {"verdict": "pass"},
                    "checks": [],
                },
            },
            "package": {
                "creative_trace_uri": f"s3://content-lab/reels/packages/{reel_id}/creative_trace.json",
                "creative_trace": {
                    "schema_version": "phase_1",
                    "artifact_type": "creative_trace",
                    "reel_id": reel_id,
                    "run_id": "run-debug",
                    "generator_selection": {"provider_name": "test"},
                },
            },
        },
    )
    db_session.add(run)
    db_session.flush()
    db_session.expire_all()

    response = runs_client.get(f"/orgs/{org_id}/runs/{run.id}?expand_debug=true")
    assert response.status_code == 200
    payload = response.json()
    debug = payload.get("operator_debug")
    assert debug is not None
    assert debug["qa"]["semantic_script"]["findings"][0]["code"] == "semantic_smoke"
    assert debug["scene_plan"] is not None
    assert debug["prompt_trace"] is not None
    assert debug["creative_trace"]["body"] is not None


def test_run_detail_includes_task_summaries(
    runs_client: TestClient,
    db_session: Session,
    seeded_run_scope: dict[str, uuid.UUID],
) -> None:
    org_id = seeded_run_scope["org_id"]

    run = Run(
        org_id=org_id,
        workflow_key="daily_reel_factory",
        flow_trigger="manual",
        status="running",
        input_params={"page_limit": 2},
        run_metadata={"submitted_via": "api"},
        external_ref="prefect-flow-run-789",
    )
    db_session.add(run)
    db_session.flush()

    db_session.execute(
        insert(Task),
        [
            {
                "id": uuid.uuid4(),
                "org_id": org_id,
                "task_type": "plan_reels",
                "idempotency_key": "task-plan-001",
                "status": "succeeded",
                "run_id": run.id,
                "payload": {"family_count": 2},
                "result": {"planned": 2},
            },
            {
                "id": uuid.uuid4(),
                "org_id": org_id,
                "task_type": "qa_review",
                "idempotency_key": "task-qa-001",
                "status": "running",
                "run_id": run.id,
                "payload": {"reel_count": 2},
                "result": None,
            },
        ],
    )
    db_session.flush()
    db_session.expire_all()

    response = runs_client.get(f"/orgs/{org_id}/runs/{run.id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == str(run.id)
    assert payload["status"] == "running"
    assert payload["external_ref"] == "prefect-flow-run-789"
    assert payload["task_status_counts"] == {"running": 1, "succeeded": 1}

    tasks_by_type = {task["task_type"]: task for task in payload["tasks"]}
    assert set(tasks_by_type) == {"plan_reels", "qa_review"}
    assert tasks_by_type["plan_reels"]["status"] == "succeeded"
    assert tasks_by_type["plan_reels"]["result"] == {"planned": 2}
    assert tasks_by_type["qa_review"]["status"] == "running"
    assert tasks_by_type["qa_review"]["result"] is None
    assert payload["outbox"]["pending_count"] == 0
    assert payload["outbox"]["summary"] is None


def test_run_detail_includes_outbox_counts_for_run_aggregate(
    runs_client: TestClient,
    db_session: Session,
    seeded_run_scope: dict[str, uuid.UUID],
) -> None:
    org_id = seeded_run_scope["org_id"]

    run = Run(
        org_id=org_id,
        workflow_key="process_reel",
        flow_trigger="reel_trigger",
        status="succeeded",
        input_params={},
        run_metadata={},
        external_ref="prefect-123",
    )
    db_session.add(run)
    db_session.flush()

    db_session.add(
        OutboxEvent(
            org_id=org_id,
            aggregate_type="run",
            aggregate_id=str(run.id),
            event_type=PROCESS_REEL_PACKAGE_READY_EVENT,
            payload={"reel_id": "reel-1"},
            delivery_status="pending",
            attempt_count=0,
        )
    )
    db_session.add(
        OutboxEvent(
            org_id=org_id,
            aggregate_type="run",
            aggregate_id=str(run.id),
            event_type="orchestration.flow.requested",
            payload={},
            delivery_status="sent",
            attempt_count=1,
        )
    )
    db_session.flush()
    db_session.expire_all()

    response = runs_client.get(f"/orgs/{org_id}/runs/{run.id}")
    assert response.status_code == 200
    payload = response.json()
    ob = payload["outbox"]
    assert ob["pending_count"] == 1
    assert ob["sent_count"] == 1
    assert ob["failed_count"] == 0
    assert ob["has_backlog"] is True
    assert ob["summary"] is not None
    assert "pending dispatch" in (ob["summary"] or "")


def test_update_run_hook_cover_persists_editor_state(
    runs_client: TestClient,
    db_session: Session,
    seeded_run_scope: dict[str, uuid.UUID],
) -> None:
    org_id = seeded_run_scope["org_id"]
    page_id = seeded_run_scope["page_id"]
    run = Run(
        org_id=org_id,
        workflow_key="process_reel",
        flow_trigger="manual",
        status="succeeded",
        input_params={
            "page_id": str(page_id),
            "workflow_stage": "asset_composition_render",
        },
        output_payload={"hook_cover": {"title": "Original hook"}},
        run_metadata={"target": {"page_id": str(page_id)}},
    )
    db_session.add(run)
    db_session.flush()
    task = Task(
        org_id=org_id,
        task_type="process_reel",
        idempotency_key=f"task:{run.id}",
        status="succeeded",
        run_id=run.id,
        payload={},
        result=dict(run.output_payload or {}),
    )
    db_session.add(task)
    db_session.commit()

    response = runs_client.patch(
        f"/orgs/{org_id}/runs/{run.id}/hook-cover",
        json={
            "title": "Edited hook",
            "editor_state": {
                "selected_background_id": "bg-01",
                "items": [{"id": "copy-1"}],
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["output_payload"]["hook_cover"]["title"] == "Edited hook"
    assert payload["output_payload"]["hook_cover"]["editor_state"]["items"] == [{"id": "copy-1"}]
    db_session.refresh(task)
    assert task.result["hook_cover"]["title"] == "Edited hook"


def test_generate_package_from_cinematic_plan_run_merges_plan_and_package_steps(
    runs_client: TestClient,
    db_session: Session,
    seeded_run_scope: dict[str, uuid.UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    org_id = seeded_run_scope["org_id"]
    page_id = seeded_run_scope["page_id"]
    plan_run = Run(
        org_id=org_id,
        workflow_key="process_reel",
        flow_trigger="manual",
        status="succeeded",
        input_params={
            "page_id": str(page_id),
            "workflow_stage": "asset_composition_render",
        },
        run_metadata={"client": {"workflow_stage": "asset_composition_render"}},
        output_payload={
            "output_type": "cinematic_reel_plan",
            "package": {
                "composition_manifest": {
                    "schema_version": "cinematic_reel_plan_manifest.v1",
                    "roles": {
                        "background": {
                            "asset_id": "tomato-bg",
                            "asset_kind": "background",
                            "metadata": {
                                "storage_uri": "s3://content-lab/assets/tomato-bg.png",
                                "media_type": "image/png",
                            },
                        }
                    },
                },
                "cinematic_plan": {
                    "plan_id": "cinematic-1",
                    "content_goal": "Make ratatouille prep feel vivid and practical.",
                    "total_duration_seconds": 7.0,
                    "narrative_arc": {
                        "hook": "Tomato slices pull the eye into the prep.",
                        "development": "Eggplant and pepper build a layered colour stack.",
                        "reveal_payoff": "Basil finishes the bowl.",
                    },
                    "scenes": [
                        {
                            "scene_id": "hook",
                            "start_time": 0,
                            "end_time": 3,
                            "purpose": "Open on tomato texture.",
                            "captions": [{"text": "Tomato texture starts the stack"}],
                        },
                        {
                            "scene_id": "payoff",
                            "start_time": 3,
                            "end_time": 7,
                            "purpose": "Finish on basil garnish.",
                            "captions": [{"text": "Basil makes it ready"}],
                        },
                    ],
                },
                "cinematic_artifacts": {
                    "reel_timeline.json": {
                        "total_duration_seconds": 7.0,
                    }
                },
            },
        },
    )
    db_session.add(plan_run)
    db_session.flush()
    monkeypatch.setattr(
        runs_route,
        "_launch_process_reel_flow",
        lambda **_: {"pid": 12345, "mode": "test"},
    )

    response = runs_client.post(
        f"/orgs/{org_id}/pages/{page_id}/cinematic-plans/{plan_run.id}/generate-package",
        json={"generation_mode": "smoke_test"},
    )

    assert response.status_code == 201
    payload = response.json()
    package_run = db_session.get(Run, uuid.UUID(payload["id"]))
    db_session.refresh(plan_run)
    assert package_run is not None
    assert package_run.input_params["workflow_stage"] == "package_generation"
    assert package_run.input_params["source_plan_stage"] == "cinematic_plan_package"
    assert package_run.input_params["generation_mode"] == "smoke_test"
    assert package_run.input_params["dry_run"] is False
    reel = db_session.get(Reel, uuid.UUID(package_run.input_params["reel_id"]))
    assert reel.metadata_["duration_seconds"] == 10
    assert reel.metadata_["idea_plan"]["hook"] == "Tomato texture starts the stack"
    assert reel.metadata_["idea_plan"]["beats"][1]["text"] == "Basil makes it ready"
    assert reel.metadata_["idea_plan"]["composition_manifest"]["roles"]["background"]["asset_id"] == "tomato-bg"
    assert plan_run.output_payload["used_in_package_run_id"] == str(package_run.id)
    assert package_run.external_ref == "local-process:12345"


def test_list_page_runs_returns_only_matching_page_runs_in_newest_first_order(
    runs_client: TestClient,
    db_session: Session,
    seeded_run_scope: dict[str, uuid.UUID],
) -> None:
    org_id = seeded_run_scope["org_id"]
    page_id = seeded_run_scope["page_id"]
    sibling_page_id = seeded_run_scope["sibling_page_id"]
    other_org_id = seeded_run_scope["other_org_id"]
    other_page_id = seeded_run_scope["other_page_id"]

    matching_input_run = Run(
        org_id=org_id,
        workflow_key="daily_reel_factory",
        flow_trigger="manual",
        status="running",
        input_params={"page_id": str(page_id)},
        run_metadata={"submitted_via": "api"},
        external_ref="page-input-run",
    )
    matching_target_run = Run(
        org_id=org_id,
        workflow_key="process_reel",
        flow_trigger="reel_trigger",
        status="queued",
        input_params={},
        run_metadata={"target": {"page_id": str(page_id)}},
        external_ref="page-target-run",
    )
    sibling_page_run = Run(
        org_id=org_id,
        workflow_key="daily_reel_factory",
        flow_trigger="manual",
        status="queued",
        input_params={"page_id": str(sibling_page_id)},
        run_metadata={"submitted_via": "api"},
        external_ref="sibling-page-run",
    )
    other_org_run = Run(
        org_id=other_org_id,
        workflow_key="daily_reel_factory",
        flow_trigger="manual",
        status="queued",
        input_params={"page_id": str(other_page_id)},
        run_metadata={"submitted_via": "api"},
        external_ref="other-org-run",
    )
    db_session.add_all([matching_input_run, matching_target_run, sibling_page_run, other_org_run])
    db_session.flush()

    matching_input_run.updated_at = matching_input_run.created_at
    matching_target_run.updated_at = matching_target_run.created_at.replace(second=59)
    sibling_page_run.updated_at = sibling_page_run.created_at.replace(second=10)
    other_org_run.updated_at = other_org_run.created_at.replace(second=20)
    db_session.flush()
    db_session.expire_all()

    response = runs_client.get(f"/orgs/{org_id}/pages/{page_id}/runs")

    assert response.status_code == 200
    payload = response.json()
    assert [item["id"] for item in payload] == [
        str(matching_target_run.id),
        str(matching_input_run.id),
    ]
    assert all(item["org_id"] == str(org_id) for item in payload)
    assert {item["external_ref"] for item in payload} == {
        "page-input-run",
        "page-target-run",
    }


def test_list_page_runs_tolerates_scalar_input_params_jsonb(
    runs_client: TestClient,
    db_session: Session,
    seeded_run_scope: dict[str, uuid.UUID],
) -> None:
    """A non-object input_params JSON value must not 500 the page runs query."""
    org_id = seeded_run_scope["org_id"]
    page_id = seeded_run_scope["page_id"]

    poison = Run(
        org_id=org_id,
        workflow_key="daily_reel_factory",
        flow_trigger="manual",
        status="queued",
        input_params={},
        run_metadata={},
        external_ref="scalar-json-poison",
    )
    db_session.add(poison)
    db_session.flush()
    db_session.execute(
        text("UPDATE runs SET input_params = '42'::jsonb WHERE id = :rid"),
        {"rid": str(poison.id)},
    )
    db_session.commit()
    db_session.expire_all()

    response = runs_client.get(f"/orgs/{org_id}/pages/{page_id}/runs")
    assert response.status_code == 200
    payload = response.json()
    assert "scalar-json-poison" not in {item.get("external_ref") for item in payload}
