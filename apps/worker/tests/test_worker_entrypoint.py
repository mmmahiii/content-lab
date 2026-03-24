from content_lab_worker.actors import discover_actor_module_names
from content_lab_worker.actors._shared import build_queue_name
from content_lab_worker.worker import ACTOR_REGISTRATION, ping


def test_ping() -> None:
    assert ping.fn() == "pong"


def test_ping_queue_name_uses_integrity_namespace() -> None:
    assert ping.queue_name == build_queue_name("integrity")


def test_discover_actor_module_names_is_stable() -> None:
    assert discover_actor_module_names() == (
        "content_lab_worker.actors.editing",
        "content_lab_worker.actors.integrity",
        "content_lab_worker.actors.outbox",
        "content_lab_worker.actors.provider",
        "content_lab_worker.actors.registry",
        "content_lab_worker.actors.runway",
    )


def test_entrypoint_registers_all_actor_modules() -> None:
    assert ACTOR_REGISTRATION.module_names == discover_actor_module_names()
    assert ping in ACTOR_REGISTRATION.actors
    assert [module.__name__ for module in ACTOR_REGISTRATION.modules] == list(
        ACTOR_REGISTRATION.module_names
    )


def test_build_queue_name_normalizes_domains() -> None:
    assert build_queue_name("Outbox Jobs") == "content-lab-worker.outbox-jobs"
