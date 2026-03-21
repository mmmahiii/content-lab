from __future__ import annotations

from content_lab_editing.instructions import EditInstruction, EditOperation, EditPlan


class TestEditOperation:
    def test_members(self) -> None:
        assert EditOperation.TRIM == "trim"
        assert EditOperation.CONCAT == "concat"
        assert len(EditOperation) == 6


class TestEditInstruction:
    def test_creation(self) -> None:
        inst = EditInstruction(
            operation=EditOperation.TRIM,
            params={"start": 0, "end": 10},
            source_uri="s3://b/input.mp4",
        )
        assert inst.operation == EditOperation.TRIM
        assert inst.params["start"] == 0


class TestEditPlan:
    def test_empty_plan(self) -> None:
        plan = EditPlan(run_id="run-1")
        assert plan.step_count == 0

    def test_with_instructions(self) -> None:
        plan = EditPlan(
            run_id="run-2",
            instructions=[
                EditInstruction(operation=EditOperation.TRIM),
                EditInstruction(operation=EditOperation.RESIZE),
            ],
        )
        assert plan.step_count == 2
