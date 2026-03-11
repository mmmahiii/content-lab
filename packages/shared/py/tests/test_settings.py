from content_lab_shared.settings import Settings


def test_defaults() -> None:
    s = Settings()
    assert s.redis_url == "redis://localhost:6379/0"
    assert s.minio_bucket == "content-lab"
