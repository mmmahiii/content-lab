from prefect import flow, task


@task
def hello(name: str) -> str:
    return f"hello {name}"


@flow
def example_flow(name: str = "world") -> str:
    return hello(name)
