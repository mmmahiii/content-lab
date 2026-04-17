from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

EXPECTED_TASK_TYPES = (
    "process_reel",
    "creative_planning",
    "asset_resolution",
    "editing",
    "qa",
    "packaging",
)
EXPECTED_PACKAGE_ARTIFACTS = (
    "final_video",
    "cover",
    "caption_variants",
    "posting_plan",
)
EXPECTED_MINIO_FILES = (
    "final_video.mp4",
    "cover.png",
    "caption_variants.txt",
    "posting_plan.json",
    "provenance.json",
    "package_manifest.json",
)


class SmokeFailure(RuntimeError):
    """Raised when the smoke path finds an actionable failure."""


class SmokeRunner:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.repo_root = Path(args.repo_root).resolve()
        self.compose_file = self.repo_root / "infra" / "docker-compose.yml"
        self.env_file = self.repo_root / ".env"
        self.api_base_url = args.api_base_url.rstrip("/")
        self.request_counter = 0
        self.dotenv = self._load_dotenv()

    def run(self) -> dict[str, Any]:
        self._step("Checking prerequisites")
        self._assert_command("docker")
        self._assert_command("poetry")
        self._assert_command("ffmpeg")
        self._assert_compose_service_running("postgres")
        self._assert_compose_service_running("minio")
        self._wait_for_api()
        if self.args.provider_mode != "mock":
            self._assert_live_runway_key_configured()

        bucket = self._env_setting("MINIO_BUCKET") or "content-lab"
        org_id, org_created = self._ensure_org()
        page_id = self._ensure_page(org_id)
        self._ensure_policy(org_id, page_id)
        family_id = self._create_reel_family(org_id, page_id)
        reel_id = self._create_reel(org_id, page_id, family_id)
        run_id = self._queue_run(org_id, page_id, reel_id)
        self._execute_process_reel(reel_id, run_id)

        self._step("Loading final API state")
        run_detail = self._api_json("GET", f"/orgs/{org_id}/runs/{run_id}")
        package_detail = self._api_json("GET", f"/orgs/{org_id}/packages/{run_id}")
        reel_detail = self._api_json("GET", f"/orgs/{org_id}/pages/{page_id}/reels/{reel_id}")

        self._step("Verifying API-level success criteria")
        self._assert_equal(
            actual=str(reel_detail["status"]),
            expected="ready",
            label="reel status",
            context={"org_id": org_id, "page_id": page_id, "reel_id": reel_id},
        )
        self._assert_equal(
            actual=str(run_detail["status"]),
            expected="succeeded",
            label="run status",
            context={"run_id": run_id},
        )
        self._assert_equal(
            actual=str(package_detail["status"]),
            expected="succeeded",
            label="package status",
            context={"run_id": run_id},
        )
        task_types = [str(task["task_type"]) for task in run_detail.get("tasks", [])]
        for task_type in EXPECTED_TASK_TYPES:
            self._assert_contains(
                collection=task_types,
                expected=task_type,
                label="run tasks",
                context={"run_id": run_id},
            )
        artifact_names = [str(artifact["name"]) for artifact in package_detail.get("artifacts", [])]
        for artifact_name in EXPECTED_PACKAGE_ARTIFACTS:
            self._assert_contains(
                collection=artifact_names,
                expected=artifact_name,
                label="package artifacts",
                context={"run_id": run_id},
            )
        self._assert_non_blank(
            value=package_detail.get("provenance_uri"),
            label="package provenance_uri",
            context={"run_id": run_id},
        )
        self._assert_non_blank(
            value=package_detail.get("manifest_uri"),
            label="package manifest_uri",
            context={"run_id": run_id},
        )

        self._step("Inspecting Postgres state")
        run_rows = self._postgres_query(
            f"select id, workflow_key, status from runs where id = '{run_id}';"
        )
        task_rows = self._postgres_query(
            "select task_type, status from tasks "
            f"where run_id = '{run_id}' order by created_at, task_type;"
        )
        reel_rows = self._postgres_query(f"select id, status from reels where id = '{reel_id}';")
        outbox_rows = self._postgres_query(
            "select event_type, delivery_status, aggregate_id from outbox_events "
            f"where aggregate_id = '{run_id}' order by created_at;"
        )
        self._assert_true(
            len(run_rows) == 1,
            "Expected one run row for the smoke run.",
            context={"run_id": run_id, "rows": run_rows},
        )
        self._assert_true(
            len(reel_rows) == 1,
            "Expected one reel row for the smoke reel.",
            context={"reel_id": reel_id, "rows": reel_rows},
        )
        self._assert_true(
            len(task_rows) >= len(EXPECTED_TASK_TYPES),
            "Expected all persisted task rows for the smoke run.",
            context={"run_id": run_id, "rows": task_rows},
        )
        self._assert_true(
            any(row.startswith("process_reel.package_ready|") for row in outbox_rows),
            "Expected a package-ready outbox event for the smoke run.",
            context={"run_id": run_id, "rows": outbox_rows},
        )

        self._step("Listing the canonical package prefix from MinIO")
        package_prefix = f"reels/packages/{reel_id}"
        minio_listing = self._minio_listing(bucket=bucket, prefix=package_prefix)
        self._assert_true(
            len(minio_listing) > 0,
            "Expected package objects to exist in MinIO.",
            context={"bucket": bucket, "prefix": package_prefix},
        )
        for filename in EXPECTED_MINIO_FILES:
            self._assert_true(
                any(filename in item for item in minio_listing),
                f"Expected MinIO package listing to include {filename}.",
                context={"bucket": bucket, "prefix": package_prefix, "objects": minio_listing},
            )

        self._step("Smoke succeeded")
        summary = {
            "org_id": org_id,
            "page_id": page_id,
            "reel_family_id": family_id,
            "reel_id": reel_id,
            "run_id": run_id,
            "provider_mode": self.args.provider_mode,
            "reel_status": str(reel_detail["status"]),
            "run_status": str(run_detail["status"]),
            "package_root_uri": str(package_detail["package_root_uri"]),
            "policy_scope": self.args.policy_scope,
            "org_created": org_created,
        }
        print(json.dumps(summary, indent=2, sort_keys=True))
        return summary

    def _ensure_org(self) -> tuple[str, bool]:
        requested_org_id = self.args.org_id.strip()
        if requested_org_id:
            self._step(f"Reusing existing org {requested_org_id}")
            rows = self._postgres_query(
                f"select id, slug from orgs where id = '{requested_org_id}';"
            )
            self._assert_true(
                len(rows) == 1,
                "Expected the requested org to exist before reusing it.",
                context={"org_id": requested_org_id, "rows": rows},
            )
            return requested_org_id, False

        self._step("Creating a fresh smoke-test org directly in Postgres")
        org_id = str(uuid.uuid4())
        slug = f"mvp-smoke-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        sql = (
            "insert into orgs (id, name, slug) "
            f"values ('{org_id}', 'MVP Smoke Org', '{self._sql_literal(slug)}');"
        )
        self._postgres_query(sql)
        return org_id, True

    def _ensure_page(self, org_id: str) -> str:
        if self.args.page_id.strip():
            page_id = str(self.args.page_id.strip())
            self._step(f"Reusing existing page {page_id}")
            page = self._api_json("GET", f"/orgs/{org_id}/pages/{page_id}")
            self._assert_equal(
                actual=str(page["ownership"]),
                expected="owned",
                label="page ownership",
                context={"org_id": org_id, "page_id": page_id},
            )
            return page_id

        self._step("Creating an owned page through the real API")
        page_external_id = f"mvp-smoke-page-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        page = self._api_json(
            "POST",
            f"/orgs/{org_id}/pages",
            body={
                "platform": self.args.page_platform,
                "display_name": self.args.page_display_name,
                "external_page_id": page_external_id,
                "handle": self.args.page_handle,
                "ownership": "owned",
                "metadata": {
                    "persona": {
                        "label": "Calm educator",
                        "audience": "Busy founders",
                        "content_pillars": ["operations"],
                    },
                    "constraints": {
                        "allow_direct_cta": True,
                        "max_hashtags": 4,
                    },
                    "timezone": "UTC",
                    "locale": "en",
                },
            },
        )
        return str(page["id"])

    def _ensure_policy(self, org_id: str, page_id: str) -> None:
        self._step("Upserting the applicable policy")
        body = {
            "mode_ratios": {
                "exploit": 0.0,
                "explore": 1.0,
                "mutation": 0.0,
                "chaos": 0.0,
            },
            "budget": {
                "per_run_usd_limit": 20.0,
                "daily_usd_limit": 50.0,
                "monthly_usd_limit": 500.0,
            },
        }
        if self.args.policy_scope == "global":
            self._api_json("PATCH", f"/orgs/{org_id}/policy/global", body=body)
            return
        self._api_json("PATCH", f"/orgs/{org_id}/policy/page/{page_id}", body=body)

    def _create_reel_family(self, org_id: str, page_id: str) -> str:
        self._step("Creating a reel family")
        family = self._api_json(
            "POST",
            f"/orgs/{org_id}/pages/{page_id}/reel-families",
            body={
                "name": f"{self.args.family_name} {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')}",
                "mode": "explore",
                "metadata": {
                    "smoke": True,
                    "source": "scripts/e2e_mvp_smoke.py",
                    "provider_mode": self.args.provider_mode,
                },
            },
        )
        return str(family["id"])

    def _create_reel(self, org_id: str, page_id: str, family_id: str) -> str:
        self._step("Creating a generated reel")
        reel = self._api_json(
            "POST",
            f"/orgs/{org_id}/pages/{page_id}/reel-families/{family_id}/reels",
            body={
                "origin": "generated",
                "status": "draft",
                "variant_label": self.args.variant_label,
                "metadata": {
                    "smoke": True,
                    "source": "scripts/e2e_mvp_smoke.py",
                    "provider_mode": self.args.provider_mode,
                },
            },
        )
        return str(reel["id"])

    def _queue_run(self, org_id: str, page_id: str, reel_id: str) -> str:
        self._step("Queueing process_reel via the real trigger route")
        queued_run = self._api_json(
            "POST",
            f"/orgs/{org_id}/pages/{page_id}/reels/{reel_id}/trigger",
            body={
                "input_params": {"priority": "high"},
                "metadata": {
                    "source": "e2e-mvp-smoke",
                    "provider_mode": self.args.provider_mode,
                },
            },
        )
        return str(queued_run["id"])

    def _execute_process_reel(self, reel_id: str, run_id: str) -> None:
        self._step(
            f"Executing the process_reel flow with provider mode {self.args.provider_mode!r}"
        )
        command = [
            "poetry",
            "run",
            "python",
            "-m",
            "content_lab_orchestrator.cli",
            "run",
            "--flow",
            "process_reel",
            "--reel-id",
            reel_id,
            "--run-id",
            run_id,
        ]
        env = os.environ.copy()
        env["RUNWAY_API_MODE"] = self.args.provider_mode
        completed = self._run_command(
            command,
            cwd=self.repo_root / "apps" / "orchestrator",
            env=env,
            step="orchestrator flow execution",
        )
        self._assert_true(
            bool(completed.stdout.strip() or completed.stderr.strip()),
            "Expected orchestrator CLI output after running process_reel.",
            context={"reel_id": reel_id, "run_id": run_id},
        )

    def _wait_for_api(self) -> None:
        self._step(f"Waiting for API health at {self.api_base_url}/health")
        deadline = time.time() + self.args.health_timeout_seconds
        last_error: str | None = None
        while time.time() < deadline:
            try:
                health = self._read_json(f"{self.api_base_url}/health")
                if health.get("status") == "ok":
                    return
                last_error = json.dumps(health, sort_keys=True)
            except (HTTPError, URLError, ValueError) as exc:
                last_error = str(exc)
            time.sleep(1)
        raise SmokeFailure(
            "API health check did not become ready before timeout. "
            f"Checked {self.api_base_url}/health for {self.args.health_timeout_seconds} seconds. "
            f"Last error: {last_error}"
        )

    def _api_json(
        self, method: str, path: str, body: Mapping[str, Any] | None = None
    ) -> dict[str, Any]:
        self.request_counter += 1
        headers = {
            "X-Actor-Id": self.args.actor_id,
            "X-Request-Id": f"e2e-mvp-smoke-{self.request_counter:03d}",
        }
        encoded_body = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            encoded_body = json.dumps(body).encode("utf-8")
        request = Request(
            f"{self.api_base_url}{path}",
            data=encoded_body,
            headers=headers,
            method=method,
        )
        try:
            with urlopen(request) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            response_body = exc.read().decode("utf-8", errors="replace")
            raise SmokeFailure(
                f"API request failed for {method} {path} with HTTP {exc.code}. "
                f"Response body: {response_body}"
            ) from exc
        except URLError as exc:
            raise SmokeFailure(
                f"API request failed for {method} {path}. Could not reach {self.api_base_url}: {exc}"
            ) from exc
        if not isinstance(payload, dict):
            raise SmokeFailure(
                f"API request for {method} {path} returned a non-object JSON payload: {payload!r}"
            )
        return payload

    def _assert_compose_service_running(self, service_name: str) -> None:
        completed = self._run_command(
            [
                "docker",
                "compose",
                "-f",
                str(self.compose_file),
                "ps",
                "--status",
                "running",
                "--services",
            ],
            step=f"compose service check for {service_name}",
        )
        running_services = {line.strip() for line in completed.stdout.splitlines() if line.strip()}
        self._assert_true(
            service_name in running_services,
            "Expected required Docker Compose service to be running before the smoke path.",
            context={"service": service_name, "running_services": sorted(running_services)},
        )

    def _postgres_query(self, sql: str) -> list[str]:
        completed = self._run_command(
            [
                "docker",
                "compose",
                "-f",
                str(self.compose_file),
                "exec",
                "-T",
                "postgres",
                "psql",
                "-U",
                "contentlab",
                "-d",
                "contentlab",
                "-v",
                "ON_ERROR_STOP=1",
                "-At",
                "-F",
                "|",
                "-c",
                sql,
            ],
            step="Postgres query",
        )
        return [line.strip() for line in completed.stdout.splitlines() if line.strip()]

    def _minio_listing(self, *, bucket: str, prefix: str) -> list[str]:
        minio_user = self._env_setting("MINIO_ROOT_USER")
        minio_password = self._env_setting("MINIO_ROOT_PASSWORD")
        self._assert_non_blank(
            minio_user,
            label="MINIO_ROOT_USER",
            context={"env_file": str(self.env_file)},
        )
        self._assert_non_blank(
            minio_password,
            label="MINIO_ROOT_PASSWORD",
            context={"env_file": str(self.env_file)},
        )
        shell_command = (
            "mc alias set local http://minio:9000 "
            f"{self._sh_single_quote(str(minio_user))} "
            f"{self._sh_single_quote(str(minio_password))} >/dev/null && "
            f"mc ls --recursive local/{bucket}/{prefix.lstrip('/')}"
        )
        completed = self._run_command(
            [
                "docker",
                "compose",
                "-f",
                str(self.compose_file),
                "run",
                "--rm",
                "--no-deps",
                "--entrypoint",
                "/bin/sh",
                "minio-init",
                "-lc",
                shell_command,
            ],
            step="MinIO listing",
        )
        return [line.strip() for line in completed.stdout.splitlines() if line.strip()]

    def _assert_live_runway_key_configured(self) -> None:
        runway_key = self._env_setting("RUNWAY_API_KEY")
        self._assert_true(
            bool(runway_key and runway_key != "changeme"),
            "RUNWAY_API_KEY must be configured for live-provider smoke runs.",
            context={"env_file": str(self.env_file)},
        )

    def _env_setting(self, name: str) -> str | None:
        value = os.environ.get(name)
        if value is not None and value.strip():
            return value.strip()
        candidate = self.dotenv.get(name)
        if candidate is None:
            return None
        stripped = candidate.strip()
        return stripped or None

    def _load_dotenv(self) -> dict[str, str]:
        if not self.env_file.exists():
            return {}
        values: dict[str, str] = {}
        for raw_line in self.env_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, raw_value = line.split("=", 1)
            value = raw_value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
                value = value[1:-1]
            values[key.strip()] = value
        return values

    def _read_json(self, url: str) -> dict[str, Any]:
        with urlopen(url) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"Expected JSON object from {url}, got {payload!r}")
        return payload

    def _run_command(
        self,
        command: list[str],
        *,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
        step: str,
    ) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(
            command,
            cwd=None if cwd is None else str(cwd),
            env=None if env is None else dict(env),
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            stderr = completed.stderr.strip()
            stdout = completed.stdout.strip()
            raise SmokeFailure(
                f"{step} failed with exit code {completed.returncode}. "
                f"Command: {' '.join(command)}. "
                f"Stdout: {stdout or '<empty>'}. "
                f"Stderr: {stderr or '<empty>'}."
            )
        return completed

    @staticmethod
    def _step(message: str) -> None:
        print(f"\n==> {message}", flush=True)

    @staticmethod
    def _assert_command(name: str) -> None:
        if shutil.which(name) is None:
            raise SmokeFailure(f"Missing required command on PATH: {name}")

    @staticmethod
    def _assert_true(condition: bool, message: str, *, context: Mapping[str, Any]) -> None:
        if not condition:
            raise SmokeFailure(f"{message} Context: {json.dumps(dict(context), sort_keys=True)}")

    @staticmethod
    def _assert_equal(
        *,
        actual: str,
        expected: str,
        label: str,
        context: Mapping[str, Any],
    ) -> None:
        if actual != expected:
            raise SmokeFailure(
                f"Unexpected {label}: expected {expected!r}, got {actual!r}. "
                f"Context: {json.dumps(dict(context), sort_keys=True)}"
            )

    @staticmethod
    def _assert_contains(
        *,
        collection: Iterable[str],
        expected: str,
        label: str,
        context: Mapping[str, Any],
    ) -> None:
        items = list(collection)
        if expected not in items:
            raise SmokeFailure(
                f"Expected {label} to include {expected!r}. "
                f"Actual: {items}. Context: {json.dumps(dict(context), sort_keys=True)}"
            )

    @staticmethod
    def _assert_non_blank(value: Any, *, label: str, context: Mapping[str, Any]) -> None:
        if value is None or not str(value).strip():
            raise SmokeFailure(
                f"Expected {label} to be present and non-blank. "
                f"Context: {json.dumps(dict(context), sort_keys=True)}"
            )

    @staticmethod
    def _sql_literal(value: str) -> str:
        return value.replace("'", "''")

    @staticmethod
    def _sh_single_quote(value: str) -> str:
        return "'" + value.replace("'", "'\"'\"'") + "'"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the Content Lab MVP golden-path smoke using the real scaffold."
    )
    parser.add_argument(
        "--repo-root",
        default=str(Path(__file__).resolve().parents[1]),
        help="Absolute or relative path to the repo root.",
    )
    parser.add_argument(
        "--api-base-url",
        default="http://127.0.0.1:8000",
        help="Base URL for the running API instance.",
    )
    parser.add_argument("--org-id", default="", help="Reuse an existing org UUID.")
    parser.add_argument("--page-id", default="", help="Reuse an existing page UUID.")
    parser.add_argument(
        "--policy-scope",
        choices=("page", "global"),
        default="page",
        help="Where to upsert the policy used by the smoke run.",
    )
    parser.add_argument(
        "--actor-id",
        default="operator:e2e-mvp-smoke",
        help="Actor header used for API requests.",
    )
    parser.add_argument(
        "--page-platform",
        default="instagram",
        help="Platform used when creating a smoke owned page.",
    )
    parser.add_argument(
        "--page-display-name",
        default="MVP Smoke Test Page",
        help="Display name used when creating a smoke owned page.",
    )
    parser.add_argument(
        "--page-handle",
        default="@mvp-smoke",
        help="Handle used when creating a smoke owned page.",
    )
    parser.add_argument(
        "--family-name",
        default="MVP Smoke Family",
        help="Base family name for the smoke reel family.",
    )
    parser.add_argument(
        "--variant-label",
        default="A",
        help="Variant label for the smoke reel.",
    )
    parser.add_argument(
        "--provider-mode",
        choices=("mock", "live"),
        default=os.environ.get("RUNWAY_API_MODE", "mock").strip().lower() or "mock",
        help="Runway provider mode to use for the orchestrator step.",
    )
    parser.add_argument(
        "--health-timeout-seconds",
        type=int,
        default=60,
        help="How long to wait for API health before failing.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.page_id and not args.org_id:
        raise SystemExit("Provide --org-id when reusing an existing --page-id.")
    try:
        SmokeRunner(args).run()
    except SmokeFailure as exc:
        print(f"\nSmoke failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
