from content_lab_worker.worker import ping


def test_ping() -> None:
    assert ping.fn() == "pong"
