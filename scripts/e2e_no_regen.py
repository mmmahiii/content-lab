from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class NoRegenFailure(RuntimeError):
    """Raised when the no-regeneration regression check fails."""


class NoRegenRunner:
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
        self._assert_compose_service_running("postgres")
        self._wait_for_api()

        org_id = self._create_org()
        payload = self._resolve_payload(org_id=org_id)

        self._step("Resolving the generation request for the first time")
        first_decision = self._api_json(
            "POST",
            f"/orgs/{org_id}/assets/resolve",
            body=payload,
        )
        self._assert_equal(
            actual=str(first_decision["decision"]),
            expected="generate",
            label="first resolve decision",
            context={"org_id": org_id, "decision": first_decision},
        )
        generation_intent = first_decision.get("generation_intent")
        self._assert_true(
            isinstance(generation_intent, Mapping),
            "Expected the first resolve decision to include generation_intent.",
            context={"org_id": org_id, "decision": first_decision},
        )
        generation_intent_map = cast(Mapping[str, Any], generation_intent)
        asset_id = str(generation_intent_map["asset_id"])
        asset_key_hash = str(first_decision["asset_key_hash"])
        first_provider_job_count = self._postgres_int(
            "select count(*) from provider_jobs "
            f"where org_id = '{org_id}' and provider = 'runway';"
        )
        first_provider_history_entries = self._postgres_int(
            "select coalesce(sum(jsonb_array_length(coalesce(metadata->'history', '[]'::jsonb))), 0) "
            "from provider_jobs "
            f"where org_id = '{org_id}' and provider = 'runway';"
        )
        first_task_count = self._postgres_int(
            f"select count(*) from tasks where org_id = '{org_id}';"
        )
        self._assert_equal(
            actual=str(first_provider_job_count),
            expected="1",
            label="provider job count after first resolve",
            context={"org_id": org_id},
        )
        self._assert_equal(
            actual=str(first_provider_history_entries),
            expected="1",
            label="provider submission history length after first resolve",
            context={"org_id": org_id},
        )
        self._assert_equal(
            actual=str(first_task_count),
            expected="1",
            label="task count after first resolve",
            context={"org_id": org_id},
        )

        self._step("Marking the staged asset ready without invoking a second provider submission")
        ready_storage_uri = f"s3://content-lab/assets/derived/{asset_id}.mp4"
        self._postgres_query(
            "update assets "
            "set status = 'ready', storage_uri = "
            f"'{ready_storage_uri}', source = 'runway' "
            f"where id = '{asset_id}' and org_id = '{org_id}';"
        )

        self._step("Resolving the identical generation request again")
        second_decision = self._api_json(
            "POST",
            f"/orgs/{org_id}/assets/resolve",
            body=payload,
        )
        self._assert_equal(
            actual=str(second_decision["decision"]),
            expected="reuse_exact",
            label="second resolve decision",
            context={"org_id": org_id, "decision": second_decision},
        )
        self._assert_equal(
            actual=str(second_decision["asset_id"]),
            expected=asset_id,
            label="reused asset id",
            context={"org_id": org_id, "first": first_decision, "second": second_decision},
        )
        self._assert_equal(
            actual=str(second_decision["asset_key_hash"]),
            expected=asset_key_hash,
            label="reused asset key hash",
            context={"org_id": org_id, "first": first_decision, "second": second_decision},
        )
        self._assert_equal(
            actual=str(second_decision["storage_uri"]),
            expected=ready_storage_uri,
            label="reused storage uri",
            context={"org_id": org_id, "second": second_decision},
        )

        second_provider_job_count = self._postgres_int(
            "select count(*) from provider_jobs "
            f"where org_id = '{org_id}' and provider = 'runway';"
        )
        second_provider_history_entries = self._postgres_int(
            "select coalesce(sum(jsonb_array_length(coalesce(metadata->'history', '[]'::jsonb))), 0) "
            "from provider_jobs "
            f"where org_id = '{org_id}' and provider = 'runway';"
        )
        second_task_count = self._postgres_int(
            f"select count(*) from tasks where org_id = '{org_id}';"
        )
        self._assert_equal(
            actual=str(second_provider_job_count),
            expected="1",
            label="provider job count after second resolve",
            context={"org_id": org_id},
        )
        self._assert_equal(
            actual=str(second_provider_history_entries),
            expected="1",
            label="provider submission history length after second resolve",
            context={"org_id": org_id},
        )
        self._assert_equal(
            actual=str(second_task_count),
            expected="1",
            label="task count after second resolve",
            context={"org_id": org_id},
        )

        self._step("No-regeneration regression succeeded")
        summary = {
            "org_id": org_id,
            "asset_id": asset_id,
            "asset_key_hash": asset_key_hash,
            "first_decision": str(first_decision["decision"]),
            "second_decision": str(second_decision["decision"]),
            "provider_job_count": second_provider_job_count,
            "provider_submission_history_entries": second_provider_history_entries,
            "task_count": second_task_count,
            "storage_uri": ready_storage_uri,
        }
        print(json.dumps(summary, indent=2, sort_keys=True))
        return summary

    def _create_org(self) -> str:
        self._step("Creating a fresh org for the regression check")
        org_id = str(uuid.uuid4())
        slug = f"no-regen-{uuid.uuid4().hex[:12]}"
        self._postgres_query(
            "insert into orgs (id, name, slug) "
            f"values ('{org_id}', 'No Regen Regression Org', '{self._sql_literal(slug)}');"
        )
        return org_id

    @staticmethod
    def _resolve_payload(*, org_id: str) -> dict[str, Any]:
        reference_one = str(uuid.UUID("11111111-1111-4111-8111-111111111111"))
        reference_two = str(uuid.UUID("22222222-2222-4222-8222-222222222222"))
        run_suffix = org_id.split("-", 1)[0]
        return {
            "asset_class": "clip",
            "provider": "Runway",
            "model": "GEN4.5",
            "prompt": f"Hero launch shot {run_suffix}",
            "negative_prompt": "no text overlays",
            "seed": 7,
            "duration_seconds": 6.0,
            "fps": 24,
            "ratio": "9:16",
            "motion": {
                "camera": {"pan": "slow left"},
                "strength": 0.6,
            },
            "init_image_hash": "abc123",
            "reference_asset_ids": [reference_one, reference_two],
            "metadata": {
                "regression": "e2e-no-regen",
                "expected_contract": "second-identical-request-reuses-exact-asset",
            },
        }

    def _wait_for_api(self) -> None:
        self._step(f"Waiting for API health at {self.api_base_url}/health")
        deadline = time.time() + self.args.health_timeout_seconds
        last_error: str | None = None
        while time.time() < deadline:
            try:
                payload = self._read_json(f"{self.api_base_url}/health")
                if payload.get("status") == "ok":
                    return
                last_error = json.dumps(payload, sort_keys=True)
            except (HTTPError, URLError, ValueError) as exc:
                last_error = str(exc)
            time.sleep(1)
        raise NoRegenFailure(
            "API health check did not become ready before timeout. "
            f"Checked {self.api_base_url}/health for {self.args.health_timeout_seconds} seconds. "
            f"Last error: {last_error}"
        )

    def _api_json(
        self,
        method: str,
        path: str,
        body: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.request_counter += 1
        headers = {
            "X-Actor-Id": self.args.actor_id,
            "X-Request-Id": f"e2e-no-regen-{self.request_counter:03d}",
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
            raise NoRegenFailure(
                f"API request failed for {method} {path} with HTTP {exc.code}. "
                f"Response body: {response_body}"
            ) from exc
        except URLError as exc:
            raise NoRegenFailure(
                f"API request failed for {method} {path}. Could not reach {self.api_base_url}: {exc}"
            ) from exc
        if not isinstance(payload, dict):
            raise NoRegenFailure(
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
            "Expected required Docker Compose service to be running before the regression check.",
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
                self._env_setting("POSTGRES_USER") or "contentlab",
                "-d",
                self._env_setting("POSTGRES_DB") or "contentlab",
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

    def _postgres_int(self, sql: str) -> int:
        rows = self._postgres_query(sql)
        if len(rows) != 1:
            raise NoRegenFailure(
                f"Expected one scalar row from Postgres query, got {rows}. SQL: {sql}"
            )
        try:
            return int(rows[0])
        except ValueError as exc:
            raise NoRegenFailure(
                f"Expected an integer scalar from Postgres query, got {rows[0]!r}. SQL: {sql}"
            ) from exc

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
        step: str,
    ) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            stderr = completed.stderr.strip()
            stdout = completed.stdout.strip()
            raise NoRegenFailure(
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
            raise NoRegenFailure(f"Missing required command on PATH: {name}")

    @staticmethod
    def _assert_true(condition: bool, message: str, *, context: Mapping[str, Any]) -> None:
        if not condition:
            raise NoRegenFailure(f"{message} Context: {json.dumps(dict(context), sort_keys=True)}")

    @staticmethod
    def _assert_equal(
        *,
        actual: str,
        expected: str,
        label: str,
        context: Mapping[str, Any],
    ) -> None:
        if actual != expected:
            raise NoRegenFailure(
                f"Unexpected {label}: expected {expected!r}, got {actual!r}. "
                f"Context: {json.dumps(dict(context), sort_keys=True)}"
            )

    @staticmethod
    def _sql_literal(value: str) -> str:
        return value.replace("'", "''")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Prove that two identical asset-resolution requests only record one provider "
            "submission and that the second request reuses the ready asset exactly."
        )
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
    parser.add_argument(
        "--actor-id",
        default="operator:e2e-no-regen",
        help="Actor header used for API requests.",
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
    try:
        NoRegenRunner(args).run()
    except NoRegenFailure as exc:
        print(f"\nNo-regeneration regression failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
