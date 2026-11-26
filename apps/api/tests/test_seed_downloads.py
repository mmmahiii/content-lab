"""scripts/seed_downloads.py: cached, certifi-verified downloads for the seed scripts."""

from __future__ import annotations

import io
import ssl
import sys
import urllib.error
from email.message import Message
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import seed_downloads  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"rest"


class _Response(io.BytesIO):
    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


def _png_only(data: bytes) -> None:
    if not data.startswith(b"\x89PNG"):
        raise RuntimeError("not a png")


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    recorded: list[dict[str, Any]] = []

    def _fake_urlopen(request: Any, *, timeout: float, context: ssl.SSLContext) -> _Response:
        recorded.append({"url": request.full_url, "context": context})
        return _Response(PNG)

    monkeypatch.setattr(seed_downloads.urllib.request, "urlopen", _fake_urlopen)
    return recorded


def test_second_run_is_served_from_the_cache(tmp_path: Path, calls: list[dict[str, Any]]) -> None:
    target = tmp_path / "cache" / "a.png"

    first, first_cached = seed_downloads.cached_bytes(
        "https://upload.example/a.png", cache_path=target, user_agent="t", validate=_png_only
    )
    second, second_cached = seed_downloads.cached_bytes(
        "https://upload.example/a.png", cache_path=target, user_agent="t", validate=_png_only
    )

    assert first == second == PNG
    assert (first_cached, second_cached) == (False, True)
    assert len(calls) == 1
    assert not target.with_name("a.png.part").exists()


def test_corrupt_cache_entries_are_downloaded_again(
    tmp_path: Path, calls: list[dict[str, Any]]
) -> None:
    target = tmp_path / "a.png"
    target.write_bytes(b"<html>rate limited</html>")

    data, from_cache = seed_downloads.cached_bytes(
        "https://upload.example/a.png", cache_path=target, user_agent="t", validate=_png_only
    )

    assert (data, from_cache) == (PNG, False)
    assert target.read_bytes() == PNG


def test_refresh_bypasses_the_cache(tmp_path: Path, calls: list[dict[str, Any]]) -> None:
    target = tmp_path / "a.png"
    target.write_bytes(PNG)

    seed_downloads.cached_bytes(
        "https://upload.example/a.png", cache_path=target, user_agent="t", refresh=True
    )

    assert len(calls) == 1


def test_tls_uses_certifi_unless_a_bundle_is_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import certifi

    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    monkeypatch.delenv("REQUESTS_CA_BUNDLE", raising=False)
    assert seed_downloads.ca_bundle_path() == certifi.where()

    bundle = tmp_path / "corp.pem"
    bundle.write_text("x")
    monkeypatch.setenv("SSL_CERT_FILE", str(bundle))
    assert seed_downloads.ca_bundle_path() == str(bundle)

    monkeypatch.setenv("SSL_CERT_FILE", str(tmp_path / "missing.pem"))
    assert seed_downloads.ca_bundle_path() == certifi.where()


def test_ssl_context_verifies_certificates() -> None:
    context = seed_downloads.ssl_context()

    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True


def test_throttling_is_retried_with_retry_after(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts: list[int] = []
    sleeps: list[float] = []

    def _flaky(request: Any, *, timeout: float, context: ssl.SSLContext) -> _Response:
        attempts.append(1)
        if len(attempts) < 3:
            headers = Message()
            headers["Retry-After"] = "2"
            raise urllib.error.HTTPError(request.full_url, 429, "Too Many", headers, None)
        return _Response(PNG)

    monkeypatch.setattr(seed_downloads.urllib.request, "urlopen", _flaky)

    data = seed_downloads.fetch_bytes(
        "https://upload.example/a.png", user_agent="t", sleep=sleeps.append
    )

    assert data == PNG
    assert sleeps == [2, 2]


def test_certificate_failures_fail_fast_with_a_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    def _bad_cert(request: Any, *, timeout: float, context: ssl.SSLContext) -> _Response:
        raise urllib.error.URLError(ssl.SSLCertVerificationError("certificate has expired"))

    monkeypatch.setattr(seed_downloads.urllib.request, "urlopen", _bad_cert)

    with pytest.raises(RuntimeError, match="SSL_CERT_FILE"):
        seed_downloads.fetch_bytes(
            "https://upload.example/a.png", user_agent="t", sleep=lambda _s: None
        )
