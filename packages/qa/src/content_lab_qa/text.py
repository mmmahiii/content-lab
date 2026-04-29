"""Caption and short-copy meta-language scanning for publish packages."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from content_lab_core.types import QAVerdict
from content_lab_qa.gate import QAResult

# Harden publish captions against internal / planning / system phrasing.
# Keep aligned with semantic_script._META_FAIL_PATTERNS where noted.

CaptionMetaRule = tuple[str, re.Pattern[str], str]

_CAPTION_META_FAIL_RULES: tuple[CaptionMetaRule, ...] = (
    (
        "caption_meta_placeholder",
        re.compile(
            r"\b(insert (the )?hook|write (the )?hook|todo|placeholder|"
            r"hook text(?! ?:)|overlay text(?! ?:)|caption text|lorem ipsum)\b",
            re.IGNORECASE,
        ),
        "Caption looks like a placeholder or authoring instruction instead of publish copy.",
    ),
    (
        "caption_meta_generation",
        re.compile(
            r"\b(plain[- ]language step|planner language|generation process|"
            r"script package|short[- ]form reel|packaged as|caption plan|"
            r"hashtags ready|overlay plan|fresh angle)\b",
            re.IGNORECASE,
        ),
        "Caption references generation artifacts rather than the reel subject.",
    ),
    (
        "caption_internal_system",
        re.compile(
            r"\b("
            r"clear captions?|internal caption|system caption|"
            r"draft caption|do not publish|internal use only|not for publish"
            r")\b",
            re.IGNORECASE,
        ),
        "Caption reads like internal or system guidance instead of publishable post copy.",
    ),
)


def extract_caption_text_entries(package_payload: Mapping[str, Any]) -> list[tuple[str, str]]:
    """Return ``(field_path, text)`` for every caption body in the package payload."""

    entries: list[tuple[str, str]] = []
    trace = package_payload.get("creative_trace")
    if isinstance(trace, Mapping):
        script = trace.get("script")
        if isinstance(script, Mapping):
            entries.extend(
                _rows_from_caption_variants(
                    script.get("caption_variants"),
                    "creative_trace.script.caption_variants",
                )
            )

    root = package_payload.get("caption_variants")
    if root is not None:
        entries.extend(_rows_from_caption_variants(root, "caption_variants"))

    return entries


def lint_caption_texts(
    entries: Sequence[tuple[str, str]],
) -> list[dict[str, str]]:
    """Run caption meta rules; return structured findings (non-empty if any violation)."""

    findings: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for field_path, raw_text in entries:
        text = raw_text.strip()
        if not text:
            continue
        for code, pattern, rule_message in _CAPTION_META_FAIL_RULES:
            if pattern.search(text):
                key = (field_path, code, text[:280])
                if key in seen:
                    continue
                seen.add(key)
                findings.append(
                    {
                        "field_path": field_path,
                        "code": code,
                        "rule": rule_message,
                        "caption_text": text if len(text) <= 400 else f"{text[:397]}...",
                    }
                )
    return findings


def validate_caption_meta_language(package_payload: Mapping[str, Any] | object) -> QAResult:
    """Fail packages whose caption variants contain meta/system language."""

    if not isinstance(package_payload, Mapping):
        return QAResult(
            gate_name="caption_meta_language",
            verdict=QAVerdict.SKIP,
            message="Caption meta-language QA skipped: package payload is not an object.",
            details={},
        )

    payload = dict(package_payload)
    entries = extract_caption_text_entries(payload)
    if not entries:
        return QAResult(
            gate_name="caption_meta_language",
            verdict=QAVerdict.FAIL,
            message=(
                "Package is missing caption variant text required for meta-language QA "
                "(expected creative_trace.script.caption_variants or caption_variants)."
            ),
            details={"errors": ["missing_caption_sources"]},
        )

    findings = lint_caption_texts(entries)
    if findings:
        return QAResult(
            gate_name="caption_meta_language",
            verdict=QAVerdict.FAIL,
            message=findings[0]["rule"],
            details={"findings": findings, "failure_code": findings[0]["code"]},
        )

    return QAResult(
        gate_name="caption_meta_language",
        verdict=QAVerdict.PASS,
        message="Caption variants contain no blocked meta or system language.",
        details={"caption_field_paths": [path for path, _ in entries]},
    )


def _rows_from_caption_variants(raw: object, base_path: str) -> list[tuple[str, str]]:
    if raw is None:
        return []
    if isinstance(raw, str):
        stripped = raw.strip()
        if not stripped:
            return []
        return [(base_path, stripped)]

    if not isinstance(raw, list):
        return []

    rows: list[tuple[str, str]] = []
    for index, item in enumerate(raw):
        field_path = f"{base_path}[{index}]"
        if isinstance(item, Mapping):
            text = str(item.get("text", "")).strip()
            variant = str(item.get("variant", "")).strip()
            label = variant or str(index)
            rows.append((f"{base_path}[{index}]/{label}", text))
        else:
            rows.append((field_path, str(item).strip()))
    return [(path, text) for path, text in rows if text]


__all__ = [
    "extract_caption_text_entries",
    "lint_caption_texts",
    "validate_caption_meta_language",
]
