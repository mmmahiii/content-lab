from __future__ import annotations

from content_lab_api.services import (
    InMemoryProcessReelRepository,
    ProcessReelPersistenceService,
    StubProcessReelExecutor,
    build_process_reel_persistence_service,
)
from content_lab_runs import RunStatus, TaskStatus


def test_build_persistence_service_returns_process_reel_persistence() -> None:
    service = build_process_reel_persistence_service(executor=StubProcessReelExecutor())
    assert isinstance(service, ProcessReelPersistenceService)


def test_persistence_starts_inmemory_run_and_top_level_task() -> None:
    repository = InMemoryProcessReelRepository()
    repository.seed_reel(
        reel_id="reel-1",
        org_id="org-1",
        page_id="page-1",
        reel_family_id="fam-1",
    )
    service = ProcessReelPersistenceService(
        repository=repository,
        executor=StubProcessReelExecutor(),
    )
    execution = service.start_execution(reel_id="reel-1", dry_run=True)

    run = repository.runs[execution.run_id]
    assert run.status == RunStatus.RUNNING.value
    process_task = repository.tasks[(execution.run_id, "process_reel")]
    assert process_task.status == TaskStatus.RUNNING.value
