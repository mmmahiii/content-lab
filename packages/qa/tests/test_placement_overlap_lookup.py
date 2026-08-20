from __future__ import annotations

from io import BytesIO

from content_lab_qa.placement_overlap_lookup import build_overlap_validation_context


def test_build_overlap_validation_context_indexes_by_asset_and_uri() -> None:
    from PIL import Image

    buffer = BytesIO()
    Image.new("L", (4, 4), color=255).save(buffer, format="PNG")
    png_bytes = buffer.getvalue()

    def fetch(uri: str) -> bytes | None:
        if uri == "s3://masks/plate.png":
            return png_bytes
        return None

    context = build_overlap_validation_context(
        assets_by_id={
            "plate": {
                "placement_overlap": {"support_surface_mask_uri": "s3://masks/plate.png"},
                "width": 100,
                "height": 100,
            }
        },
        mask_uris={"s3://masks/plate.png"},
        fetch_bytes=fetch,
    )

    assert "plate" in context.by_asset_id
    assert context.by_asset_id["plate"].support_surface_mask is not None
    assert "s3://masks/plate.png" in context.by_mask_uri
