from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = ROOT / "debug-b60655.log"
SESSION_ID = "b60655"
RUN_ID = "pre-fix"


def emit(hypothesis_id: str, location: str, message: str, data: dict[str, object]) -> None:
    payload = {
        "sessionId": SESSION_ID,
        "runId": RUN_ID,
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data,
        "timestamp": int(__import__("time").time() * 1000),
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload) + "\n")


def main() -> None:
    ci_yml = ROOT / ".github" / "workflows" / "ci.yml"
    lockfile = ROOT / "pnpm-lock.yaml"
    py_check = ROOT / "scripts" / "py_check.sh"

    ci_content = ci_yml.read_text(encoding="utf-8")
    py_check_bytes = py_check.read_bytes()
    py_check_text = py_check_bytes.decode("utf-8", errors="replace")

    # #region agent log
    emit(
        "H1",
        "scripts/ci_debug_probe.py:32",
        "Node cache-via-pnpm lockfile precondition",
        {
            "ciCachePnpmConfigured": "cache: 'pnpm'" in ci_content or 'cache: "pnpm"' in ci_content,
            "pnpmLockExists": lockfile.exists(),
        },
    )
    # #endregion

    # #region agent log
    emit(
        "H2",
        "scripts/ci_debug_probe.py:45",
        "py_check.sh executable permission status",
        {
            "pyCheckExists": py_check.exists(),
            "osExecutableBit": bool(os.stat(py_check).st_mode & 0o111),
        },
    )
    # #endregion

    # #region agent log
    emit(
        "H3",
        "scripts/ci_debug_probe.py:57",
        "py_check.sh shebang and line-ending health",
        {
            "startsWithBashShebang": py_check_text.startswith("#!/usr/bin/env bash"),
            "containsCRLF": b"\r\n" in py_check_bytes,
        },
    )
    # #endregion

    # #region agent log
    emit(
        "H4",
        "scripts/ci_debug_probe.py:69",
        "Python CI step points at py_check.sh",
        {
            "ciRunsPyCheckScript": "./scripts/py_check.sh" in ci_content,
            "ciInstallsPoetry": "pip install poetry" in ci_content,
        },
    )
    # #endregion

    import re

    # #region agent log  -- H5: pnpm action version issues
    pnpm_action_match = re.search(r"pnpm/action-setup@(v\d+)", ci_content)
    pnpm_version_match = re.search(r"version:\s*(\S+)", ci_content.split("pnpm/action-setup")[1]) if "pnpm/action-setup" in ci_content else None
    pkg_json = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    emit(
        "H5",
        "scripts/ci_debug_probe.py:80",
        "pnpm action-setup version config",
        {
            "actionTag": pnpm_action_match.group(1) if pnpm_action_match else None,
            "actionVersionInput": pnpm_version_match.group(1) if pnpm_version_match else None,
            "packageManagerField": pkg_json.get("packageManager"),
        },
    )
    # #endregion

    # #region agent log  -- H6: untyped params in main.py
    api_main = (ROOT / "apps" / "api" / "src" / "content_lab_api" / "main.py").read_text(encoding="utf-8")
    untyped_request = "_request," in api_main and "_request:" not in api_main
    emit(
        "H6",
        "scripts/ci_debug_probe.py:95",
        "mypy strict: untyped _request parameter in main.py",
        {
            "hasUntypedRequest": untyped_request,
            "mypyStrictInApiConfig": "strict = true" in (ROOT / "apps" / "api" / "pyproject.toml").read_text(encoding="utf-8"),
        },
    )
    # #endregion

    # #region agent log  -- H7: missing ignore_missing_imports
    pyprojects = [
        "packages/shared/py/pyproject.toml",
        "apps/api/pyproject.toml",
        "apps/worker/pyproject.toml",
        "apps/orchestrator/pyproject.toml",
    ]
    missing_imports_config = {}
    for pp in pyprojects:
        content = (ROOT / pp).read_text(encoding="utf-8")
        missing_imports_config[pp] = "ignore_missing_imports" in content
    emit(
        "H7",
        "scripts/ci_debug_probe.py:115",
        "mypy ignore_missing_imports configured per project",
        {"ignoreMissingImportsSet": missing_imports_config},
    )
    # #endregion


if __name__ == "__main__":
    main()
