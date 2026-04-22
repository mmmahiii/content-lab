# Bad-reel fixture pack (golden regression)

This directory holds **deterministic, lightweight** JSON bundles that model **known-weak reel
outputs** so semantic QA gates do not regress silently.

## Bad-output class (protected)

The primary class is **intent drift**: the creative brief / lead message says one vertical
(e.g. artisan coffee and roastery culture) while downstream artifacts were generated as if the
brief were a different topic (e.g. home solar incentives). The phase-1 alignment gate is
expected to flag this as **semantic failure** (`messaging_drift`, `asset_prompt_drift`), not as
a media **format** failure.

## What these fixtures are not

- They are **not** invalid JSON or broken schema shapes (those would fail earlier at
  validation / technical gates).
- They are **not** a replacement for model-based QA; they anchor the **first-pass deterministic**
  heuristics.

## How to use

- Load a case with `content_lab_qa.tests.fixtures.bad_reels.loader` (see `loader.py`) or read
  JSON directly.
- Expected outcomes live in `expected_outcomes.json`. **Do not weaken** required fail codes
  without an explicit product decision and test updates.

## Cross-package layout

The canonical files live here. `packages/creative/tests/fixtures/bad_reels/README.md` points
back to this directory so creative and orchestrator tests can share the same bundles without
duplicating content.
