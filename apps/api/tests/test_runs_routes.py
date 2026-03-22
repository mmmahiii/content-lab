from __future__ import annotations

import uuid
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import insert
from sqlalchemy.orm import Session

from content_lab_api.deps import get_db
from content_lab_api.main import app
from content_lab_api.models import AuditLog, Org, Page, PageKind, Reel, ReelFamily, Run, Task
from content_lab_api.routes.runs import OrchestrationTriggerResult, get_orchestration_backend


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
    other_page = _make_page(
        org_two.id,
        platform="instagram",
        display_name="Other Page",
        external_page_id="ig-other-001",
    )
    db_session.add_all([primary_page, other_page])
    db_session.flush()

    primary_family = ReelFamily(
        org_id=org_one.id,
        page_id=primary_page.id,
        name="Primary family",
        metadata_={"mode": "explore"},
    )
    other_family = ReelFamily(
        org_id=org_two.id,
        page_id=other_page.id,
        name="Other family",
        metadata_={"mode": "exploit"},
    )
    db_session.add_all([primary_family, other_family])
    db_session.flush()

    primary_reel = Reel(
        org_id=org_one.id,
        reel_family_id=primary_family.id,
        variant_label="A",
        metadata_={},
    )
    other_reel = Reel(
        org_id=org_two.id,
        reel_family_id=other_family.id,
        variant_label="B",
        metadata_={},
    )
    db_session.add_all([primary_reel, other_reel])
    db_session.flush()

    return {
        "org_id": org_one.id,
        "other_org_id": org_two.id,
        "page_id": primary_page.id,
        "reel_id": primary_reel.id,
        "reel_family_id": primary_family.id,
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
