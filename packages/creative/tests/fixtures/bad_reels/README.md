# Bad-reel fixtures (see canonical pack)

The **canonical** JSON bundles and expected-outcome manifest live in:

`packages/qa/tests/fixtures/bad_reels/`

Creative tests can load them via `loader.py` in this directory (re-exporting the shared JSON)
so the same “nonsense drift” and baseline cases are used across the creative, QA, and
orchestrator test suites without duplicating content.

**Do not copy-paste** large JSON into `packages/creative/tests/fixtures/`: that drifts. Prefer
importing the loader and reading the shared files.
