from content_lab_runs import RunStatus, TaskStatus


def test_run_status_values_stable() -> None:
    assert RunStatus.PENDING == "pending"
    assert RunStatus.SUCCEEDED == "succeeded"


def test_task_status_includes_skipped() -> None:
    assert TaskStatus.SKIPPED == "skipped"
