"""QA package imports the same copy-lint engine as creative."""

from __future__ import annotations

from content_lab_qa.text import evaluate_user_facing_text


def test_qa_reexports_creative_copy_lint() -> None:
    hits = evaluate_user_facing_text("Use a short-form reel and caption plan", caption_scoped=False)
    assert any(h.code == "meta_generation_language" for h in hits)
