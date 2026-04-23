# Content-quality E2E (process_reel)

This check validates the **“good enough to review”** bar for a reel: not just that
artifacts exist, but that **semantic script QA** and **creative trace** (generator
choice, script lint, scene plan, prompt trace) are part of the terminal run output
and, in the happy path, uploaded to storage.

The script drives the same **phase-one** path used in `apps/orchestrator/tests/test_flow.py`:

- in-memory `process_reel` persistence (no Postgres)
- a **mock Runway** round-trip and FFmpeg-generated fixture media (`pass` mode)
- real `evaluate_semantic_script` and `build_creative_trace` in the live executor path

## Prerequisites

- Python 3.11, Poetry, and the orchestrator env installed: `cd apps/orchestrator && poetry install`
- **FFmpeg** on `PATH` (the harness generates a short MP4 for the fake provider clip)
- no API keys; no Docker required for this script

## Run (recommended)

From the repository root (Git Bash / Linux / macOS):

```bash
./scripts/e2e_content_quality.sh
./scripts/e2e_content_quality.sh --mode pass
./scripts/e2e_content_quality.sh --mode fail
```

From Windows (PowerShell), from repo root:

```powershell
Set-Location apps\orchestrator; poetry run python ..\..\scripts\e2e_content_quality.py --mode pass
Set-Location apps\orchestrator; poetry run python ..\..\scripts\e2e_content_quality.py --mode fail
```

## Modes

| Mode   | Intent |
|--------|--------|
| `pass` | Full `process_reel` run: reel `reel-42` ends `ready`, package manifest and package QA pass, `semantic_script.verdict` is `pass`, `creative_trace` is present, and the fake S3 store contains `creative_trace.json`. |
| `fail` | Synthetic executor forces semantic failure (weak hook / CTA-heavy script). Expects `qa_failed`, semantic `verdict` `fail` with an `incomplete_hook` finding, and a `process_reel.failed` outbox event (no “ready to review” package). |

Exit code `0` means assertions matched; non-zero on failure or missing tools (e.g. FFmpeg not found when building the pass fixture).
