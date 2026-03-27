"""Scan recent assets and reel packages for missing or corrupt storage objects."""

# mypy: disable-error-code="no-any-return,untyped-decorator"

from __future__ import annotations

import uuid
from argparse import Namespace
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any, Protocol

from content_lab_storage.client import S3StorageClient
from content_lab_storage.config import S3StorageConfig
from content_lab_storage.integrity import (
    ObjectIntegrityResult,
    ObjectIntegrityVerifier,
    S3ObjectIntegrityVerifier,
)
from content_lab_storage.reel_packages import assert_reel_package_complete
from prefect.flows import flow
from prefect.tasks import task
from sqlalchemy.orm import Session, sessionmaker

from content_lab_api.db import SessionLocal
from content_lab_api.models import Asset, OutboxEvent, Reel, ReelOrigin, StorageIntegrityCheck
from content_lab_shared.settings import Settings

from .registry import FlowDefinition

_DEFAULT_ASSET_LIMIT = 50
_DEFAULT_PACKAGE_LIMIT = 25
_ASSET_CHECK_KIND = "asset_object"
_REEL_PACKAGE_CHECK_KIND = "reel_package"
_STORAGE_INTEGRITY_ALERT_EVENT = "storage_integrity.alert"


@dataclass(frozen=True, slots=True)
class AssetIntegrityCandidate:
    """Recent asset row selected for storage verification."""

    asset_id: str
    org_id: str
    asset_class: str
    storage_uri: str
    expected_checksum_sha256: str | None
    created_at: str

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "asset_id": self.asset_id,
            "org_id": self.org_id,
            "asset_class": self.asset_class,
            "storage_uri": self.storage_uri,
            "created_at": self.created_at,
        }
        if self.expected_checksum_sha256 is not None:
            payload["expected_checksum_sha256"] = self.expected_checksum_sha256
        return payload

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> AssetIntegrityCandidate:
        return cls(
            asset_id=str(payload["asset_id"]),
            org_id=str(payload["org_id"]),
            asset_class=str(payload["asset_class"]),
            storage_uri=str(payload["storage_uri"]),
            expected_checksum_sha256=_optional_text(payload.get("expected_checksum_sha256")),
            created_at=str(payload["created_at"]),
        )


@dataclass(frozen=True, slots=True)
class ReelPackageArtifactCandidate:
    """A persisted package artifact that should exist in object storage."""

    name: str
    storage_uri: str
    expected_checksum_sha256: str | None = None

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name,
            "storage_uri": self.storage_uri,
        }
        if self.expected_checksum_sha256 is not None:
            payload["expected_checksum_sha256"] = self.expected_checksum_sha256
        return payload

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> ReelPackageArtifactCandidate:
        return cls(
            name=str(payload["name"]),
            storage_uri=str(payload["storage_uri"]),
            expected_checksum_sha256=_optional_text(payload.get("expected_checksum_sha256")),
        )


@dataclass(frozen=True, slots=True)
class ReelPackageIntegrityCandidate:
    """A persisted generated reel with package artifact references."""

    reel_id: str
    org_id: str
    reel_status: str
    package_root_uri: str | None
    updated_at: str
    artifacts: tuple[ReelPackageArtifactCandidate, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "reel_id": self.reel_id,
            "org_id": self.org_id,
            "reel_status": self.reel_status,
            "updated_at": self.updated_at,
            "artifacts": [artifact.to_payload() for artifact in self.artifacts],
        }
        if self.package_root_uri is not None:
            payload["package_root_uri"] = self.package_root_uri
        return payload

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> ReelPackageIntegrityCandidate:
        raw_artifacts = payload.get("artifacts", [])
        artifacts = []
        if isinstance(raw_artifacts, list):
            for artifact in raw_artifacts:
                if isinstance(artifact, Mapping):
                    artifacts.append(ReelPackageArtifactCandidate.from_payload(artifact))
        return cls(
            reel_id=str(payload["reel_id"]),
            org_id=str(payload["org_id"]),
            reel_status=str(payload["reel_status"]),
            package_root_uri=_optional_text(payload.get("package_root_uri")),
            updated_at=str(payload["updated_at"]),
            artifacts=tuple(artifacts),
        )


@dataclass(frozen=True, slots=True)
class StorageIntegrityCheckResult:
    """Durable integrity outcome for an asset or reel package."""

    org_id: str
    check_kind: str
    status: str
    detail: dict[str, Any]
    checked_object_count: int
    issue_count: int
    asset_id: str | None = None
    reel_id: str | None = None
    check_id: str | None = None
    alert_emitted: bool = False

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "org_id": self.org_id,
            "check_kind": self.check_kind,
            "status": self.status,
            "detail": dict(self.detail),
            "checked_object_count": self.checked_object_count,
            "issue_count": self.issue_count,
            "alert_emitted": self.alert_emitted,
        }
        if self.asset_id is not None:
            payload["asset_id"] = self.asset_id
        if self.reel_id is not None:
            payload["reel_id"] = self.reel_id
        if self.check_id is not None:
            payload["check_id"] = self.check_id
        return payload


class StorageIntegrityRuntime(Protocol):
    """Runtime boundary for discovering and reconciling storage references."""

    def list_recent_assets(
        self, *, limit: int = _DEFAULT_ASSET_LIMIT
    ) -> tuple[AssetIntegrityCandidate, ...]: ...

    def list_recent_reel_packages(
        self,
        *,
        limit: int = _DEFAULT_PACKAGE_LIMIT,
    ) -> tuple[ReelPackageIntegrityCandidate, ...]: ...

    def reconcile_asset(
        self, candidate: AssetIntegrityCandidate
    ) -> StorageIntegrityCheckResult: ...

    def reconcile_reel_package(
        self,
        candidate: ReelPackageIntegrityCandidate,
    ) -> StorageIntegrityCheckResult: ...


class SQLStorageIntegrityRuntime:
    """Default SQL-backed runtime for storage integrity verification."""

    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session] | None = None,
        verifier: ObjectIntegrityVerifier | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._session_factory = session_factory or SessionLocal
        resolved_settings = settings or Settings()
        self._verifier = verifier or S3ObjectIntegrityVerifier(
            _build_storage_client(resolved_settings)
        )

    def list_recent_assets(
        self,
        *,
        limit: int = _DEFAULT_ASSET_LIMIT,
    ) -> tuple[AssetIntegrityCandidate, ...]:
        with self._session_factory() as session:
            assets = (
                session.query(Asset)
                .order_by(Asset.created_at.desc(), Asset.id.desc())
                .limit(limit)
                .all()
            )
            return tuple(
                AssetIntegrityCandidate(
                    asset_id=str(asset.id),
                    org_id=str(asset.org_id),
                    asset_class=asset.asset_class,
                    storage_uri=asset.storage_uri,
                    expected_checksum_sha256=asset.content_hash,
                    created_at=asset.created_at.astimezone(UTC).isoformat(),
                )
                for asset in assets
            )

    def list_recent_reel_packages(
        self,
        *,
        limit: int = _DEFAULT_PACKAGE_LIMIT,
    ) -> tuple[ReelPackageIntegrityCandidate, ...]:
        with self._session_factory() as session:
            reels = (
                session.query(Reel)
                .filter(Reel.origin == ReelOrigin.GENERATED.value)
                .order_by(Reel.updated_at.desc(), Reel.created_at.desc(), Reel.id.desc())
                .all()
            )
            candidates: list[ReelPackageIntegrityCandidate] = []
            for reel in reels:
                package_payload = _package_payload_from_reel_metadata(reel.metadata_)
                if package_payload is None:
                    continue
                candidates.append(
                    ReelPackageIntegrityCandidate(
                        reel_id=str(reel.id),
                        org_id=str(reel.org_id),
                        reel_status=reel.status,
                        package_root_uri=_optional_text(package_payload.get("package_root_uri")),
                        updated_at=reel.updated_at.astimezone(UTC).isoformat(),
                        artifacts=_package_artifacts_from_payload(package_payload),
                    )
                )
                if len(candidates) >= limit:
                    break
            return tuple(candidates)

    def reconcile_asset(self, candidate: AssetIntegrityCandidate) -> StorageIntegrityCheckResult:
        object_result = self._verifier.verify_object(
            storage_uri=candidate.storage_uri,
            expected_checksum_sha256=candidate.expected_checksum_sha256,
            verify_checksum=candidate.expected_checksum_sha256 is not None,
        )
        result = StorageIntegrityCheckResult(
            org_id=candidate.org_id,
            check_kind=_ASSET_CHECK_KIND,
            status=object_result.status,
            asset_id=candidate.asset_id,
            checked_object_count=1,
            issue_count=0 if object_result.status == "healthy" else 1,
            detail={
                "asset": {
                    "asset_class": candidate.asset_class,
                    "asset_id": candidate.asset_id,
                    "created_at": candidate.created_at,
                    "storage_uri": candidate.storage_uri,
                },
                "objects": [object_result.as_payload()],
                "summary": {
                    "checked_object_count": 1,
                    "issue_count": 0 if object_result.status == "healthy" else 1,
                },
            },
        )
        return self._record_result(result)

    def reconcile_reel_package(
        self,
        candidate: ReelPackageIntegrityCandidate,
    ) -> StorageIntegrityCheckResult:
        object_results: list[ObjectIntegrityResult] = []
        issues: list[dict[str, Any]] = []

        for artifact in candidate.artifacts:
            object_result = self._verifier.verify_object(
                storage_uri=artifact.storage_uri,
                expected_checksum_sha256=artifact.expected_checksum_sha256,
                verify_checksum=artifact.expected_checksum_sha256 is not None,
            )
            object_results.append(object_result)
            if object_result.status != "healthy":
                issues.append(
                    {
                        "artifact_name": artifact.name,
                        **object_result.as_payload(),
                    }
                )

        missing_required_artifacts = _missing_required_package_artifacts(candidate.artifacts)
        for artifact_name in missing_required_artifacts:
            issues.append(
                {
                    "artifact_name": artifact_name,
                    "status": "missing",
                    "exists": False,
                    "detail": "package metadata is missing a required artifact reference",
                }
            )

        status = _combined_integrity_status(
            statuses=[item["status"] for item in issues],
            object_statuses=[result.status for result in object_results],
        )
        result = StorageIntegrityCheckResult(
            org_id=candidate.org_id,
            check_kind=_REEL_PACKAGE_CHECK_KIND,
            status=status,
            reel_id=candidate.reel_id,
            checked_object_count=len(object_results),
            issue_count=len(issues),
            detail={
                "package": {
                    "package_root_uri": candidate.package_root_uri,
                    "reel_id": candidate.reel_id,
                    "reel_status": candidate.reel_status,
                    "updated_at": candidate.updated_at,
                },
                "objects": [
                    {
                        "artifact_name": artifact.name,
                        **object_result.as_payload(),
                    }
                    for artifact, object_result in zip(
                        candidate.artifacts, object_results, strict=True
                    )
                ],
                "summary": {
                    "checked_object_count": len(object_results),
                    "issue_count": len(issues),
                    "missing_required_artifacts": missing_required_artifacts,
                },
            },
        )
        return self._record_result(result)

    def _record_result(self, result: StorageIntegrityCheckResult) -> StorageIntegrityCheckResult:
        with self._session_factory.begin() as session:
            check = StorageIntegrityCheck(
                org_id=_as_uuid(result.org_id, field_name="org_id"),
                asset_id=None
                if result.asset_id is None
                else _as_uuid(result.asset_id, field_name="asset_id"),
                check_kind=result.check_kind,
                status=result.status,
                detail=result.detail,
                completed_at=datetime.now(UTC),
            )
            session.add(check)
            session.flush()

            alert_emitted = False
            if result.status in {"missing", "corrupt"}:
                session.add(
                    OutboxEvent(
                        org_id=_as_uuid(result.org_id, field_name="org_id"),
                        aggregate_type="storage_integrity_check",
                        aggregate_id=str(check.id),
                        event_type=_STORAGE_INTEGRITY_ALERT_EVENT,
                        payload=_build_storage_integrity_alert_payload(
                            check_id=str(check.id),
                            result=result,
                        ),
                    )
                )
                alert_emitted = True

            return replace(
                result,
                check_id=str(check.id),
                alert_emitted=alert_emitted,
            )


def build_storage_integrity_runtime() -> StorageIntegrityRuntime:
    """Construct the default SQL-backed storage integrity runtime."""

    return SQLStorageIntegrityRuntime()


@task
def find_recent_assets(limit: int) -> list[dict[str, Any]]:
    """List recent assets to be checked for ghost objects."""

    runtime = build_storage_integrity_runtime()
    return [candidate.to_payload() for candidate in runtime.list_recent_assets(limit=limit)]


@task
def find_recent_reel_packages(limit: int) -> list[dict[str, Any]]:
    """List recent generated reel packages to be verified."""

    runtime = build_storage_integrity_runtime()
    return [candidate.to_payload() for candidate in runtime.list_recent_reel_packages(limit=limit)]


@task
def reconcile_assets(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Persist integrity results for recent assets."""

    runtime = build_storage_integrity_runtime()
    return [
        runtime.reconcile_asset(AssetIntegrityCandidate.from_payload(candidate)).to_payload()
        for candidate in candidates
    ]


@task
def reconcile_reel_packages(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Persist integrity results for recent reel packages."""

    runtime = build_storage_integrity_runtime()
    return [
        runtime.reconcile_reel_package(
            ReelPackageIntegrityCandidate.from_payload(candidate)
        ).to_payload()
        for candidate in candidates
    ]


@flow(name="storage_integrity_check")
def storage_integrity_check(
    asset_limit: int = _DEFAULT_ASSET_LIMIT,
    package_limit: int = _DEFAULT_PACKAGE_LIMIT,
) -> dict[str, Any]:
    """Scan recent storage-backed assets and reel packages for missing or corrupt objects."""

    asset_candidates = find_recent_assets(asset_limit)
    package_candidates = find_recent_reel_packages(package_limit)
    asset_results = reconcile_assets(asset_candidates)
    package_results = reconcile_reel_packages(package_candidates)
    results = [*asset_results, *package_results]

    counts = {
        "assets_scanned": len(asset_candidates),
        "packages_scanned": len(package_candidates),
        "healthy": 0,
        "missing": 0,
        "corrupt": 0,
        "skipped": 0,
        "alerts_emitted": 0,
        "records_written": len(results),
    }
    for result in results:
        status = str(result["status"])
        if status in counts:
            counts[status] += 1
        if bool(result.get("alert_emitted")):
            counts["alerts_emitted"] += 1

    return {
        "status": "completed",
        "counts": counts,
        "assets": asset_candidates,
        "packages": package_candidates,
        "results": results,
    }


def build_storage_integrity_check_kwargs(_args: Namespace) -> dict[str, object]:
    """Map CLI arguments onto the storage integrity flow signature."""

    return {}


FLOW_DEFINITION = FlowDefinition(
    name="storage_integrity_check",
    description="Scan recent assets and ready-to-post packages for missing or corrupt storage.",
    entrypoint=storage_integrity_check,
    build_kwargs=build_storage_integrity_check_kwargs,
)


def _package_payload_from_reel_metadata(
    metadata: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    candidate = _mapping(_mapping(metadata).get("package"))
    if not candidate and "package_uri" in _mapping(metadata):
        candidate = {"package_root_uri": _mapping(metadata).get("package_uri")}
    if not candidate:
        return None
    if "package_root_uri" not in candidate and candidate.get("package_uri") is not None:
        candidate["package_root_uri"] = candidate.get("package_uri")
    return candidate


def _package_artifacts_from_payload(
    package_payload: Mapping[str, Any],
) -> tuple[ReelPackageArtifactCandidate, ...]:
    artifacts: list[ReelPackageArtifactCandidate] = []
    raw_artifacts = package_payload.get("artifacts")
    if isinstance(raw_artifacts, list):
        for raw_artifact in raw_artifacts:
            if not isinstance(raw_artifact, Mapping):
                continue
            name = _optional_text(raw_artifact.get("name"))
            storage_uri = _optional_text(raw_artifact.get("storage_uri"))
            if name is None or storage_uri is None:
                continue
            artifacts.append(
                ReelPackageArtifactCandidate(
                    name=name,
                    storage_uri=storage_uri,
                    expected_checksum_sha256=_optional_text(raw_artifact.get("checksum_sha256")),
                )
            )
    return tuple(artifacts)


def _missing_required_package_artifacts(
    artifacts: tuple[ReelPackageArtifactCandidate, ...],
) -> list[str]:
    try:
        assert_reel_package_complete([{"name": artifact.name} for artifact in artifacts])
    except ValueError as exc:
        prefix = "Reel package is incomplete; missing required artifacts: "
        message = str(exc)
        if message.startswith(prefix):
            return [item.strip() for item in message[len(prefix) :].split(",") if item.strip()]
        raise
    return []


def _combined_integrity_status(
    *,
    statuses: list[str],
    object_statuses: list[str],
) -> str:
    all_statuses = [*statuses, *object_statuses]
    if "corrupt" in all_statuses:
        return "corrupt"
    if "missing" in all_statuses:
        return "missing"
    if "skipped" in all_statuses:
        return "skipped"
    return "healthy"


def _build_storage_integrity_alert_payload(
    *,
    check_id: str,
    result: StorageIntegrityCheckResult,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "check_id": check_id,
        "check_kind": result.check_kind,
        "status": result.status,
        "org_id": result.org_id,
        "checked_object_count": result.checked_object_count,
        "issue_count": result.issue_count,
        "detail": dict(result.detail),
    }
    if result.asset_id is not None:
        payload["asset_id"] = result.asset_id
    if result.reel_id is not None:
        payload["reel_id"] = result.reel_id
    return payload


def _build_storage_client(settings: Settings) -> S3StorageClient:
    return S3StorageClient(
        S3StorageConfig(
            endpoint=settings.minio_endpoint,
            access_key_id=settings.minio_root_user,
            secret_access_key=settings.minio_root_password.get_secret_value(),
            default_bucket=settings.minio_bucket,
        )
    )


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _as_uuid(value: str, *, field_name: str) -> uuid.UUID:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    return uuid.UUID(normalized)


__all__ = [
    "AssetIntegrityCandidate",
    "FLOW_DEFINITION",
    "ReelPackageArtifactCandidate",
    "ReelPackageIntegrityCandidate",
    "SQLStorageIntegrityRuntime",
    "StorageIntegrityCheckResult",
    "StorageIntegrityRuntime",
    "build_storage_integrity_runtime",
    "storage_integrity_check",
]
