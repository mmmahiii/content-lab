from content_lab_orchestrator.flows import (
    DEFAULT_FLOW_NAME,
    example_flow,
    get_flow_definition,
    list_flow_names,
    process_reel,
)


def test_example_flow_alias_uses_default_phase1_flow() -> None:
    assert example_flow("ryan") == "hello ryan"


def test_flow_discovery_lists_phase1_flows() -> None:
    assert list_flow_names() == ("daily_reel_factory", "process_reel")


def test_default_flow_registration_points_at_daily_factory() -> None:
    assert get_flow_definition(DEFAULT_FLOW_NAME).entrypoint(name="ryan") == "hello ryan"


def test_process_reel_flow_supports_named_execution() -> None:
    assert process_reel(reel_id="reel-42", dry_run=True) == "dry-run processed reel reel-42"
