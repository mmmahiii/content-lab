# AI Rules (mandatory)

These rules exist to keep the codebase coherent, secure, and testable when using AI.

## Scope of changes
- One PR = one logical change. Avoid "drive-by" refactors.
- Do not change architecture decisions unless explicitly authorised in the task brief.

## Output contracts are sacred
- The "ready-to-post package" contract must never be broken.
- All API contracts must remain backwards compatible unless versioned.

## Safety + security
- **Never** commit secrets, tokens, API keys, cookies, or real account credentials.
- Log redaction is mandatory for any value coming from environment secrets.

## Testing expectations
- Every new endpoint: request validation + at least one unit test.
- Every new workflow step: idempotency + retries + at least one unit test.
- Any bug fix: add a regression test.

## Determinism + idempotency
- All expensive external calls must have idempotency keys.
- Asset Registry lookups must be deterministic (canonicalisation + stable hashing).

## How to work (AI prompt hygiene)
When implementing a task, always:
1. List files to touch.
2. Implement minimal change set.
3. Run: format → lint → typecheck → tests.
4. Provide a short "verification checklist" in the PR description.
