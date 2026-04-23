# Semantic reel regression lane (bad-but-valid)

This is a **small, fast** regression surface for reels that are *technically* presentable (valid script
shapes, overlays, timing) but **semantically hollow or manipulative** — the main false-positive class
for “ready to review” if the `semantic_script` gate regresses.

## What it is (and is not)

- **In scope:** `content_lab_qa.evaluate_semantic_script` only, plus JSON **bad-reel** fixtures under
  `packages/qa/tests/fixtures/bad_reels/` where we declare a `semantic_script` block in
  `expected_outcomes.json`.
- **Out of phase-2+:** no format/FFprobe, no packaging, no provider jobs, no alignment-heavy flows
  beyond what the JSON bundles already carry for other tests.
- **Relationship to alignment tests:** `tests/test_bad_reel_semantic_regression.py` covers
  **alignment** drift. This lane covers the **script gate** so both stay independent.

## Where tests live

| Path | Role |
|------|------|
| `packages/qa/tests/semantic_reel_regression/` | Inline “nonsense class” scripts + JSON contract tests |
| `packages/qa/tests/fixtures/bad_reels/` | Versioned JSON cases + `expected_outcomes.json` |

## How CI and `py_check` run it

`scripts/py_check.sh` / `scripts/py_check.ps1`:

1. For `packages/qa` only, the main `pytest` sweep uses `--ignore=tests/semantic_reel_regression`
   so the lane is explicit in logs.
2. Immediately after the monorepo loop, they run  
   `cd packages/qa && poetry run pytest -q tests/semantic_reel_regression`.

## Local CI-equivalent (QA only)

```bash
cd packages/qa
poetry install
poetry run pytest -q --ignore=tests/semantic_reel_regression
poetry run pytest -q tests/semantic_reel_regression
```

Or from the repo root (full Python gate): `bash ./scripts/py_check.sh`.

## Pytest marker

Tests are marked `semantic_reel_regression` (see `packages/qa/pyproject.toml`). Optional filter:

```bash
cd packages/qa && poetry run pytest -q -m semantic_reel_regression
```
