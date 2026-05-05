# Regression Guardrails

Previously fixed bugs must be protected by executable regression checks. The rule
is not "remember that someone fixed this"; the rule is "make the repo fail if it
comes back."

## Fast Historical Gate

Run the fast historical regression suite from the repo root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-regressions.ps1
```

```bash
bash scripts/verify-regressions.sh
```

This gate collects focused checks for known past failures:

| Area | Protected Failure Class |
| --- | --- |
| `packages/editing` | overlay text truncation, hook wrapping/autofit, overlay handoff and render diagnostics |
| `packages/qa` | bad-but-valid reel semantic drift, caption meta-language, overlay text fidelity |
| `packages/creative` | bad-reel fixture shape, copy-lint/script-lint guardrails |
| `apps/orchestrator` | process-reel QA wiring and saved idea-plan overlay regressions |

## Heavier Gates

Some historical fixes need infrastructure or full E2E runtime checks, so they stay
outside the fast gate:

| Command | Use When |
| --- | --- |
| `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/py_check.ps1` | broad Python package checks |
| `python scripts/e2e_no_regen.py` | no-regeneration/cost-control behavior must be verified against live local services |
| `python scripts/e2e_mvp_smoke.py` | full MVP package artifact path needs a runtime smoke |
| `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/v32_full_validation.ps1` | full validation, marker coverage, E2E, and artifact checks |

## Adding A Future Fix

When a bug is fixed:

1. Add or update the smallest regression test at the layer where the bug escaped.
2. If it is a known historical class, include that test in `scripts/verify-regressions.ps1`
   and `scripts/verify-regressions.sh`.
3. If it requires services, document the heavier command in this file instead of
   hiding it in memory or chat history.
4. In the final/PR verification notes, name the regression command that was run.
