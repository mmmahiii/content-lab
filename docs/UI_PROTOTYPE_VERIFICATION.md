# Prototype delivery and verification

Verified locally on 10 September 2026 with Node 24, pnpm 9 and installed Google Chrome. Only the frontend was started. The archived interface and Python/backend sources were not modified.

## Results

| Check | Result |
| --- | --- |
| Workspace lint (`pnpm lint`) | Passed, no lint warnings/errors |
| Workspace typecheck (`pnpm typecheck`) | Passed for web and shared TypeScript |
| Workspace tests (`pnpm test`) | Passed: 30 web tests and 4 shared TypeScript tests |
| Production build (`pnpm --filter web build`) | Passed; home prerendered, approximately 158 kB first-load JavaScript |
| Browser journeys (`pnpm --filter web test:e2e`) | Passed: 10 journeys against the production build |
| Browser traffic | No backend/API or provider requests across the journeys |
| Visual inspection | Principal workspaces, editor, partial packs, failed execution, blocked preview, read-only editor and narrow review inspected |
| Screenshot capture | No browser errors or unexpected network requests; see `outputs/prototype/inspection.json` |
| Graphify | AST update completed through the bundled runtime; graph JSON, HTML and report refreshed without LLM/provider calls |

After the final icon-navigation accessibility labels were added, the production build passed again and the principal-workspace and narrow-review browser checks were rerun successfully (2/2). The complete ten-journey suite had passed before that label-only change.

The Vite test runner emits its existing CJS API deprecation notice. It does not fail the checks. Backend routes remain in the Next application but the prototype does not invoke them; they were not integrated or operationally validated here.

## Browser coverage

The browser suite lives in [`operator-prototype.spec.ts`](../apps/web/e2e/operator-prototype.spec.ts). It covers:

1. All nine workspaces and local-only traffic.
2. Registry selection → new content → copy → pinned preview/render → QA → exact approval → downloadable handoff → manual simulated post → unavailable observations and refresh persistence.
3. Object position, replacement comparison, exact text, scene timing/reorder, immutable history, a new preview/render and parent comparison.
4. Pack planning, separate acquisition authorisation, partial fulfilment and content creation from the ready subset.
5. Unknown-outcome reconciliation, a new retry attempt that preserves the failed attempt, and its exact output review.
6. Role limits, loading, unavailable service recovery, empty workspace and corrupt storage recovery.
7. Narrow-screen review, no horizontal document overflow, keyboard skip navigation and accessible navigation names.
8. Immediate brief-to-editor navigation, immediate revision save, preserved earlier results and blocked publication from an outdated approval.
9. Original idea capture and editorial evidence carried into its brief.
10. Mandatory ingredient conflicts and invalid source intervals with visible recovery.

Focused [service tests](../apps/web/app/prototype/mock-service.test.ts) also cover atomic budget reservations, duplicate starts, provider uncertainty, failed jobs, rights/readiness, unsupported media capabilities, exact approval/copy checks, timestamp requirements, role scopes, storage failures, experiments and partial acquisition. [Timing tests](../apps/web/app/prototype/scene-timing.test.ts), [timezone tests](../apps/web/app/prototype/publication-time.test.ts) and [handoff tests](../apps/web/app/prototype/prototype-handoff.test.ts) cover the frame clock, daylight-saving ambiguity and pinned repeated asset uses.

## Screenshots and preview

Open the running UI at **http://127.0.0.1:3000**. See [startup instructions](UI_PROTOTYPE_RUN.md) if it has stopped.

The local [screenshot gallery](../outputs/prototype/index.html) contains Content, Pages, Ideas, Asset Registry, Asset packs, Scene editor, Review, Publication, Operations, Learning and example failure/permission states. Screenshot artifacts are intentionally ignored by Git and can be regenerated using the inspection script.

Representative files: [content studio](../outputs/prototype/content.png), [scene editor](../outputs/prototype/editor.png), [asset registry](../outputs/prototype/assets.png), [package review](../outputs/prototype/review.png), [failed execution](../outputs/prototype/failed-execution.png) and [narrow review](../outputs/prototype/mobile-review.png).

## Graph audit limits

The standalone Windows graphify launcher still points at an unusable Python installation. Queries and AST updates worked through the bundled runtime using local parser wheels in ignored `.venv-graphify`. A transient Windows signature-file write failure was resolved on retry. Graphify reported 17 source/configuration records producing zero nodes; these are not proof that every file is represented. Community names were refreshed from local hub labels; semantic relabelling and document/image extraction were not requested. The [source audit](UI_PROTOTYPE_AUDIT.md) remains the evidence-linked integration register.

## Review gate

The prototype is ready for workflow and information-architecture review. Real provider selection, database migrations, production permission enforcement, encoded rendering, acquisition and authorised publishing remain deferred. Approving a simulated package in this UI does not approve backend implementation; that is a separate product decision after reviewing the workflows.
