from __future__ import annotations

from content_lab_core.types import AssetKind, Platform, QAVerdict, RunStatus


class TestRunStatus:
    def test_members(self) -> None:
        assert RunStatus.PENDING.value == "pending"
        assert RunStatus.COMPLETED.value == "completed"

    def test_all_values(self) -> None:
        assert len(RunStatus) == 6


class TestAssetKind:
    def test_members(self) -> None:
        assert AssetKind.IMAGE.value == "image"
        assert AssetKind.VIDEO.value == "video"

    def test_all_values(self) -> None:
        assert len(AssetKind) == 5


class TestQAVerdict:
    def test_pass_fail(self) -> None:
        assert QAVerdict.PASS.value == "pass"
        assert QAVerdict.FAIL.value == "fail"


class TestPlatform:
    def test_members(self) -> None:
        assert Platform.INSTAGRAM.value == "instagram"
        assert Platform.TIKTOK.value == "tiktok"
        assert Platform.YOUTUBE_SHORTS.value == "youtube_shorts"
