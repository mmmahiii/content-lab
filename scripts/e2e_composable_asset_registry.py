from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import struct
import subprocess
import sys
import time
import uuid
import wave
import zlib
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, insert, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from content_lab_api.models import (
    Asset,
    AssetPack,
    AssetPackItem,
    AssetUsage,
    GeneratedReelStatus,
    Org,
    Page,
    Reel,
    ReelFamily,
)
from content_lab_api.services import build_asset_pack_compositions
from content_lab_assets.types import (
    AlphaMode,
    AssetKind,
    AssetSource,
    MediaType,
    detect_png_transparency,
    detect_png_visual_metadata,
)


class ComposableAssetRegistryFailure(RuntimeError):
    """Raised when the composable asset registry smoke test finds a regression."""


class E2EComposableAssetRegistryRunner:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.repo_root = Path(args.repo_root).resolve()
        self.artifact_root = (
            Path(args.artifact_dir).resolve()
            if args.artifact_dir
            else self.repo_root / "artifacts" / "e2e_composable_asset_registry"
        )
        self.run_dir = self.artifact_root / time.strftime("%Y%m%d-%H%M%S")
        self.database_url = args.database_url or os.environ.get(
            "DATABASE_URL",
            "postgresql+psycopg://contentlab:contentlab@127.0.0.1:5433/contentlab",
        )
        self.asset_paths: dict[str, Path] = {}
        self.hook_text_by_asset_id: dict[str, str] = {}

    def run(self) -> dict[str, Any]:
        self._step("Checking prerequisites")
        self._assert_command("ffmpeg")
        self.run_dir.mkdir(parents=True, exist_ok=True)

        self._step("Creating synthetic component media")
        synthetic_assets = self._create_synthetic_assets()

        engine = create_engine(self.database_url, pool_pre_ping=True)
        try:
            with engine.connect() as connection:
                connection.exec_driver_sql("SELECT 1")
        except OperationalError as exc:
            raise ComposableAssetRegistryFailure(
                f"PostgreSQL is not reachable at {self.database_url!r}. "
                "Start infra and run migrations before this smoke test."
            ) from exc

        SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
        with SessionLocal() as db:
            self._step("Registering component assets and one reusable asset pack")
            org_id, pack_id, page_id, family_id = self._seed_pack(db, synthetic_assets)

            self._step("Verifying first-class component asset registration")
            registration_summary = self._assert_component_assets_registered(db, org_id=org_id)

            self._step("Running asset combinator for five candidates")
            candidates = build_asset_pack_compositions(
                db,
                org_id=org_id,
                asset_pack_id=pack_id,
                target_reel_count=5,
                format_filters=["hook-led tip"],
                style_filters=["clean editorial"],
                selection_mode="balanced",
            )
            self._assert_equal(len(candidates), 5, "candidate count")
            self._assert_candidates_use_overlapping_assets(candidates)

            self._step("Rendering two candidate reels from component assets")
            render_results = []
            for index, candidate in enumerate(candidates[:2], start=1):
                render_results.append(
                    self._render_candidate(
                        db,
                        org_id=org_id,
                        page_id=page_id,
                        family_id=family_id,
                        pack_id=pack_id,
                        candidate_index=index,
                        candidate=candidate,
                    )
                )
            self._assert_final_renders_differ(render_results)

            self._step("Verifying component-level asset_usage lineage")
            lineage_summary = self._assert_asset_usage_lineage(
                db,
                org_id=org_id,
                reel_ids=[uuid.UUID(result["reel_id"]) for result in render_results],
            )
            db.commit()

        result = {
            "status": "passed",
            "artifact_dir": str(self.run_dir),
            "asset_pack_id": str(pack_id),
            "candidate_count": len(candidates),
            "rendered_reels": render_results,
            "registration": registration_summary,
            "lineage": lineage_summary,
        }
        (self.run_dir / "summary.json").write_text(
            json.dumps(result, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return result

    def _create_synthetic_assets(self) -> list[dict[str, Any]]:
        bg_a = self.run_dir / "background_clean_blue.png"
        bg_b = self.run_dir / "background_clean_green.png"
        object_a = self.run_dir / "object_transparent_gold.png"
        object_b = self.run_dir / "object_transparent_coral.png"
        image = self.run_dir / "reference_image.png"
        hook_a = self.run_dir / "hook_a.txt"
        hook_b = self.run_dir / "hook_b.txt"
        hook_c = self.run_dir / "hook_c.txt"
        audio_a = self.run_dir / "audio_a.wav"
        audio_b = self.run_dir / "audio_b.wav"

        self._write_rgba_png(
            bg_a, 720, 1280, self._gradient_pixels(720, 1280, (19, 78, 118), (246, 247, 238))
        )
        self._write_rgba_png(
            bg_b, 720, 1280, self._gradient_pixels(720, 1280, (35, 96, 70), (238, 243, 232))
        )
        self._write_rgba_png(
            image, 720, 1280, self._gradient_pixels(720, 1280, (76, 61, 132), (240, 239, 250))
        )
        self._write_rgba_png(
            object_a, 256, 256, self._transparent_badge_pixels(256, (236, 186, 72))
        )
        self._write_rgba_png(object_b, 256, 256, self._transparent_badge_pixels(256, (231, 98, 82)))
        hook_a.write_text("Stop wasting your first three seconds", encoding="utf-8")
        hook_b.write_text("This tiny setup changes the scroll", encoding="utf-8")
        hook_c.write_text("Make the visual do the first job", encoding="utf-8")
        self._write_wav(audio_a, frequency=440.0)
        self._write_wav(audio_b, frequency=554.37)

        records = [
            self._asset_record(
                path=bg_a,
                asset_kind=AssetKind.BACKGROUND_IMAGE,
                media_type=MediaType.IMAGE,
                pack_role="background",
                title="blue editorial background",
                performance_score=0.86,
            ),
            self._asset_record(
                path=bg_b,
                asset_kind=AssetKind.BACKGROUND_IMAGE,
                media_type=MediaType.IMAGE,
                pack_role="background",
                title="green editorial background",
                performance_score=0.82,
            ),
            self._asset_record(
                path=object_a,
                asset_kind=AssetKind.TRANSPARENT_CUTOUT_PNG,
                media_type=MediaType.IMAGE,
                pack_role="object",
                title="gold transparent badge",
                performance_score=0.78,
            ),
            self._asset_record(
                path=object_b,
                asset_kind=AssetKind.TRANSPARENT_CUTOUT_PNG,
                media_type=MediaType.IMAGE,
                pack_role="object",
                title="coral transparent badge",
                performance_score=0.74,
            ),
            self._asset_record(
                path=image,
                asset_kind=AssetKind.OBJECT_IMAGE,
                media_type=MediaType.IMAGE,
                pack_role="object",
                title="opaque reference image",
                performance_score=0.55,
                include_in_pack=False,
            ),
            self._asset_record(
                path=hook_a,
                asset_kind=AssetKind.HOOK_TEXT,
                media_type=MediaType.TEXT,
                pack_role="hook",
                title="first three seconds hook",
                hook_text=hook_a.read_text(encoding="utf-8"),
                performance_score=0.91,
            ),
            self._asset_record(
                path=hook_b,
                asset_kind=AssetKind.HOOK_TEXT,
                media_type=MediaType.TEXT,
                pack_role="hook",
                title="scroll setup hook",
                hook_text=hook_b.read_text(encoding="utf-8"),
                performance_score=0.88,
            ),
            self._asset_record(
                path=hook_c,
                asset_kind=AssetKind.HOOK_TEXT,
                media_type=MediaType.TEXT,
                pack_role="hook",
                title="visual first job hook",
                hook_text=hook_c.read_text(encoding="utf-8"),
                performance_score=0.84,
            ),
            self._asset_record(
                path=audio_a,
                asset_kind=AssetKind.AUDIO_TRACK,
                media_type=MediaType.AUDIO,
                pack_role="audio",
                title="warm sine pulse",
                performance_score=0.72,
            ),
            self._asset_record(
                path=audio_b,
                asset_kind=AssetKind.AUDIO_TRACK,
                media_type=MediaType.AUDIO,
                pack_role="audio",
                title="bright sine pulse",
                performance_score=0.68,
            ),
        ]
        return records

    def _asset_record(
        self,
        *,
        path: Path,
        asset_kind: AssetKind,
        media_type: MediaType,
        pack_role: str,
        title: str,
        performance_score: float,
        hook_text: str | None = None,
        include_in_pack: bool = True,
    ) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "asset_kind": asset_kind.value,
            "media_type": media_type.value,
            "source_type": AssetSource.UPLOADED.value,
            "title": title,
            "performance_score": performance_score,
            "compatibility": self._compatibility(asset_kind),
        }
        if media_type is MediaType.IMAGE:
            data = path.read_bytes()
            visual = detect_png_visual_metadata(data)
            if visual is not None:
                metadata["visual"] = visual.model_dump(mode="json")
            if asset_kind is AssetKind.TRANSPARENT_CUTOUT_PNG:
                transparency = detect_png_transparency(data)
                metadata["transparency"] = transparency.model_dump(mode="json")
        if hook_text is not None:
            metadata["hook"] = hook_text
        return {
            "id": uuid.uuid4(),
            "path": path,
            "asset_kind": asset_kind.value,
            "media_type": media_type.value,
            "pack_role": pack_role,
            "title": title,
            "metadata": metadata,
            "include_in_pack": include_in_pack,
        }

    def _seed_pack(
        self,
        db: Session,
        assets: Sequence[Mapping[str, Any]],
    ) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
        org_id = uuid.uuid4()
        page_id = uuid.uuid4()
        family_id = uuid.uuid4()
        pack_id = uuid.uuid4()
        db.execute(
            insert(Org).values(
                id=org_id,
                name="Composable Asset Registry Smoke",
                slug=f"car-smoke-{org_id.hex[:12]}",
            )
        )
        db.execute(
            insert(Page).values(
                id=page_id,
                org_id=org_id,
                platform="instagram",
                display_name="Composable Registry Smoke",
                handle=f"car_{org_id.hex[:8]}",
                kind="owned",
            )
        )
        db.execute(
            insert(ReelFamily).values(
                id=family_id,
                org_id=org_id,
                page_id=page_id,
                name="Composable asset registry smoke family",
                metadata_={"source": "e2e_composable_asset_registry"},
            )
        )
        db.execute(
            insert(AssetPack).values(
                id=pack_id,
                org_id=org_id,
                name="Clean editorial component pack",
                niche="creator education",
                purpose="Prove one component pack can drive multiple reels.",
                requested_asset_count=9,
                asset_mix_requested_json={
                    "background": 2,
                    "object": 2,
                    "hook": 3,
                    "audio": 2,
                },
                status="ready",
                strategy_summary="Reusable backgrounds, transparent objects, hooks, and audio.",
            )
        )

        for index, asset in enumerate(assets):
            asset_id = asset["id"]
            metadata = dict(asset["metadata"])
            self.asset_paths[str(asset_id)] = Path(asset["path"])
            if asset["asset_kind"] == AssetKind.HOOK_TEXT.value:
                self.hook_text_by_asset_id[str(asset_id)] = str(metadata["hook"])
            db.execute(
                insert(Asset).values(
                    id=asset_id,
                    org_id=org_id,
                    asset_class="component",
                    storage_uri=Path(asset["path"]).as_uri(),
                    source=metadata["source_type"],
                    status="ready",
                    content_hash=self._sha256_file(Path(asset["path"])),
                    metadata_=metadata,
                )
            )
            if asset["include_in_pack"]:
                db.execute(
                    insert(AssetPackItem).values(
                        id=uuid.uuid4(),
                        asset_pack_id=pack_id,
                        asset_id=asset_id,
                        asset_kind=asset["asset_kind"],
                        pack_role=asset["pack_role"],
                        reuse_purpose=f"Reusable {asset['pack_role']} component",
                        priority=index,
                        status="selected",
                        metadata_json=metadata,
                        compatibility_metadata=metadata["compatibility"],
                    )
                )
        db.flush()
        return org_id, pack_id, page_id, family_id

    def _assert_component_assets_registered(
        self, db: Session, *, org_id: uuid.UUID
    ) -> dict[str, Any]:
        rows = list(db.scalars(select(Asset).where(Asset.org_id == org_id)).all())
        by_kind = Counter(str(row.metadata_.get("asset_kind")) for row in rows)
        required = {
            AssetKind.OBJECT_IMAGE.value: "image assets can be registered",
            AssetKind.TRANSPARENT_CUTOUT_PNG.value: "transparent PNG assets can be registered",
            AssetKind.BACKGROUND_IMAGE.value: "background assets can be registered",
            AssetKind.HOOK_TEXT.value: "hook/text assets can be registered",
            AssetKind.AUDIO_TRACK.value: "audio assets can be registered",
        }
        for asset_kind, label in required.items():
            self._assert_true(by_kind[asset_kind] > 0, label, {"registered_kinds": dict(by_kind)})

        transparent_assets = [
            row
            for row in rows
            if row.metadata_.get("asset_kind") == AssetKind.TRANSPARENT_CUTOUT_PNG.value
        ]
        for asset in transparent_assets:
            transparency = asset.metadata_.get("transparency")
            self._assert_true(isinstance(transparency, Mapping), "transparent PNG metadata exists")
            self._assert_equal(
                str(transparency.get("alpha_mode")),
                AlphaMode.ALPHA.value,
                "transparent PNG alpha mode",
            )
            self._assert_equal(
                str(transparency.get("has_transparency")).lower(),
                "true",
                "transparent PNG has_transparency",
            )

        return {"asset_count": len(rows), "by_kind": dict(by_kind)}

    def _assert_candidates_use_overlapping_assets(self, candidates: Sequence[Any]) -> None:
        all_asset_ids: list[str] = []
        unique_role_signatures: set[tuple[tuple[str, str], ...]] = set()
        for candidate in candidates:
            roles = candidate.roles
            for role in ("background", "foreground", "hook", "audio"):
                self._assert_true(role in roles, f"candidate includes {role}")
            all_asset_ids.extend(asset.asset_id for asset in roles.values())
            unique_role_signatures.add(
                tuple(sorted((role, asset.asset_id) for role, asset in roles.items()))
            )

        counts = Counter(all_asset_ids)
        reused = {asset_id: count for asset_id, count in counts.items() if count >= 2}
        self._assert_true(
            bool(reused),
            "candidates use overlapping reusable assets",
            {"asset_counts": dict(counts)},
        )
        self._assert_true(
            len(unique_role_signatures) >= 5,
            "candidate compositions are distinct",
            {"distinct_signatures": len(unique_role_signatures)},
        )

    def _render_candidate(
        self,
        db: Session,
        *,
        org_id: uuid.UUID,
        page_id: uuid.UUID,
        family_id: uuid.UUID,
        pack_id: uuid.UUID,
        candidate_index: int,
        candidate: Any,
    ) -> dict[str, Any]:
        roles = candidate.roles
        background = roles["background"]
        foreground = roles["foreground"]
        hook = roles["hook"]
        audio = roles["audio"]
        output_path = self.run_dir / f"candidate_{candidate_index}.mp4"
        hook_text = self.hook_text_by_asset_id[hook.asset_id]
        self._ffmpeg_render(
            background_path=self.asset_paths[background.asset_id],
            foreground_path=self.asset_paths[foreground.asset_id],
            audio_path=self.asset_paths[audio.asset_id],
            output_path=output_path,
            hook_text=hook_text,
        )
        self._assert_true(output_path.exists(), "render output exists", {"path": str(output_path)})
        self._assert_true(output_path.stat().st_size > 10_000, "render output is non-empty")

        render_hash = self._sha256_file(output_path)
        final_asset_id = uuid.uuid4()
        reel_id = uuid.uuid4()
        db.execute(
            insert(Reel).values(
                id=reel_id,
                org_id=org_id,
                reel_family_id=family_id,
                origin="generated",
                status=GeneratedReelStatus.READY.value,
                variant_label=f"candidate-{candidate_index}",
                metadata_={
                    "source": "e2e_composable_asset_registry",
                    "asset_pack_id": str(pack_id),
                    "composition_id": candidate.composition_id,
                    "render_sha256": render_hash,
                },
            )
        )
        db.execute(
            insert(Asset).values(
                id=final_asset_id,
                org_id=org_id,
                asset_class="render",
                storage_uri=output_path.as_uri(),
                source=AssetSource.DERIVED.value,
                status="ready",
                content_hash=render_hash,
                metadata_={
                    "asset_kind": AssetKind.FINAL_RENDER.value,
                    "media_type": MediaType.VIDEO.value,
                    "source_type": AssetSource.DERIVED.value,
                    "derived_from_component_assets": [
                        asset.asset_id for _, asset in sorted(roles.items())
                    ],
                    "composition_id": candidate.composition_id,
                },
            )
        )

        component_roles = {
            "background": background,
            "object": foreground,
            "hook": hook,
            "audio": audio,
        }
        for sort_order, (component_role, asset) in enumerate(component_roles.items()):
            db.execute(
                insert(AssetUsage).values(
                    id=uuid.uuid4(),
                    org_id=org_id,
                    reel_id=reel_id,
                    asset_id=uuid.UUID(asset.asset_id),
                    usage_role=component_role,
                    sort_order=sort_order,
                    component_role=component_role,
                    layer_role=self._layer_role(component_role),
                    sequence_index=0,
                    z_index=sort_order,
                    start_time=0.0,
                    end_time=2.0,
                    transform_version="e2e-composable-v1",
                    transform_recipe={
                        "composition_id": candidate.composition_id,
                        "candidate_index": candidate_index,
                        "source_asset_kind": asset.asset_kind.value,
                    },
                    metadata_json={
                        "asset_pack_id": str(pack_id),
                        "final_render_asset_id": str(final_asset_id),
                    },
                )
            )
        db.execute(
            insert(AssetUsage).values(
                id=uuid.uuid4(),
                org_id=org_id,
                reel_id=reel_id,
                asset_id=final_asset_id,
                usage_role="final_render",
                sort_order=99,
                component_role="final_render",
                layer_role="output",
                sequence_index=0,
                z_index=99,
                start_time=0.0,
                end_time=2.0,
                transform_version="e2e-composable-v1",
                transform_recipe={
                    "derived_from_component_assets": [
                        asset.asset_id for _, asset in sorted(roles.items())
                    ]
                },
                metadata_json={"asset_pack_id": str(pack_id)},
            )
        )
        db.flush()
        return {
            "candidate_index": candidate_index,
            "composition_id": candidate.composition_id,
            "reel_id": str(reel_id),
            "final_render_asset_id": str(final_asset_id),
            "path": str(output_path),
            "sha256": render_hash,
            "component_asset_ids": [asset.asset_id for _, asset in sorted(roles.items())],
        }

    def _assert_final_renders_differ(self, render_results: Sequence[Mapping[str, Any]]) -> None:
        hashes = {str(result["sha256"]) for result in render_results}
        self._assert_equal(len(hashes), len(render_results), "final renders differ")

    def _assert_asset_usage_lineage(
        self,
        db: Session,
        *,
        org_id: uuid.UUID,
        reel_ids: Sequence[uuid.UUID],
    ) -> dict[str, Any]:
        rows = list(
            db.scalars(
                select(AssetUsage).where(
                    AssetUsage.org_id == org_id,
                    AssetUsage.reel_id.in_(reel_ids),
                )
            ).all()
        )
        by_reel: dict[str, list[AssetUsage]] = {}
        for row in rows:
            by_reel.setdefault(str(row.reel_id), []).append(row)
        required_roles = {"background", "object", "hook", "audio", "final_render"}
        for reel_id in reel_ids:
            reel_rows = by_reel.get(str(reel_id), [])
            roles = {str(row.component_role) for row in reel_rows}
            self._assert_true(
                required_roles.issubset(roles),
                "asset_usage records component roles",
                {"reel_id": str(reel_id), "roles": sorted(roles)},
            )
            component_rows = [row for row in reel_rows if row.component_role != "final_render"]
            self._assert_equal(len(component_rows), 4, "component lineage row count")
            for row in component_rows:
                self._assert_true(row.layer_role is not None, "asset_usage layer_role recorded")
                self._assert_true(
                    row.transform_recipe is not None,
                    "asset_usage transform recipe recorded",
                )
                self._assert_true(
                    row.metadata_json.get("final_render_asset_id") is not None,
                    "asset_usage links components to final render",
                )
        return {
            "asset_usage_count": len(rows),
            "roles": sorted({str(row.component_role) for row in rows}),
        }

    def _ffmpeg_render(
        self,
        *,
        background_path: Path,
        foreground_path: Path,
        audio_path: Path,
        output_path: Path,
        hook_text: str,
    ) -> None:
        safe_hook = hook_text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
        filter_complex = (
            "[0:v]scale=720:1280,format=rgba[bg];"
            "[1:v]scale=280:-1,format=rgba[fg];"
            "[bg][fg]overlay=(W-w)/2:H-h-220[comp];"
            f"[comp]drawtext=text='{safe_hook}':"
            "fontcolor=white:fontsize=44:box=1:boxcolor=black@0.55:"
            "boxborderw=24:x=(w-text_w)/2:y=120[v]"
        )
        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-loop",
            "1",
            "-t",
            "2",
            "-i",
            str(background_path),
            "-loop",
            "1",
            "-t",
            "2",
            "-i",
            str(foreground_path),
            "-i",
            str(audio_path),
            "-filter_complex",
            filter_complex,
            "-map",
            "[v]",
            "-map",
            "2:a",
            "-shortest",
            "-r",
            "24",
            "-pix_fmt",
            "yuv420p",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            str(output_path),
        ]
        result = subprocess.run(command, cwd=self.repo_root, capture_output=True, text=True)
        if result.returncode != 0:
            raise ComposableAssetRegistryFailure(
                "FFmpeg render failed.\n"
                f"Command: {' '.join(command)}\n"
                f"stdout: {result.stdout}\n"
                f"stderr: {result.stderr}"
            )

    def _compatibility(self, asset_kind: AssetKind) -> dict[str, Any]:
        base: dict[str, Any] = {
            "niche": ["creator education"],
            "topic": ["asset reuse"],
            "theme": ["composition"],
            "emotion": ["confident"],
            "visual_style": ["clean editorial"],
            "pace": ["snappy"],
            "format_type": ["hook-led tip"],
        }
        if asset_kind is AssetKind.BACKGROUND_IMAGE:
            base["works_as_background_for"] = [
                AssetKind.TRANSPARENT_CUTOUT_PNG.value,
                AssetKind.OBJECT_IMAGE.value,
                "foreground",
                "object",
            ]
        if asset_kind is AssetKind.TRANSPARENT_CUTOUT_PNG:
            base["requires_transparency"] = True
        return base

    @staticmethod
    def _layer_role(component_role: str) -> str:
        return {
            "background": "base_visual",
            "object": "foreground_overlay",
            "hook": "text_overlay",
            "audio": "audio_bed",
        }[component_role]

    @staticmethod
    def _gradient_pixels(
        width: int,
        height: int,
        start: tuple[int, int, int],
        end: tuple[int, int, int],
    ) -> bytes:
        pixels = bytearray()
        for y in range(height):
            t = y / max(1, height - 1)
            r = int(start[0] * (1 - t) + end[0] * t)
            g = int(start[1] * (1 - t) + end[1] * t)
            b = int(start[2] * (1 - t) + end[2] * t)
            for x in range(width):
                vignette = int(16 * math.sin((x / width) * math.pi))
                pixels.extend(
                    (min(255, r + vignette), min(255, g + vignette), min(255, b + vignette), 255)
                )
        return bytes(pixels)

    @staticmethod
    def _transparent_badge_pixels(size: int, color: tuple[int, int, int]) -> bytes:
        pixels = bytearray()
        center = (size - 1) / 2
        radius = size * 0.42
        for y in range(size):
            for x in range(size):
                distance = math.sqrt((x - center) ** 2 + (y - center) ** 2)
                if distance <= radius:
                    alpha = (
                        230 if distance < radius - 8 else int(max(0, 230 * (radius - distance) / 8))
                    )
                    pixels.extend((color[0], color[1], color[2], alpha))
                else:
                    pixels.extend((0, 0, 0, 0))
        return bytes(pixels)

    @staticmethod
    def _write_rgba_png(path: Path, width: int, height: int, rgba_pixels: bytes) -> None:
        if len(rgba_pixels) != width * height * 4:
            raise ValueError("RGBA pixel data length does not match dimensions")

        def chunk(kind: bytes, data: bytes) -> bytes:
            return (
                struct.pack(">I", len(data))
                + kind
                + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
            )

        raw = b"".join(
            b"\x00" + rgba_pixels[y * width * 4 : (y + 1) * width * 4] for y in range(height)
        )
        png = (
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, level=6))
            + chunk(b"IEND", b"")
        )
        path.write_bytes(png)

    @staticmethod
    def _write_wav(path: Path, *, frequency: float, duration_seconds: float = 2.0) -> None:
        sample_rate = 44_100
        frame_count = int(sample_rate * duration_seconds)
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            frames = bytearray()
            for index in range(frame_count):
                envelope = 0.5 + 0.5 * math.sin(2 * math.pi * index / frame_count)
                sample = int(
                    16_000 * envelope * math.sin(2 * math.pi * frequency * index / sample_rate)
                )
                frames.extend(struct.pack("<h", sample))
            wav.writeframes(bytes(frames))

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _assert_command(self, command: str) -> None:
        if shutil.which(command) is None:
            raise ComposableAssetRegistryFailure(f"Required command not found on PATH: {command}")

    def _assert_true(
        self,
        condition: bool,
        label: str,
        context: Mapping[str, Any] | None = None,
    ) -> None:
        if not condition:
            raise ComposableAssetRegistryFailure(
                f"Assertion failed: {label}"
                + (f"\nContext: {json.dumps(context, indent=2, default=str)}" if context else "")
            )

    def _assert_equal(self, actual: object, expected: object, label: str) -> None:
        if actual != expected:
            raise ComposableAssetRegistryFailure(
                f"Assertion failed: {label}; expected {expected!r}, got {actual!r}"
            )

    @staticmethod
    def _step(message: str) -> None:
        print(f"[e2e-composable] {message}", flush=True)


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify composable Asset Registry pack, combinator, render, and lineage paths."
    )
    parser.add_argument("--repo-root", default=Path(__file__).resolve().parents[1])
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--artifact-dir", default=None)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        result = E2EComposableAssetRegistryRunner(args).run()
    except ComposableAssetRegistryFailure as exc:
        print(f"[e2e-composable] FAILED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
