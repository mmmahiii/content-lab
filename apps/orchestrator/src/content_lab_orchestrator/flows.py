from prefect import flow, task

from content_lab_orchestrator.correlation import orchestrator_service_context


@task
def hello(name: str) -> str:
    return f"hello {name}"


@flow
def example_flow(name: str = "world") -> str:
    _ = orchestrator_service_context()
    return hello(name)
