from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest

from content_lab_storage import checksum_bytes, checksum_stream, normalize_sha256
from content_lab_storage.checksums import checksum_file


def test_checksum_bytes_returns_expected_encodings() -> None:
    checksums = checksum_bytes(b"content-lab")

    assert checksums.sha256_hex == (
        "a01ab5b49e93d291f740e8859624248d2aeaf49f7d9adfc45702032101d54a14"
    )
    assert checksums.md5_hex == "ddc5c323ab4fb38f15b88f380fb17540"
    assert checksums.md5_base64 == "3cXDI6tPs48VuI84D7F1QA=="
    assert checksums.content_hash == (
        "sha256:a01ab5b49e93d291f740e8859624248d2aeaf49f7d9adfc45702032101d54a14"
    )
    assert checksums.as_metadata() == {
        "checksum-sha256": (
            "sha256:a01ab5b49e93d291f740e8859624248d2aeaf49f7d9adfc45702032101d54a14"
        )
    }


def test_checksum_stream_matches_bytes() -> None:
    payload = b"phase-1 package bytes"

    from_bytes = checksum_bytes(payload)
    from_stream = checksum_stream(BytesIO(payload), chunk_size=4)

    assert from_stream == from_bytes


def test_checksum_file_reads_from_disk(tmp_path: Path) -> None:
    path = tmp_path / "artifact.bin"
    path.write_bytes(b"artifact-body")

    checksums = checksum_file(path)

    assert checksums.content_hash == (
        "sha256:6c1215ea7a4a26fa2e8d95465bf02d4a698a4fc3dc541b3cf5db487449b10f83"
    )


@pytest.mark.parametrize(
    ("raw_value", "normalized"),
    [
        (
            "sha256:a01ab5b49e93d291f740e8859624248d2aeaf49f7d9adfc45702032101d54a14",
            "sha256:a01ab5b49e93d291f740e8859624248d2aeaf49f7d9adfc45702032101d54a14",
        ),
        (
            "A01AB5B49E93D291F740E8859624248D2AEAF49F7D9ADFC45702032101D54A14",
            "sha256:a01ab5b49e93d291f740e8859624248d2aeaf49f7d9adfc45702032101d54a14",
        ),
    ],
)
def test_normalize_sha256_accepts_prefixed_and_unprefixed_values(
    raw_value: str,
    normalized: str,
) -> None:
    assert normalize_sha256(raw_value) == normalized


def test_normalize_sha256_rejects_invalid_digest() -> None:
    with pytest.raises(ValueError, match="64-character"):
        normalize_sha256("sha256:not-a-real-digest")
