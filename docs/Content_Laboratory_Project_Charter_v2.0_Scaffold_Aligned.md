# Content Laboratory — Project Charter v2.0 (Scaffold-Aligned Master Charter)

**Owner:** Ryan  
**Date:** 18 March 2026  
**Status:** Authoritative working charter  
**Scope:** Monorepo scaffold baseline → build-ready MVP Reel Factory → launch hardening  
**Supersedes:** Project Charter v1.2 (FULL Superset)

---

## 0. Document purpose

This document is the single working charter for Content Laboratory. It replaces the older charter language that no longer matched the current repository scaffold and reconciles four things into one coherent source of truth:

1. the original product vision for an adaptive, multi-agent content system;
2. the current codebase scaffold that actually exists in the repository;
3. the locked stack and architecture decisions already made for v1; and
4. the practical build contract needed to implement the backlog cleanly on top of the current repo.

This charter is intentionally explicit about **what already exists**, **what is required next**, and **what is deferred** so that engineering, planning, and AI-assisted implementation all operate against the same baseline.

---

## 1. Executive summary

Content Laboratory is a **local-first, monorepo-based reel production system** whose primary output is a **ready-to-post package** for Instagram-style vertical video content.

The system is not conceived as “an AI that posts content.” It is conceived as an **adaptive content organism** that:

- observes what is working,
- forms hypotheses,
- generates concepts and variants,
- reuses or mutates assets intelligently,
- assembles final reels,
- quality-checks them,
- packages them for posting,
- and learns from subsequent performance.

The repository already contains the approved scaffold for this system. The scaffold is not yet feature-complete, but it establishes the real implementation boundaries that all new work must follow:

- **API:** FastAPI
- **Workflow orchestration:** Prefect 2
- **Execution queue:** Dramatiq + Redis
- **Database:** Postgres 16 + pgvector
- **Object storage:** MinIO locally, S3-compatible in production
- **Web app:** Next.js 15
- **Python packaging:** Poetry per app/package
- **Node packaging:** pnpm workspace
- **Core v1 video provider:** Runway API using `gen4.5`
- **MVP posting model:** human approval and human posting, not autonomous posting

The scaffold currently implements only a starter slice of this architecture. The purpose of this charter is to define the full build target **without pretending the current scaffold already implements it**.

---

## 2. Product vision and philosophy

### 2.1 Core philosophy

The system exists to generate content that compounds performance over time. It must balance two truths:

- virality is non-linear and partially stochastic; and
- compounding outcomes require disciplined memory, policy, and reuse.

The operating philosophy is therefore:

- **explore creatively** when the system needs discovery;
- **exploit what works** when evidence is strong;
- **mutate intelligently** when a prior concept or asset should be refreshed rather than fully regenerated; and
- allow controlled **chaos** when the portfolio needs novel probes.

This is why the product is built as a **multi-role system** rather than a single monolithic model call. Strategy, concepting, asset resolution, editing, QA, packaging, and policy all need distinct responsibilities even if some are implemented by the same LLM provider underneath.

### 2.2 Product promise

The promise of the MVP is simple:

> Given a page, a policy state, and a budget, the system can produce a small but reliable flow of ready-to-post reels packages with provenance and anti-repetition controls.

### 2.3 Product form

The product is a **reel factory** first and an **intelligence system** second.

That means the first shipping milestone is not “perfect prediction of virality.”  
It is:

- dependable package generation,
- deterministic reuse of expensive assets,
- policy-driven variation,
- and a clean operational path from trigger to deliverable.

Ingestion, clustering, scoring, and adaptive learning are important, but they are built on top of that factory.

---

## 3. Problem statement

The core operating problems this system addresses are:

1. **AI content generation is expensive** if every reel is generated from scratch.
2. **Repeated output becomes visibly stale** unless prior assets and concepts are tracked and controlled.
3. **Manual content ops do not scale** across multiple pages or niches.
4. **Creative generation without feedback loops drifts** into generic output.
5. **Trend following without policy** leads to overfitting and fatigue.
6. **A production system needs operational reliability** as much as it needs creative quality.

The system must therefore combine content intelligence, asset memory, workflow orchestration, and deterministic packaging in one coherent build.

---

## 4. Coherence locks and non-negotiable decisions

The following decisions are locked for v1 and remove ambiguity across backlog, code, and architecture.

### 4.1 Repo and implementation locks

- The current repository scaffold is the implementation baseline.
- All new work must fit the existing monorepo shape rather than invent a parallel structure.
- Python apps and Python domain packages remain Poetry-based.
- The web app remains in the pnpm workspace.

### 4.2 Runtime locks

- **FastAPI** is the only HTTP API framework for v1.
- **Prefect 2** is the only workflow orchestrator for v1.
- **Dramatiq + Redis** is the only queue and worker mechanism for v1.
- **Postgres 16 + pgvector** is the source of truth for operational and vector data.
- **MinIO** is the local object store and the canonical stand-in for S3.
- **FFmpeg** is the deterministic editing/export engine.

### 4.3 Provider locks

- AI video generation in v1 is **Runway API only**.
- The model lock for v1 is **`gen4.5`**.
- Future provider adapters are allowed by design but are out of the MVP implementation path unless explicitly approved.

### 4.4 Product boundary locks

- MVP output is a **ready-to-post package**, not an autonomous posting robot.
- Human approval and human posting remain the default boundary in MVP.
- The system must still be useful even if competitor ingestion is unavailable or degraded.
- Asset Registry and anti-repetition are first-class requirements, not optional enhancements.

### 4.5 Reliability locks

- Expensive external actions must be idempotent.
- Asset resolution must be deterministic for equivalent inputs.
- Package completeness is a hard gate, not a best-effort output.
- All stateful background execution must be observable through runs, tasks, and logs.

---

## 5. What exists today in the scaffold

This section describes the real repository baseline as of the current scaffold.

### 5.1 Apps that exist

- `apps/api` — FastAPI service
- `apps/worker` — Dramatiq worker service
- `apps/orchestrator` — Prefect flow service
- `apps/web` — Next.js admin UI
- `packages/shared/py` — shared Python settings, logging, error models
- `packages/shared/ts` — shared TypeScript package

### 5.2 Domain package directories that exist

The repository also includes the following Python package directories for domain expansion:

- `packages/core`
- `packages/auth`
- `packages/storage`
- `packages/assets`
- `packages/creative`
- `packages/editing`
- `packages/features`
- `packages/ingestion`
- `packages/intelligence`
- `packages/outbox`
- `packages/qa`
- `packages/runs`

These currently act as scaffolded placeholders and extension points. Their existence is part of the repo contract even where feature implementation is still to come.

### 5.3 Infra that exists

The scaffold already defines local infrastructure for:

- Postgres
- Redis
- MinIO
- MinIO bucket initialisation
- app Dockerfiles for API, worker, and orchestrator

### 5.4 Engineering controls that exist

The repo already includes:

- CI workflow
- linting
- formatting
- typing
- tests
- contributing rules
- AI rules
- scaffold verification scripts
- local run documentation
- worktree workflow support

### 5.5 Current implemented code baseline

The scaffold currently implements a **starter slice**, not the full product:

- API exposes health/error handling and starter models/schemas
- worker contains a starter Dramatiq actor
- orchestrator contains an example Prefect flow
- database migration currently provisions starter tables:
  - `assets`
  - `runs`
  - `run_assets`
  - `outbox_events`

This means the repository is **structurally correct but functionally incomplete**.  
This charter does not assume that the wider target schema or endpoint surface has already been coded.

---

## 6. Charter scope

### 6.1 In scope

This charter governs the build of:

- the reel factory MVP;
- the supporting operational platform around it;
- the anti-repetition and asset memory kernel;
- the page, reel, and package lifecycle;
- the local-first development workflow;
- and the launch-ready hardening path.

### 6.2 Explicitly in scope for MVP

The MVP must be able to:

1. register pages and page policy;
2. create reel families and concrete reel variants;
3. plan, generate, edit, QA, and package a reel;
4. resolve whether assets should be reused, transformed, regenerated, or blocked;
5. store all artifacts and provenance;
6. notify operators when packages are ready or failed;
7. support manual triggering and scheduled triggering;
8. support human approval and human posting;
9. record posting metadata and later performance snapshots when available; and
10. enforce basic budget and anti-repetition controls.

### 6.3 Out of scope for MVP

The following are deferred unless explicitly approved as launch-plus work:

- full autonomous posting
- broad multi-provider video generation in production
- fully automated competitor scraping at scale
- advanced self-optimising policy loops without guardrails
- complex monetisation intelligence
- multi-tenant billing systems
- enterprise-grade SSO as a required MVP dependency

---

## 7. Goals, success criteria, and definition of done

### 7.1 Primary goal

The primary goal is to ship a **working, reliable reel factory** on the current scaffold that can produce at least a modest but repeatable flow of high-quality deliverables.

### 7.2 MVP success criteria

The MVP is successful when all of the following are true:

- the system can produce **at least 3 ready-to-post reels packages per day** across the initial portfolio under normal operating conditions;
- every successful reel output includes the required package artifacts;
- expensive asset generation is not repeated for equivalent generation requests;
- the system blocks or transforms content when repetition risk is too high;
- a human operator can trigger, review, and mark outputs as posted;
- runs and failures are visible and diagnosable;
- the build runs cleanly on the existing repo scaffold and local stack.

### 7.3 Definition of done for the MVP production slice

The MVP production slice is done only when:

1. the end-to-end path from trigger to package is implemented;
2. the package contract is satisfied on every successful run;
3. policy and asset reuse decisions are persisted;
4. all major state transitions are observable;
5. tests cover the critical deterministic contracts;
6. the system can be run locally on the scaffold without architecture exceptions or one-off hacks; and
7. the backlog can continue on top of the codebase without redefining the repo model again.

---

## 8. Output contract

Every successful generated reel must produce a **ready-to-post package**.

### 8.1 Required artifacts

At minimum:

- `final_video.mp4`
- `cover.png`
- `caption_variants.txt`
- `posting_plan.json`
- `provenance.json`

### 8.2 Optional artifacts

Where available:

- hashtags
- pinned comment suggestions
- alt text
- package manifest
- keyframes or preview images

### 8.3 Hard output rules

- final video must target vertical social format, with 1080 × 1920 as the default output size;
- package output must be written to object storage with persistent URIs;
- provenance must be sufficient to explain how the output was made;
- package creation is not complete until all required files are written and verified.

---

## 9. Repo-native monorepo contract

The chartered repository shape is the one that already exists in the scaffold.

```text
content-lab/
  apps/
    api/
    orchestrator/
    web/
    worker/
  docs/
  infra/
  packages/
    assets/
    auth/
    core/
    creative/
    editing/
    features/
    ingestion/
    intelligence/
    outbox/
    qa/
    runs/
    shared/
      py/
      ts/
    storage/
  scripts/
  .github/
  README.md
  CONTRIBUTING.md
  AGENTS.md
  package.json
  pnpm-workspace.yaml
```

### 9.1 Repo rules

- new feature work must extend this structure rather than replacing it;
- cross-cutting shared Python code belongs in `packages/shared/py`;
- cross-cutting shared TypeScript types or utilities belong in `packages/shared/ts`;
- domain logic should be added to the existing package namespaces rather than creating random top-level folders;
- Docker and environment orchestration remain under `infra/`;
- developer instructions remain under `docs/`.

### 9.2 Scaffold compatibility note

The repo contains compatibility scripts for scaffold verification expectations. These are implementation support utilities, not a separate architecture. The authoritative repo shape remains the one above.

---

## 10. Service architecture

### 10.1 API service — `apps/api`

The API is the authoritative HTTP boundary for the system. Its responsibilities are:

- authentication and authorisation
- CRUD for pages, reels, assets, runs, and policy
- manual run triggering
- retrieval of operational state
- exposure of package and artifact metadata
- validation of all user-facing inputs
- consistent error models

The API must remain thin in orchestration terms. It should trigger workflows and record intent, not execute the full production pipeline inline.

### 10.2 Orchestrator service — `apps/orchestrator`

The orchestrator owns:

- scheduled workflows
- dependency graph sequencing
- high-level retries policy
- named production flows
- operational coordination between planning, generation, editing, QA, and packaging

Prefect is the source of truth for workflow structure, but not the queue implementation itself.

### 10.3 Worker service — `apps/worker`

The worker owns execution of discrete background tasks, including:

- provider calls
- feature extraction
- asset transformation
- FFmpeg editing and export
- QA checks
- package assembly
- outbox dispatch
- integrity checks

Dramatiq workers must remain idempotent and retry-safe.

### 10.4 Web service — `apps/web`

The web app is the operator-facing UI. MVP expectations are pragmatic:

- page list and page details
- reel family and reel status views
- run visibility
- package visibility
- approval and mark-posted actions
- policy controls within approved bounds

The web app is useful operationally but is not allowed to force architecture changes on the backend.

---

## 11. Domain package responsibilities

The existing package directories form the intended domain boundaries.

### 11.1 `packages/core`

Common domain primitives, enums, canonical models, and shared business rules that are not specific to a single subsystem.

### 11.2 `packages/auth`

Auth helpers, RBAC models, session/key handling, and route-level authorisation support.

### 11.3 `packages/storage`

Object storage abstractions, URI conventions, checksum handling, package writing, and integrity checks.

### 11.4 `packages/assets`

Asset Registry logic, AssetKey canonicalisation, similarity lookups, mutation recipes, and asset usage tracking.

### 11.5 `packages/creative`

Concept planning, hook generation, script assembly, creative brief shaping, and persona-aware text generation.

### 11.6 `packages/editing`

Deterministic reel assembly, FFmpeg templates, overlays, beat sync, render presets, and export handling.

### 11.7 `packages/features`

Feature definitions and extractors for content analysis and downstream scoring.

### 11.8 `packages/ingestion`

Public metadata ingestion, page/reel ingestion adapters, and later audio trend ingestion.

### 11.9 `packages/intelligence`

Pattern discovery, scoring, time-decay logic, policy suggestions, and later model-assisted decision layers.

### 11.10 `packages/outbox`

Notification events, dispatch policies, retries, and downstream operational notifications.

### 11.11 `packages/qa`

Formatting checks, policy conformance checks, repetition risk checks, and packaging gate logic.

### 11.12 `packages/runs`

Run state helpers, task state conventions, idempotency utilities, and execution audit support.

### 11.13 `packages/shared/py`

Shared settings, logging, common errors, and other cross-app Python utilities already used by API, worker, and orchestrator.

### 11.14 `packages/shared/ts`

Shared TypeScript types/utilities for the web app and future UI-domain coordination.

---

## 12. Functional system modules

### 12.1 Ingestion layer — “eyes and ears”

The ingestion layer exists to capture what is working in the market and on owned pages.

Inputs may include:

- reel metadata
- engagement counts
- saves, shares, comments, likes, and view counts where available
- posting time
- early view velocity
- visible loop-rate proxies
- observed hook styles in the first 1–2 seconds
- caption structures
- audio identifiers and trend crossover signals
- visible content patterns
- later performance snapshots from owned pages

Important boundary:

- competitor signals are public-signal only by default;
- richer internal signals are available only for owned pages where lawful and operationally available.

The system must be able to function without full ingestion coverage. Ingestion strengthens the intelligence loop but is not allowed to become a hard dependency for package generation.

### 12.2 Virality dataset and feature store

The system will maintain a structured representation of observed and generated content, including:

- page identity
- ownership type
- concept family
- hook type
- audio choice
- visual structure
- posting context
- growth/performance signals
- derived features
- outcome score

This dataset is the substrate for later scoring and policy tuning, but it must be grounded in the canonical reel and asset data model rather than in disconnected spreadsheets or ad hoc files.

### 12.3 Intelligence engine — “the brain”

The intelligence layer is responsible for:

- finding patterns;
- separating emerging patterns from exhausted ones;
- identifying when a creative family should be exploited, mutated, or cooled down;
- and shaping policy suggestions.

The chartered scoring direction remains the original conceptual model:

> **Virality Score = Novelty × Pattern Strength × Emotional Pull × Platform Bias × Creator Consistency**

This is not required to ship as a mathematically perfect model in phase 1, but it is the conceptual north star the intelligence layer should converge towards.

Phase progression:

- Phase 1: rule-based and heuristic policy
- Phase 2: light feature extraction and similarity
- Phase 3: clustering and scoring
- Phase 4: guarded adaptive policy tuning

Methods that may be used later include:

- clustering such as HDBSCAN or K-means;
- time-decay weighting;
- feature-importance style explanations;
- novelty scoring;
- trend saturation logic.

### 12.4 Creative generation layer — “the artist”

The creative layer must support distinct responsibilities:

- selecting operating mode;
- generating concept briefs;
- creating hooks and text overlay structure;
- generating caption variants;
- deciding when to reuse prior ideas and when to introduce variation.

Core roles conceptually include:

- Director / Planner
- Script / Hook Generator
- Trend Adapter
- Asset Builder
- Editor
- QA gate

These roles can be implemented as separate modules and prompts rather than separate deployed services.

### 12.5 Asset Registry and reuse engine — “the anti-repetition kernel”

This is a hard requirement for the product.

The Asset Registry must answer:

- have we already generated this exact asset request?
- is there an existing near-equivalent asset that can be reused?
- should an old asset be reused with transformation?
- should generation be blocked because repetition risk is too high?
- should the system pay for a fresh generation?

The registry must therefore support:

- exact memoisation via a canonical AssetKey hash;
- near-duplicate detection via hashes and embeddings over time;
- usage history;
- recency and cooldown logic;
- mutation recipes;
- provenance tracking;
- and deterministic resolution outcomes.

### 12.6 Editing and composition

Editing is deterministic production logic, not a loose artistic side-effect.

It must support:

- fixed social format exports
- overlays and text timing
- assembly from raw and derived assets
- audio handling
- intros/outros if used
- consistent export presets
- and generation of the final package assets

### 12.7 QA gate

QA must check at least:

- format conformance
- package completeness
- asset availability
- policy compliance
- repetition risk
- persona/constraint compliance
- and basic failure conditions before packaging is finalised

### 12.8 Human review and posting boundary

MVP posting remains human-driven. The system must prepare a postable package and enough metadata to make the posting step efficient, but posting itself remains outside the autonomous scope unless a later phase explicitly authorises adapters and permissions.

### 12.9 Feedback loop

The long-term system compounds by learning from outcomes. That loop includes:

- recording posted content identity;
- recording later metrics;
- updating feature and scoring datasets;
- adjusting policy state within bounds;
- and learning where mutation or freshness is required.

---

## 13. Mode controller and policy state

The system operates under four policy modes:

- **exploit** — push proven patterns harder
- **explore** — test adjacent concepts or lightly evidenced patterns
- **mutation** — reuse a working family with deliberate transformation
- **chaos** — inject controlled novelty

Policy state should capture at least:

- mode ratios
- budget guardrails
- similarity thresholds
- cooldown windows
- family reuse limits
- freshness rules
- optional page-level overrides

Policy updates must be persisted, auditable, and bounded.

---

## 14. AI provider and model strategy

### 14.1 Video generation

For v1:

- provider: **Runway**
- model: **`gen4.5`**

This is a lock, not a suggestion.

### 14.2 LLM usage

LLM usage should remain provider-agnostic at the interface level where reasonable, but the product does not require a heavyweight multi-provider abstraction before the core reel factory is functioning.

### 14.3 Provider boundary design

External providers should be wrapped behind internal adapters so that:

- request canonicalisation is stable;
- provider-specific parameters do not leak into unrelated layers;
- retries and idempotency can be enforced;
- and future provider swaps do not force a database redesign.

---

## 15. Data model

This charter distinguishes between:

1. the **starter schema currently implemented in the scaffold**, and
2. the **canonical phase-1 schema required to build the real MVP**.

### 15.1 Current scaffold schema

The existing Alembic baseline already defines:

#### `assets`
Starter asset record for stored/generated items, including storage key, metadata, embedding, and created time.

#### `runs`
Starter record of execution runs, including name, status, config, result, and timestamps.

#### `run_assets`
Join table between runs and assets.

#### `outbox_events`
Starter event table for later dispatch/notification patterns.

These tables are valid scaffold anchors and should be evolved rather than discarded without cause.

### 15.2 Canonical phase-1 schema

The phase-1 MVP requires the following broader entities.

#### Auth and tenancy

- `orgs`
- `users`
- `org_memberships`
- `api_keys`

#### Pages and content

- `pages`
- `reel_families`
- `reels`
- `reel_metrics`
- `audio`
- `features`

#### Asset Registry

- `asset_families`
- `assets`
- `asset_gen_params`
- `asset_usage`

#### Experiments and policy

- `experiments`
- `policy_state`

#### Orchestration and reliability

- `runs`
- `tasks`
- `provider_jobs`
- `outbox_events`
- `audit_log`
- `storage_integrity_checks`

### 15.3 Canonical entity meanings

#### Pages

Represents an Instagram page or comparable content account in the portfolio. Pages may be owned or competitor pages.

#### Reel families

Represents a concept or hypothesis instance. Families allow the system to express A/B/C style variants without losing shared context.

#### Reels

Represents a concrete content variant or an observed reel. Generated reels move through a lifecycle; observed reels remain observational records.

#### Assets

Represents raw or derived media used or created by the system. Assets must support content hashes, provenance, storage URIs, and similarity metadata.

#### Runs and tasks

Runs represent higher-level workflow executions. Tasks represent idempotent substeps with clear status and retry behaviour.

#### Provider jobs

Tracks the lifecycle of external provider work such as Runway submissions and polling.

#### Policy state

Stores operating mode ratios, thresholds, limits, and page- or org-scoped controls.

### 15.4 Constraints and uniqueness

The system must enforce at minimum:

- unique AssetKey semantics for exact memoisation;
- unique content checksum semantics where required;
- unique external media identity per org when known;
- unique task idempotency keys;
- and ordered outbox processing with retry support.

### 15.5 Retention defaults

Recommended defaults:

- ready-to-post packages: retained indefinitely by default;
- raw generated assets: retained for at least 180 days since last use;
- derived assets: retained for at least 90 days since last use;
- observed competitor reel binaries: retained for up to 365 days unless policy changes;
- run/task logs: retained for at least 90 days, longer for failures;
- audit logs: retained for 2 years or longer where needed.

---

## 16. API contract direction

### 16.1 Current implemented API baseline

The scaffold currently exposes a starter API with:

- `/health`
- shared error response structure
- starter schemas around assets, runs, and outbox events

### 16.2 Required MVP API surface

The API must grow to support at least:

- auth/session or API-key access
- page creation and listing
- reel family creation and retrieval
- reel creation and retrieval
- reel processing trigger
- mark-posted action
- run creation and run retrieval
- asset retrieval and asset resolution
- policy retrieval and update

### 16.3 API design rules

- route contracts must map cleanly to the canonical data model;
- request validation must be strict;
- enums must be explicit;
- conflict states must produce proper conflict errors;
- and mutating actions must be auditable.

---

## 17. Workflow architecture

### 17.1 Core production flows

The following named flows are required:

1. `daily_reel_factory`
2. `process_reel`

### 17.2 Core execution sequence

The canonical generated reel path is:

1. trigger
2. plan
3. asset resolution
4. generation or transform
5. editing
6. QA
7. package
8. notify
9. optional human posting
10. later metrics ingestion

### 17.3 Phase-2 and later flows

The following flows are planned after the MVP factory is stable:

- `ingest_observed_reels`
- `extract_features`
- `cluster_patterns`
- `score_candidates`
- `policy_tune`
- `provider_job_sweeper`
- `outbox_dispatcher`
- `storage_integrity_check`
- `retention_cleanup`
- `budget_guardrail_enforcer`

### 17.4 Run and task philosophy

Runs should remain coarse and human-meaningful.  
Tasks should remain fine-grained, idempotent, observable, and retry-safe.

---

## 18. Asset Registry specification

### 18.1 Exact memoisation

The system must canonicalise generation parameters into a stable AssetKey.  
Equivalent generation requests must resolve to the same AssetKey.

### 18.2 Near-duplicate detection

The system should progressively support:

- perceptual hashes;
- embeddings;
- similarity thresholds;
- cooldown windows;
- and usage frequency controls.

### 18.3 Resolution outcomes

Asset resolution should be able to return one of four outcomes:

- `reuse_exact`
- `reuse_with_transform`
- `generate`
- `blocked`

### 18.4 Mutation recipes

Mutation is a first-class path, not an edge case. It may include:

- reframing
- cropping or camera motion changes
- timing changes
- audio changes
- overlay treatment changes
- colour treatment changes
- sequence recomposition
- or other deterministic transform policies

### 18.5 Provenance

The system must always be able to explain:

- what inputs were used,
- what prompts/params were used,
- what source assets were reused,
- what transforms were applied,
- and what package was emitted.

---

## 19. Object storage contract

The canonical storage model is S3-compatible and must work on MinIO locally.

Recommended object layout:

```text
content-lab/
  assets/
    raw/{asset_id}/...
    derived/{asset_id}/...
  reels/
    packages/{reel_id}/final_video.mp4
    packages/{reel_id}/cover.png
    packages/{reel_id}/caption_variants.txt
    packages/{reel_id}/posting_plan.json
    packages/{reel_id}/provenance.json
    packages/{reel_id}/package_manifest.json
  logs/
    runs/{run_id}/...
    tasks/{task_id}/...
```

Rules:

- packages must have stable URIs;
- object metadata should support integrity and traceability;
- content checksums must be stored in the database where required;
- storage integrity checks should be runnable independently of content generation.

---

## 20. Local-first environment and runtime

### 20.1 Local dev baseline

The repo is designed to run locally with:

- Docker Compose for infra
- Python 3.11
- Poetry
- Node 24+
- pnpm 9
- FFmpeg

### 20.2 Local infra services

The local stack must include:

- Postgres
- Redis
- MinIO
- MinIO bucket creation/init

### 20.3 Environment configuration

Shared settings already expect:

- database URL
- Redis URL
- MinIO endpoint and bucket
- MinIO credentials
- Runway API key

Environment loading should continue to work both in local checkout contexts and container contexts.

### 20.4 Production migration path

Once stable locally, the architecture should migrate without rewriting core logic:

- MinIO → S3
- local Postgres → managed Postgres
- local Redis → managed Redis
- local containers → orchestrated runtime
- local observability → managed telemetry stack

---

## 21. Security and governance

### 21.1 Authentication

MVP may use simple auth and/or API keys, but keys must be hashed at rest and revocable.

### 21.2 Authorisation

The product should support org-scoped RBAC with roles such as:

- owner
- admin
- operator
- reviewer
- readonly

### 21.3 Secrets handling

- secrets must never be committed;
- `.env` is acceptable for local MVP operation;
- secret values must be redacted from logs;
- managed secrets are the launch-ready target.

### 21.4 Audit and traceability

Mutating actions, high-cost provider calls, packaging completion, and delete/destructive actions should be audit logged.

### 21.5 Input hardening

- strict schema validation
- bounded prompt lengths
- MIME and size controls on uploads
- URI restrictions to avoid unsafe fetch behaviour
- no arbitrary remote execution patterns through user input

---

## 22. Engineering operating rules

The charter inherits the repo’s engineering controls.

### 22.1 Mandatory quality gates

All meaningful code changes must pass:

- format
- lint
- typecheck
- tests

### 22.2 Determinism requirements

- expensive external calls require idempotency keys;
- asset canonicalisation must be stable;
- ordering-sensitive behaviour should be explicit;
- bug fixes should add regression coverage.

### 22.3 AI-assisted implementation rules

AI-generated work must:

- stay within the repo architecture;
- touch the minimum necessary files;
- preserve output contracts;
- keep secrets out of the repo;
- and include validation and tests.

### 22.4 Documentation obligations

If behaviour changes, docs must be updated alongside the code.  
If migrations are introduced, migration notes must accompany the change.

---

## 23. Roadmap

### Phase 1 — Reel Factory MVP (must ship first)

Build the production slice that turns a concept into a ready-to-post package on the current scaffold:

- page and policy data model
- reel family and reel lifecycle
- Runway adapter
- Asset Registry exact memoisation
- reuse-with-transform path
- deterministic editor templates
- QA gate
- package writer
- outbox notifications
- operator-visible run/reel/package state

### Phase 2 — Ingestion and feature extraction

Add observational intelligence inputs:

- public competitor ingestion where permitted
- owned-page post/metrics ingestion
- feature extraction
- audio and caption pattern capture
- first repetition heuristics using hashes and usage history

### Phase 3 — Pattern discovery and scoring

Add intelligence depth:

- clustering
- emerging vs dying pattern logic
- novelty and saturation scoring
- explainable candidate scoring
- stronger similarity controls using pgvector at meaningful volume

### Phase 4 — Feedback loop and guarded tuning

Add adaptive controls:

- update policy from outcomes
- tune mode ratios within bounds
- learn transform effectiveness
- page-specific adaptation
- portfolio-level shared intelligence

### Phase 5 — Launch hardening and expansion

Add post-MVP scale features:

- richer web dashboard
- approval workflows
- optional autopost adapters
- stronger RBAC
- managed secrets/infra
- deeper observability
- optional provider expansion

---

## 24. Risks and mitigations

### 24.1 Provider volatility and rate limits

Mitigation: queue backpressure, retries, budget guardrails, and provider job tracking.

### 24.2 Duplicate spend on generation

Mitigation: AssetKey uniqueness, deterministic canonicalisation, idempotent tasks, and usage-aware reuse.

### 24.3 Repetition fatigue

Mitigation: cooldown windows, similarity thresholds, family reuse limits, and mutation recipes.

### 24.4 Ingestion fragility or platform restrictions

Mitigation: do not make ingestion a prerequisite for package generation; design for degraded-but-useful operation.

### 24.5 Ghost assets or broken packages

Mitigation: storage checksums, integrity verification, staged-to-ready transitions, and package completeness gates.

### 24.6 Security leaks

Mitigation: secret redaction, scoped access, private object storage, audit logs, and managed secrets in later phases.

### 24.7 Architectural drift

Mitigation: this charter, the scaffold verification path, and a backlog that maps directly to the actual repo shape.

---

## 25. Explicit non-goals and anti-patterns

The following are not acceptable implementation patterns under this charter:

- inventing a second repo layout beside the current scaffold;
- replacing Prefect, Dramatiq, or FastAPI without an explicit architecture decision;
- bypassing the Asset Registry for expensive generation paths;
- writing outputs to ad hoc local folders as the authoritative product output;
- treating autonomous posting as an MVP dependency;
- or using a “single giant magic agent” in place of explicit responsibilities and persistence.

---

## 26. Final alignment statement

This charter is intentionally designed to be both:

1. **ambitious enough** to preserve the full intended product shape; and
2. **strict enough** to stay in line with the real scaffold already present in the repository.

Therefore, the authoritative reading is:

- the current scaffold is the implementation baseline;
- the reel factory MVP is the first hard shipping target;
- the wider intelligence system is phased on top of that baseline;
- and all future backlog items must map cleanly to this repo-native charter without redefining the architecture again.

---

## 27. Acceptance checklist for backlog alignment

A backlog item is aligned to this charter only if it satisfies all of the following:

- it fits the existing monorepo structure;
- it does not contradict the locked runtime choices;
- it advances the reel factory, asset registry, operational platform, or approved later-phase intelligence path;
- it respects the output contract;
- it preserves determinism and idempotency where required;
- and it can be implemented without re-opening already locked architecture decisions.

---

## 28. Charter sign-off intent

This document is intended to function as the new master charter for planning, backlog correction, and implementation on the current Content Laboratory repository scaffold.