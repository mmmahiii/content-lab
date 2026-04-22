from __future__ import annotations

import importlib
import inspect

process_reel_module = importlib.import_module("content_lab_orchestrator.flows.process_reel")


def test_orchestrator_process_reel_exposes_prefect_flow() -> None:
    flow = process_reel_module.process_reel
    assert callable(flow)
    assert getattr(flow, "name", None) == "process_reel"


def test_build_process_reel_runtime_wires_api_persistence_builder() -> None:
    source = inspect.getsource(process_reel_module.build_process_reel_runtime)
    assert "build_process_reel_persistence_service" in source
