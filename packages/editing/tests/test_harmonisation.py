from __future__ import annotations

import importlib.util
from io import BytesIO
from pathlib import Path

import pytest

from content_lab_editing.composition_manifest import (
    CompositionLayer,
    CompositionManifest,
    LayerHarmonisationPass,
)
from content_lab_editing.harmonisation import (
    SceneColourStats,
    analyse_foreground_layer,
    analyse_scene_region,
    build_harmonisation_filter_segments,
    default_harmonisation_for_layer,
    derive_harmonisation_params,
)
from content_lab_editing.layered_ffmpeg import build_layered_filter_graph


def _png(width: int, height: int, *, rgb: tuple[int, int, int], alpha: int = 255) -> bytes:
    from PIL import Image

    buffer = BytesIO()
    Image.new("RGBA", (width, height), (*rgb, alpha)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_default_harmonisation_for_alpha_cutout() -> None:
    layer = CompositionLayer(
        layer_id="hero",
        asset_id="hero",
        asset_kind="transparent_cutout_png",
        media_type="image",
        z_index=10,
        start_time=0,
        end_time=4,
        mask_mode="alpha",
    )

    harmonisation = default_harmonisation_for_layer(layer)

    assert harmonisation is not None
    assert harmonisation.colour_match_to_scene is True
    assert harmonisation.shadow_blend is True


def test_derive_harmonisation_params_brightness_and_contrast() -> None:
    scene = SceneColourStats(0.8, 0.8, 0.8, 0.8, 0.2, 100)
    foreground = SceneColourStats(0.2, 0.2, 0.2, 0.2, 0.1, 100)
    harmonisation = LayerHarmonisationPass(
        colour_match_to_scene=True,
        brightness_match=True,
        contrast_match=True,
        edge_softening=True,
        strength=1.0,
    )

    params = derive_harmonisation_params(
        CompositionLayer(
            layer_id="hero",
            asset_id="hero",
            asset_kind="transparent_cutout_png",
            media_type="image",
            z_index=10,
            start_time=0,
            end_time=4,
            height=400,
        ),
        scene=scene,
        foreground=foreground,
        harmonisation=harmonisation,
    )

    assert params.brightness_delta > 0
    assert params.contrast_factor > 1.0
    assert params.edge_blur_radius >= 1


def test_build_harmonisation_filter_segments_includes_eq_and_boxblur() -> None:
    from content_lab_editing.harmonisation import HarmonisationParams

    params = HarmonisationParams(
        colour_match_to_scene=True,
        brightness_match=True,
        contrast_match=True,
        shadow_blend=False,
        edge_softening=True,
        brightness_delta=0.1,
        contrast_factor=1.1,
        edge_blur_radius=2,
    )
    segments = build_harmonisation_filter_segments("src", "dst", params)
    joined = ";".join(segments)

    assert "eq=brightness=" in joined
    assert "colorbalance=" in joined
    assert "boxblur=2:2" in joined


@pytest.mark.skipif(
    importlib.util.find_spec("PIL") is None,
    reason="Pillow is required for harmonisation analysis tests",
)
def test_analyse_scene_and_foreground(tmp_path: Path) -> None:
    background = tmp_path / "bg.png"
    foreground = tmp_path / "fg.png"
    background.write_bytes(_png(1080, 1920, rgb=(200, 200, 200)))
    foreground.write_bytes(_png(400, 400, rgb=(40, 40, 40), alpha=255))

    layer = CompositionLayer(
        layer_id="hero",
        asset_id="hero",
        asset_kind="object_image",
        media_type="image",
        z_index=10,
        start_time=0,
        end_time=4,
        x=100,
        y=200,
        width=400,
        height=400,
    )

    scene = analyse_scene_region(background, layer, canvas_width=1080, canvas_height=1920)
    fg_stats = analyse_foreground_layer(foreground)

    assert scene is not None
    assert fg_stats is not None
    assert scene.mean_luma > fg_stats.mean_luma


def _sample_manifest() -> CompositionManifest:
    return CompositionManifest(
        canvas_width=1080,
        canvas_height=1920,
        duration=1.0,
        fps=24,
        background_layer=CompositionLayer(
            layer_id="bg",
            asset_id="asset-bg",
            asset_kind="background_image",
            media_type="image",
            z_index=0,
            start_time=0.0,
            end_time=1.0,
        ),
        layers=[
            CompositionLayer(
                layer_id="fg",
                asset_id="asset-fg",
                asset_kind="transparent_cutout_png",
                media_type="image",
                z_index=1,
                start_time=0.0,
                end_time=1.0,
                x=320,
                y=720,
                width=420,
                height=420,
                mask_mode="alpha",
            ),
        ],
        audio_layers=[],
    )


def test_filter_graph_without_harmonisation_unchanged_overlay() -> None:
    manifest = _sample_manifest()
    graph = build_layered_filter_graph(
        manifest,
        input_indexes={"bg": 0, "fg": 1},
        staged_assets={
            "asset-bg": Path("bg.png"),
            "asset-fg": Path("fg.png"),
        },
        harmonisation_by_layer={},
    )

    assert "boxblur=" not in graph
    assert "colorbalance=" not in graph
    assert "[base0][layer0]overlay=" in graph


def test_filter_graph_with_shadow_blend_branch() -> None:
    from content_lab_editing.harmonisation import HarmonisationParams

    manifest = _sample_manifest()
    params = HarmonisationParams(
        colour_match_to_scene=False,
        brightness_match=False,
        contrast_match=False,
        shadow_blend=True,
        edge_softening=False,
        shadow_offset_y=12,
        shadow_blur_radius=10,
        shadow_opacity=0.35,
    )
    graph = build_layered_filter_graph(
        manifest,
        input_indexes={"bg": 0, "fg": 1},
        staged_assets={
            "asset-bg": Path("bg.png"),
            "asset-fg": Path("fg.png"),
        },
        harmonisation_by_layer={"fg": params},
    )

    assert "_shadow" in graph
    assert "alphaextract,boxblur=10:10" in graph
