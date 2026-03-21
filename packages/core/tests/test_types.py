from __future__ import annotations

from content_lab_core.types import AssetKind, Platform, QAVerdict, RunStatus


class TestRunStatus:
    def test_members(self) -> None:
        assert RunStatus.PENDING == "pending"
        assert RunStatus.COMPLETED == "completed"

    def test_all_values(self) -> None:
        assert len(RunStatus) == 6


class TestAssetKind:
    def test_members(self) -> None:
        assert AssetKind.IMAGE == "image"
        assert AssetKind.VIDEO == "video"

    def test_all_values(self) -> None:
        assert len(AssetKind) == 5


class TestQAVerdict:
    def test_pass_fail(self) -> None:
        assert QAVerdict.PASS == "pass"
        assert QAVerdict.FAIL == "fail"


class TestPlatform:
    def test_members(self) -> None:
        assert Platform.INSTAGRAM == "instagram"
        assert Platform.TIKTOK == "tiktok"
        assert Platform.YOUTUBE_SHORTS == "youtube_shorts"
