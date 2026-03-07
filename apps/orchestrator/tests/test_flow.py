from content_lab_orchestrator.flows import example_flow


def test_example_flow() -> None:
    assert example_flow("ryan") == "hello ryan"
