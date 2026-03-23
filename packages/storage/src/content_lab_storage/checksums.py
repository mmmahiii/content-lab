"""Checksum helpers for object persistence and storage integrity checks."""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

_SHA256_PREFIX = "sha256:"
_DEFAULT_CHUNK_SIZE = 1024 * 1024
_HEX_DIGITS = frozenset("0123456789abcdef")


@dataclass(frozen=True, slots=True)
class ObjectChecksums:
    """Common checksum encodings for a storage object payload."""

    sha256_hex: str
    md5_hex: str
    md5_base64: str

    @property
    def content_hash(self) -> str:
        return f"{_SHA256_PREFIX}{self.sha256_hex}"

    def as_metadata(self) -> dict[str, str]:
        return {"checksum-sha256": self.content_hash}


def normalize_sha256(value: str) -> str:
    """Normalize a SHA-256 digest into the repo's ``sha256:<hex>`` format."""

    normalized = value.strip().lower()
    if normalized.startswith(_SHA256_PREFIX):
        normalized = normalized[len(_SHA256_PREFIX) :]
    if len(normalized) != 64 or any(char not in _HEX_DIGITS for char in normalized):
        raise ValueError("checksum must be a 64-character SHA-256 hex digest")
    return f"{_SHA256_PREFIX}{normalized}"


def checksum_bytes(data: bytes | bytearray | memoryview) -> ObjectChecksums:
    """Calculate stable object checksums for in-memory bytes."""

    payload = bytes(data)
    sha256 = hashlib.sha256(payload).hexdigest()
    md5_digest = hashlib.md5(payload).digest()
    return ObjectChecksums(
        sha256_hex=sha256,
        md5_hex=md5_digest.hex(),
        md5_base64=base64.b64encode(md5_digest).decode("ascii"),
    )


def checksum_stream(
    stream: BinaryIO,
    *,
    chunk_size: int = _DEFAULT_CHUNK_SIZE,
) -> ObjectChecksums:
    """Calculate object checksums while streaming data."""

    sha256 = hashlib.sha256()
    md5 = hashlib.md5()
    while True:
        chunk = stream.read(chunk_size)
        if not chunk:
            break
        sha256.update(chunk)
        md5.update(chunk)
    md5_digest = md5.digest()
    return ObjectChecksums(
        sha256_hex=sha256.hexdigest(),
        md5_hex=md5_digest.hex(),
        md5_base64=base64.b64encode(md5_digest).decode("ascii"),
    )


def checksum_file(path: str | Path, *, chunk_size: int = _DEFAULT_CHUNK_SIZE) -> ObjectChecksums:
    """Calculate object checksums for a file on disk."""

    with Path(path).open("rb") as stream:
        return checksum_stream(stream, chunk_size=chunk_size)
