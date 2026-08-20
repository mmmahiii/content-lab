"""Render strategy decisions for cinematic reel plans."""

from __future__ import annotations

from typing import Literal

RenderStrategy = Literal[
    "realistic_single_scene",
    "realistic_sequence",
    "product_card_layout",
    "tabletop_layout",
    "graphic_layout",
    "low_res_texture_backdrop",
]

REALISTIC_RENDER_STRATEGIES = frozenset({"realistic_single_scene", "realistic_sequence"})
DOWNGRADED_RENDER_STRATEGIES = frozenset(
    {"product_card_layout", "tabletop_layout", "graphic_layout", "low_res_texture_backdrop"}
)


def downgrade_render_strategy_for_environment_quality(
    *,
    has_environment_base: bool,
    has_sharp_environment_base: bool,
    preferred_layout: RenderStrategy = "product_card_layout",
) -> RenderStrategy:
    """Choose a safer render strategy when a filmed-scene base is unavailable."""

    if has_sharp_environment_base:
        return "realistic_single_scene"
    if has_environment_base:
        return "low_res_texture_backdrop"
    return preferred_layout


__all__ = [
    "DOWNGRADED_RENDER_STRATEGIES",
    "REALISTIC_RENDER_STRATEGIES",
    "RenderStrategy",
    "downgrade_render_strategy_for_environment_quality",
]
