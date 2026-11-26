"""Cached, certificate-safe downloads for the seed scripts.

The seed scripts used to fetch every Wikimedia image on every run (throttled to ~2 min per
image, ~40 minutes per seed) into a new timestamped folder, and failed on Windows with
``CERTIFICATE_VERIFY_FAILED`` because Python there trusts an outdated system store.

* Files are cached under ``artifacts/seed-cache/`` (gitignored) by a stable name, written
  atomically, and validated before reuse, so re-runs make no network calls.
* TLS always verifies, against ``SSL_CERT_FILE`` / ``REQUESTS_CA_BUNDLE`` when set (corporate
  proxies) and otherwise against certifi's CA bundle.
"""

from __future__ import annotations

import json
import os
import ssl
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_ROOT = REPO_ROOT / "artifacts" / "seed-cache"
_RETRYABLE_HTTP = {429, 500, 502, 503, 504}

_ssl_context: ssl.SSLContext | None = None


def ca_bundle_path() -> str | None:
    """CA bundle to verify against: explicit env override, else certifi, else system store."""

    for name in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE"):
        value = os.environ.get(name, "").strip()
        if value and Path(value).is_file():
            return value
    try:
        import certifi
    except ImportError:  # pragma: no cover - certifi ships with the API env
        return None
    return certifi.where()


def ssl_context() -> ssl.SSLContext:
    global _ssl_context
    if _ssl_context is None:
        _ssl_context = ssl.create_default_context(cafile=ca_bundle_path())
    return _ssl_context


def fetch_bytes(
    url: str,
    *,
    user_agent: str,
    timeout: float = 180.0,
    attempts: int = 6,
    validate: Callable[[bytes], None] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> bytes:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": user_agent})
            with urllib.request.urlopen(
                request, timeout=timeout, context=ssl_context()
            ) as response:
                data = response.read()
            if validate is not None:
                validate(data)
            return data
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code not in _RETRYABLE_HTTP:
                raise
            retry_after = exc.headers.get("Retry-After") if exc.headers else None
            sleep(int(retry_after) if retry_after and retry_after.isdigit() else 5 * attempt)
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, ssl.SSLCertVerificationError):
                raise RuntimeError(
                    f"TLS verification failed for {url}: {exc.reason}. Set SSL_CERT_FILE to your "
                    "network's CA bundle (verification stays on)."
                ) from exc
            last_error = exc
            sleep(5 * attempt)
    raise RuntimeError(f"Unable to download after {attempts} attempts: {url}") from last_error


def cached_bytes(
    url: str,
    *,
    cache_path: Path,
    user_agent: str,
    validate: Callable[[bytes], None] | None = None,
    refresh: bool = False,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[bytes, bool]:
    """Return ``(data, from_cache)``; downloads only when the cache is missing or invalid."""

    if cache_path.is_file() and not refresh:
        data = cache_path.read_bytes()
        try:
            if validate is not None:
                validate(data)
            return data, True
        except Exception:  # noqa: BLE001 - a corrupt cache entry is simply re-downloaded
            pass
    data = fetch_bytes(url, user_agent=user_agent, validate=validate, sleep=sleep)
    _atomic_write(cache_path, data)
    return data, False


def cached_json(
    url: str,
    *,
    cache_path: Path,
    user_agent: str,
    refresh: bool = False,
) -> tuple[Any, bool]:
    data, from_cache = cached_bytes(
        url,
        cache_path=cache_path,
        user_agent=user_agent,
        validate=lambda raw: json.loads(raw.decode("utf-8")) and None,
        refresh=refresh,
    )
    return json.loads(data.decode("utf-8")), from_cache


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".part")
    partial.write_bytes(data)
    os.replace(partial, path)
