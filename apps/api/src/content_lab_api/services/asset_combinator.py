"""Load asset packs and produce compatibility-filtered composition candidates."""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from typing import Any, Literal, cast

from sqlalchemy.orm import Session

from content_lab_api.models import AssetPack, AssetPackItem
from content_lab_api.schemas.asset_packs import (
    AssetLedConceptOut,
    AssetLedIdeasOut,
    AssetLedReelBriefOut,
    AssetPackOut,
)
from content_lab_assets.combinator import (
    CandidateComposition,
    OutputPotentialEstimate,
    PackAsset,
    estimate_output_potential,
    generate_candidate_compositions,
    select_performance_weighted_combinations,
)


def build_asset_pack_compositions(
    db: Session,
    *,
    org_id: uuid.UUID,
    asset_pack_id: uuid.UUID,
    target_reel_count: int,
    format_filters: Sequence[str] | None = None,
    style_filters: Sequence[str] | None = None,
    selection_mode: Literal["balanced", "exploit", "explore", "mutation", "chaos"] = "balanced",
) -> list[CandidateComposition]:
    """Generate candidate compositions from one asset pack."""

    pack_assets = _load_pack_assets(db, org_id=org_id, asset_pack_id=asset_pack_id)
    if selection_mode == "balanced":
        return cast(
            list[CandidateComposition],
            generate_candidate_compositions(
                pack_assets,
                target_reel_count=target_reel_count,
                format_filters=format_filters,
                style_filters=style_filters,
            ),
        )
    return cast(
        list[CandidateComposition],
        select_performance_weighted_combinations(
            pack_assets,
            target_reel_count=target_reel_count,
            format_filters=format_filters,
            style_filters=style_filters,
            mode=selection_mode,
        ),
    )


def estimate_asset_pack_output_potential(
    db: Session,
    *,
    org_id: uuid.UUID,
    asset_pack_id: uuid.UUID,
    target_reel_count: int | None = None,
    format_filters: Sequence[str] | None = None,
    style_filters: Sequence[str] | None = None,
) -> OutputPotentialEstimate:
    """Estimate useful reel output for one asset pack."""

    return estimate_output_potential(
        _load_pack_assets(db, org_id=org_id, asset_pack_id=asset_pack_id),
        target_reel_count=target_reel_count,
        format_filters=format_filters,
        style_filters=style_filters,
    )


def build_asset_led_reel_ideas(
    db: Session,
    *,
    org_id: uuid.UUID,
    asset_pack_id: uuid.UUID,
    target_concept_count: int,
    selected_asset_ids: Sequence[uuid.UUID] | None = None,
    format_filters: Sequence[str] | None = None,
    style_filters: Sequence[str] | None = None,
    selection_mode: Literal["balanced", "exploit", "explore", "mutation", "chaos"] = "balanced",
) -> AssetLedIdeasOut:
    """Generate reel ideas and structured briefs from existing pack assets."""

    pack = _load_asset_pack(db, org_id=org_id, asset_pack_id=asset_pack_id)
    pack_assets = _load_pack_assets(
        db,
        org_id=org_id,
        asset_pack_id=asset_pack_id,
        selected_asset_ids=selected_asset_ids,
    )
    if selected_asset_ids:
        candidates = cast(
            list[CandidateComposition],
            generate_candidate_compositions(
                pack_assets,
                target_reel_count=target_concept_count,
                format_filters=format_filters,
                style_filters=style_filters,
                selection_mode=selection_mode,
            ),
        )
    else:
        candidates = build_asset_pack_compositions(
            db,
            org_id=org_id,
            asset_pack_id=asset_pack_id,
            target_reel_count=target_concept_count,
            format_filters=format_filters,
            style_filters=style_filters,
            selection_mode=selection_mode,
        )
    return AssetLedIdeasOut(
        asset_pack=AssetPackOut.model_validate(pack),
        concepts=[
            _concept_from_candidate(pack=pack, candidate=candidate) for candidate in candidates
        ],
    )


def _load_pack_assets(
    db: Session,
    *,
    org_id: uuid.UUID,
    asset_pack_id: uuid.UUID,
    selected_asset_ids: Sequence[uuid.UUID] | None = None,
) -> list[PackAsset]:
    _load_asset_pack(db, org_id=org_id, asset_pack_id=asset_pack_id)
    query = db.query(AssetPackItem).filter(AssetPackItem.asset_pack_id == asset_pack_id)
    if selected_asset_ids:
        query = query.filter(AssetPackItem.asset_id.in_(selected_asset_ids))
    items = query.order_by(AssetPackItem.priority.asc(), AssetPackItem.created_at.asc()).all()
    return [_pack_asset_from_item(item) for item in items if item.asset_id is not None]


def _load_asset_pack(db: Session, *, org_id: uuid.UUID, asset_pack_id: uuid.UUID) -> AssetPack:
    pack = (
        db.query(AssetPack)
        .filter(AssetPack.org_id == org_id, AssetPack.id == asset_pack_id)
        .one_or_none()
    )
    if pack is None:
        raise ValueError(f"Unknown asset_pack_id {asset_pack_id!s}")
    return pack


def _pack_asset_from_item(item: AssetPackItem) -> PackAsset:
    metadata = _merge_metadata(
        _planned_spec_metadata(item),
        item.metadata_json,
        {"compatibility": item.compatibility_metadata},
    )
    return PackAsset.from_pack_item(
        {
            "id": str(item.id),
            "asset_id": str(item.asset_id),
            "asset_kind": item.asset_kind,
            "pack_role": item.pack_role,
            "title": _first_text(
                item.reuse_purpose,
                metadata.get("working_title"),
                metadata.get("title"),
                metadata.get("description"),
            ),
            "metadata": metadata,
            "performance_score": metadata.get("performance_score"),
            "usage_count": metadata.get("usage_count", 0),
        }
    )


def _planned_spec_metadata(item: AssetPackItem) -> dict[str, Any]:
    if item.planned_asset_spec is None:
        return {}
    spec = item.planned_asset_spec
    return {
        "compatible_with": dict(spec.compatible_with or {}),
        "compatibility": dict(spec.compatibility_metadata or {}),
        "format_type": list(spec.intended_reel_formats or []),
    }


def _merge_metadata(*values: Mapping[str, Any] | None) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for value in values:
        if value:
            merged.update(dict(value))
    return merged


def _concept_from_candidate(
    *, pack: AssetPack, candidate: CandidateComposition
) -> AssetLedConceptOut:
    roles = candidate.roles
    source_asset_ids = [uuid.UUID(asset.asset_id) for _, asset in sorted(roles.items())]
    emotional_angles = _candidate_angles(candidate)
    compatible_formats = _candidate_formats(candidate)
    primary_angle = _humanize(emotional_angles[0] if emotional_angles else pack.niche)
    format_name = _humanize(compatible_formats[0] if compatible_formats else "asset led reel")
    hook = _completed_hook(roles.get("hook"), primary_angle)
    concept_title = _concept_title(hook=hook, angle=primary_angle, format_name=format_name)
    visual_sequence = _visual_sequence(roles)
    brief = AssetLedReelBriefOut(
        concept_title=concept_title,
        hook=hook,
        visual_sequence=visual_sequence,
        selected_asset_ids=source_asset_ids,
        composition_intent=_composition_intent(
            pack=pack,
            format_name=format_name,
            primary_angle=primary_angle,
            roles=roles,
        ),
        overlay_plan=_overlay_plan(roles.get("hook"), hook=hook),
        audio_direction=_audio_direction(roles.get("audio"), primary_angle=primary_angle),
        caption_angle=_caption_angle(primary_angle=primary_angle, format_name=format_name),
        posting_plan_seed={
            "niche": pack.niche,
            "target_audience": pack.target_audience,
            "format": format_name,
            "emotional_angle": primary_angle,
            "asset_pack_id": str(pack.id),
            "source_composition_id": candidate.composition_id,
        },
    )
    return AssetLedConceptOut(
        idea=concept_title,
        source_composition_id=candidate.composition_id,
        source_asset_ids=source_asset_ids,
        compatible_formats=compatible_formats,
        emotional_angles=emotional_angles,
        selection_score=candidate.selection_score,
        reasons=candidate.reasons,
        brief=brief,
    )


def _candidate_angles(candidate: CandidateComposition) -> list[str]:
    values: list[str] = []
    for asset in candidate.roles.values():
        values.extend(asset.compatibility.emotion)
        values.extend(asset.compatibility.theme)
        values.extend(asset.compatibility.topic)
        values.extend(_list_from_metadata(asset.metadata, "emotional_angles"))
        values.extend(_list_from_metadata(asset.metadata, "angles"))
    return _dedupe(values)


def _candidate_formats(candidate: CandidateComposition) -> list[str]:
    values: list[str] = []
    for asset in candidate.roles.values():
        values.extend(asset.compatibility.format_type)
        values.extend(_list_from_metadata(asset.metadata, "format_type"))
        values.extend(_list_from_metadata(asset.metadata, "intended_reel_formats"))
    return _dedupe(values)


def _visual_sequence(roles: Mapping[str, PackAsset]) -> list[str]:
    sequence: list[str] = []
    for role in ("background", "foreground", "effect", "hook", "audio", "format"):
        asset = roles.get(role)
        if asset is None:
            continue
        sequence.append(f"{_humanize(role).capitalize()}: {_asset_label(asset)}")
    return sequence


def _composition_intent(
    *,
    pack: AssetPack,
    format_name: str,
    primary_angle: str,
    roles: Mapping[str, PackAsset],
) -> str:
    role_summary = ", ".join(_humanize(role) for role in roles)
    audience = f" for {pack.target_audience}" if pack.target_audience else ""
    return (
        f"Use {role_summary} from the asset pack to create a {format_name} reel "
        f"around {primary_angle}{audience}."
    )


def _overlay_plan(hook_asset: PackAsset | None, *, hook: str) -> str:
    label = _asset_label(hook_asset) if hook_asset is not None else hook
    return f"Open with '{hook}', then keep overlays minimal and anchored to {label}."


def _audio_direction(audio_asset: PackAsset | None, *, primary_angle: str) -> str:
    if audio_asset is None:
        return f"Choose audio that reinforces {primary_angle} without overpowering the hook."
    moods = audio_asset.compatibility.emotion or audio_asset.compatibility.works_with_audio_moods
    mood_text = ", ".join(_humanize(mood) for mood in moods[:2])
    suffix = f" with a {mood_text} mood" if mood_text else ""
    return f"Use {_asset_label(audio_asset)}{suffix} to support {primary_angle}."


def _caption_angle(*, primary_angle: str, format_name: str) -> str:
    return f"Frame the caption as a {format_name} takeaway about {primary_angle}."


def _completed_hook(hook_asset: PackAsset | None, primary_angle: str) -> str:
    hook = _asset_text(
        hook_asset,
        "hook",
        "hook_text",
        "text",
        "copy",
        "caption",
        "line",
    )
    if not hook:
        return f"{primary_angle.title()} in motion"
    stripped = hook.strip()
    if stripped.endswith("...") or stripped.endswith("..") or stripped.endswith("."):
        return f"{stripped.rstrip('.')} of {primary_angle}"
    if stripped.endswith(":"):
        return f"{stripped} {primary_angle}"
    return stripped


def _concept_title(*, hook: str, angle: str, format_name: str) -> str:
    if angle.lower() in hook.lower():
        return hook
    return f"{hook} ({format_name})"


def _asset_label(asset: PackAsset) -> str:
    return (
        _asset_text(
            asset,
            "label",
            "title",
            "working_title",
            "hook",
            "hook_text",
            "text",
            "description",
            "prompt",
        )
        or asset.title
        or _humanize(asset.pack_role or asset.asset_kind.value)
    )


def _asset_text(asset: PackAsset | None, *keys: str) -> str | None:
    if asset is None:
        return None
    return _first_text(*(asset.metadata.get(key) for key in keys), asset.title)


def _first_text(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        text = " ".join(str(value).strip().split())
        if text:
            return text
    return None


def _list_from_metadata(metadata: Mapping[str, Any], key: str) -> list[str]:
    value = metadata.get(key)
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Sequence):
        return [str(item) for item in value if str(item).strip()]
    return []


def _humanize(value: str) -> str:
    return " ".join(str(value).replace("_", " ").replace("-", " ").split())


def _dedupe(values: Sequence[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = " ".join(str(value).strip().split())
        key = normalized.lower().replace("-", "_").replace(" ", "_")
        if normalized and key not in seen:
            seen.add(key)
            result.append(normalized)
    return result


__all__ = [
    "build_asset_led_reel_ideas",
    "build_asset_pack_compositions",
    "estimate_asset_pack_output_potential",
]
