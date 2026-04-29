from __future__ import annotations

from content_lab_creative.copy_lint import (
    USER_FACING_COPY_RULE_DEFS,
    CopyRuleDef,
    evaluate_user_facing_text,
)


def test_default_registry_covers_cap_d001_categories() -> None:
    bug = "Create a explore reel for Smoke Test Page focused on operations for Busy founders..."
    hits = evaluate_user_facing_text(bug, caption_scoped=True)
    categories = {h.category for h in hits}
    assert "test_scaffold_language" in categories
    assert "system_descriptions" in categories
    assert "internal_entities" in categories
    assert "mode_labels" in categories


def test_engine_supports_exact_contains_and_regex_override() -> None:
    rules = (
        CopyRuleDef(
            code="exact_ban",
            category="test_scaffold_language",
            kind="exact",
            pattern="BANNED_LINE",
            message="Exact line is not allowed.",
        ),
        CopyRuleDef(
            code="contains_xy",
            category="internal_entities",
            kind="contains",
            pattern="XYZZY",
            message="Marker leak.",
        ),
        CopyRuleDef(
            code="regex_digits",
            category="meta_generation_language",
            kind="regex",
            pattern=r"\b\d{3}-\d{4}\b",
            message="Looks like an internal id.",
        ),
    )
    exact_hits = evaluate_user_facing_text("  banned_line  ", rules=rules, caption_scoped=True)
    assert len(exact_hits) == 1
    assert exact_hits[0].code == "exact_ban"
    assert exact_hits[0].matched_text == "banned_line"

    contains_hits = evaluate_user_facing_text(
        "prefix XYZZY suffix", rules=rules, caption_scoped=True
    )
    assert len(contains_hits) == 1
    assert contains_hits[0].matched_text == "XYZZY"

    regex_hits = evaluate_user_facing_text("call 999-0000 now", rules=rules, caption_scoped=True)
    assert len(regex_hits) == 1
    assert regex_hits[0].matched_text == "999-0000"


def test_hook_and_overlay_share_engine_with_captions() -> None:
    """Global rules apply to any user text field when caption_scoped is False."""
    meta = "Use a fresh angle for the script package today."
    hits = evaluate_user_facing_text(meta, caption_scoped=False)
    assert any(h.code == "meta_generation_language" for h in hits)


def test_caption_only_rules_skipped_for_non_caption_scope() -> None:
    text = "Create a explore reel for Smoke Test Page focused on operations"
    assert not evaluate_user_facing_text(text, caption_scoped=False)


def test_registry_is_single_source() -> None:
    assert len(USER_FACING_COPY_RULE_DEFS) >= 20
