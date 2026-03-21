"""Shared domain enumerations and type aliases used across Content Lab packages."""

from __future__ import annotations

from enum import Enum


class RunStatus(str, Enum):
    """Lifecycle states for a pipeline run."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AssetKind(str, Enum):
    """Classification of media assets managed by the asset registry."""

    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    TEXT = "text"
    TEMPLATE = "template"


class QAVerdict(str, Enum):
    """Outcome of a quality-assurance gate check."""

    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"
    SKIP = "skip"


class Platform(str, Enum):
    """Social-media platforms supported for reel publishing."""

    INSTAGRAM = "instagram"
    TIKTOK = "tiktok"
    YOUTUBE_SHORTS = "youtube_shorts"
