from __future__ import annotations

from uuid import UUID

from content_lab_runs import (
    RunContext,
    correlation_dict,
    current_run_context,
    merge_run_context,
    run_context_scope,
    with_actor,
    with_request_id,
    with_run_id,
    with_task_id,
)


def test_correlation_dict_omits_none_and_stringifies_uuid() -> None:
    rid = UUID("12345678-1234-5678-1234-567812345678")
    ctx = RunContext(run_id=rid, task_id="t1", request_id=None, actor="svc")
    assert correlation_dict(ctx) == {
        "run_id": "12345678-1234-5678-1234-567812345678",
        "task_id": "t1",
        "actor": "svc",
    }


def test_merge_and_with_helpers() -> None:
    base = RunContext(run_id="r1", actor="orchestrator")
    overlay = RunContext(task_id="step-2", request_id="req-9")
    merged = merge_run_context(base, overlay)
    assert merged == RunContext(run_id="r1", task_id="step-2", request_id="req-9", actor="orchestrator")

    assert with_run_id(base, "r2").run_id == "r2"
    assert with_task_id(base, "t").task_id == "t"
    assert with_request_id(base, "x").request_id == "x"
    assert with_actor(base, "w").actor == "w"


def test_run_context_merged_with() -> None:
    a = RunContext(actor="a", run_id="1")
    b = RunContext(task_id="t", actor=None)
    assert a.merged_with(b) == RunContext(actor="a", run_id="1", task_id="t")


def test_run_context_scope_propagation() -> None:
    assert current_run_context() is None
    outer = RunContext(actor="outer", run_id="r")
    inner = RunContext(task_id="inner-task")

    with run_context_scope(outer):
        assert current_run_context() == outer
        with run_context_scope(merge_run_context(outer, inner)):
            assert current_run_context() == RunContext(
                actor="outer", run_id="r", task_id="inner-task"
            )
        assert current_run_context() == outer
    assert current_run_context() is None
