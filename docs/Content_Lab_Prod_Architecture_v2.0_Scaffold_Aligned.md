# Content Laboratory — Production Architecture v2.0 (Scaffold-Aligned Master Architecture)

**Owner:** Ryan  
**Date:** 18 March 2026  
**Status:** Authoritative working architecture  
**Scope:** Current scaffold baseline -> build-ready phase-1 Reel Factory architecture -> launch hardening  
**Supersedes:** Content Laboratory — Production Architecture v1.3 (Coherent)

---

## 0. Document purpose

This document defines the authoritative architecture for Content Laboratory in a way that matches the repository scaffold that actually exists today.

It replaces earlier architecture language that captured the intended product shape but still assumed a repo model, implementation depth, and system surface that were not fully aligned to the zip scaffold.

This architecture is designed to do five things at once:

1. preserve the intended product design for a serious multi-stage content system;
2. anchor every major decision to the current monorepo scaffold rather than to an abstract future repo;
3. distinguish clearly between the currently implemented baseline and the required phase-1 target;
4. remove ambiguity across services, packages, workflows, schemas, and output contracts; and
5. provide a direct architectural contract for backlog execution and AI-assisted coding.

The result is intentionally strict. It is ambitious enough to preserve the long-term system, but practical enough that engineering work can begin immediately on the current repository without reopening core architecture decisions.

---

## 1. Executive summary

Content Laboratory is a **local-first reel production system** that produces **ready-to-post vertical video packages** with deterministic asset reuse, provenance, policy-controlled variation, and a clear path from local development to production hardening.

The repository scaffold already locks the main implementation shape:

- `apps/api` for the FastAPI HTTP boundary;
- `apps/worker` for Dramatiq workers;
- `apps/orchestrator` for Prefect 2 flows;
- `apps/web` for the Next.js operator UI;
- `packages/shared/py` and `packages/shared/ts` as the existing shared foundations;
- domain packages under `packages/` for assets, creative, editing, QA, storage, runs, and adjacent intelligence modules;
- Alembic under `apps/api`;
- Dockerfiles under `infra`;
- Docker Compose for Postgres, Redis, and MinIO;
- Poetry per Python app/package and pnpm for the web workspace.

The architecture therefore has to be read in two layers:

1. **current scaffold baseline** — what is structurally present and partially runnable today; and
2. **required phase-1 architecture** — what must be built on top of that scaffold to reach a real MVP Reel Factory.

The current baseline is intentionally minimal. The API exposes health and shared error handling, the worker contains a starter `ping` actor, the orchestrator contains an example Prefect flow, and the initial migration only provisions starter operational tables. The system is therefore **structurally correct but functionally incomplete**.

This document defines the full architecture that closes that gap without changing the scaffold contract.

---

## 2. Architecture philosophy

The architecture is built around seven principles.

### 2.1 The package is the first product surface

The first shipping surface is not predictive intelligence. It is the ability to generate a dependable package containing the final reel, cover, caption variants, posting plan, and provenance. All architecture decisions must therefore prioritise deterministic generation, media handling, storage, packaging, and operator visibility.

### 2.2 Repo structure is part of the architecture

The architecture is not just a diagram. It includes the actual repo topology, package boundaries, migration location, Docker layout, packaging conventions, and shared utility surfaces. A design that ignores the repo scaffold is not considered aligned.

### 2.3 Determinism must exist wherever cost exists

External generation is expensive. Asset resolution, task execution, and package writing therefore need canonicalisation, hashing, idempotency, and reproducible side effects. Determinism is not a nice-to-have. It is how the system controls spend and avoids operational chaos.

### 2.4 The system must be useful under degraded intelligence

The reel factory must still function if competitor ingestion is unavailable, if scoring is still heuristic, or if clustering is not yet implemented. Intelligence deepens the system, but generation, QA, and packaging must not depend on advanced learning components being present on day one.

### 2.5 Asset memory is a platform capability

The Asset Registry is not an isolated feature. It cuts across storage, schema, workers, QA, policy, and cost control. Exact reuse, reuse-with-transform, cooldowns, and similarity checks must be reflected in the architecture at multiple layers.

### 2.6 Human approval remains the MVP boundary

The MVP system is a content factory and operational platform, not a fully autonomous posting robot. The architecture must optimise package readiness, approvals, and traceability rather than introducing premature autoposting complexity.

### 2.7 The architecture must distinguish baseline from target-state

The current scaffold is a starter baseline, not a finished production system. This document explicitly labels what already exists and what is required next so planning and implementation stay honest.

---

## 3. Coherence locks and non-negotiable decisions

These locks remove ambiguity across stack, charter, backlog, and architecture.

### 3.1 Repo and packaging locks

- The current monorepo scaffold is the implementation baseline.
- Python apps and Python packages remain Poetry-based.
- `apps/web` and `packages/shared/ts` remain the pnpm workspace surface.
- Alembic remains under `apps/api`.
- Dockerfiles remain under `infra`.
- Shared cross-app Python primitives remain in `packages/shared/py`.

### 3.2 Runtime locks

- **FastAPI** is the only API framework for v1.
- **Prefect 2** is the only workflow orchestrator for v1.
- **Dramatiq + Redis** is the only worker/queue stack for v1.
- **Postgres 16 + pgvector** is the source of truth for operational and vector data.
- **MinIO** is the local object store and the S3-compatible baseline.
- **FFmpeg** is the deterministic editing/export engine.

### 3.3 Provider locks

- AI video generation in v1 is **Runway API only**.
- The v1 model lock is **`gen4.5`**.
- Future providers may be added via adapters, but they are not part of the MVP execution path.

### 3.4 Product boundary locks

- MVP output is a **ready-to-post package**.
- Human approval and human posting remain the posting boundary in MVP.
- Competitor ingestion is useful but cannot be a hard dependency for package generation.
- Asset Registry and anti-repetition controls are first-class requirements.

### 3.5 Reliability locks

- Costly tasks must be idempotent.
- Equivalent generation requests must resolve to the same exact AssetKey.
- Package completeness is a hard gate, not a best-effort outcome.
- Background execution must be observable through run, task, provider-job, and notification records.

---

## 4. What the scaffold actually contains today

This section documents the real baseline architecture already present in the zip.

### 4.1 Applications already scaffolded

The repository already contains these app surfaces:

- `apps/api`
- `apps/worker`
- `apps/orchestrator`
- `apps/web`

### 4.2 Shared packages already scaffolded

The existing shared foundations are:

- `packages/shared/py` for settings, logging, and shared error models;
- `packages/shared/ts` for shared TypeScript types/utilities for the web surface.

### 4.3 Domain package directories already scaffolded

The repository already includes package directories for:

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

These packages are part of the architecture contract even where implementation is still minimal.

### 4.4 Infra already scaffolded

The current scaffold already includes:

- Docker Compose for Postgres, Redis, MinIO, and app profiles;
- MinIO bucket-init containers;
- `infra/Dockerfile.api`;
- `infra/Dockerfile.worker`;
- `infra/Dockerfile.orchestrator`;
- root environment wiring for local/container execution.

### 4.5 Shared runtime configuration already present

`packages/shared/py` already defines a shared settings model covering:

- `database_url`
- `redis_url`
- `minio_endpoint`
- `minio_bucket`
- `minio_root_user`
- `minio_root_password`
- `runway_api_key`

This means there is already an architecture-approved shared config surface that new work should extend rather than replace.

### 4.6 Current implemented code baseline

The scaffold is currently a starter implementation, not the full production slice:

- the API exposes `/health`, shared logging, and a top-level exception handler;
- the worker configures Dramatiq with Redis and exposes a starter `ping` actor;
- the orchestrator exposes an example Prefect flow;
- the web app exposes a starter page;
- the initial database implementation contains only a minimal starter schema.

### 4.7 Current implemented schema baseline

The initial migration currently provisions:

- `assets`
- `runs`
- `run_assets`
- `outbox_events`

These tables are useful anchors, but they are far narrower than the phase-1 target data model.

---

## 5. Architecture scope: baseline, phase-1 target, and launch-plus

The architecture must be understood across three layers.

### 5.1 Layer A — current scaffold baseline

This is what already exists and is runnable:

- service skeletons;
- shared settings/logging/error primitives;
- starter Docker topology;
- starter migration and models;
- test/lint/typecheck/CI foundation.

### 5.2 Layer B — required phase-1 target

This is the architecture required for a real MVP Reel Factory:

- page and policy management;
- reel-family and reel lifecycle management;
- Asset Registry exact memoisation;
- reuse-with-transform decisioning;
- Runway submission, polling, and registration;
- deterministic editing and cover generation;
- QA gates;
- package writing and storage registration;
- run/task/provider-job visibility;
- operator notification and mark-posted workflows.

### 5.3 Layer C — launch-plus expansion

This layer includes later architecture that is intentionally deferred until the phase-1 factory is working:

- large-scale competitor ingestion;
- richer feature extraction;
- clustering and scoring engines;
- self-tuning policy;
- advanced dashboard analytics;
- autopost adapters;
- stronger managed observability and cloud hardening.

---

## 6. System context and product boundaries

### 6.1 Primary input boundaries

The system consumes:

- owned-page configuration and persona/policy inputs;
- manual or scheduled triggers;
- optional observed content or metric signals;
- internal creative briefs;
- provider responses from Runway;
- stored raw and derived media assets.

### 6.2 Primary output boundary

The primary output is a ready-to-post package containing:

- `final_video.mp4`
- `cover.png`
- `caption_variants.txt`
- `posting_plan.json`
- `provenance.json`

Optional outputs may include hashtags, pinned comment suggestions, alt text, keyframes, and a package manifest.

### 6.3 Human boundary

In MVP, the system may prepare, score, and notify, but final posting remains a human action. The architecture therefore optimises operator review and package trustworthiness rather than autonomous posting.

---

## 7. Canonical component architecture

### 7.1 High-level component map

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│                                Operator Surface                              │
│  Browser -> apps/web (Next.js) -> apps/api (FastAPI)                        │
└──────────────────────────────────────────────────────────────────────────────┘
                                         │
                                         │ HTTP / JSON
                                         v
┌──────────────────────────────────────────────────────────────────────────────┐
│                                   API Layer                                  │
│  Auth, CRUD, triggers, run views, package views, policy reads/writes         │
└──────────────────────────────────────────────────────────────────────────────┘
             │                         │                           │
             │ SQL / metadata          │ enqueue / flow trigger    │ presign / URIs
             v                         v                           v
┌──────────────────────┐    ┌──────────────────────┐    ┌──────────────────────┐
│   Postgres + vector  │    │  Prefect 2 flows     │    │   MinIO / S3-style   │
│   source of truth    │    │  orchestration       │    │   object storage      │
└──────────────────────┘    └──────────────────────┘    └──────────────────────┘
                                       │
                                       │ task submission
                                       v
                             ┌──────────────────────┐
                             │ Dramatiq + Redis     │
                             │ background workers   │
                             └──────────────────────┘
                                       │
             ┌─────────────────────────┼─────────────────────────┐
             │                         │                         │
             v                         v                         v
┌──────────────────────┐   ┌──────────────────────┐  ┌────────────────────────┐
│ Asset Registry       │   │ Editing / QA / Pack  │  │ External providers     │
│ resolve / reuse      │   │ deterministic media  │  │ Runway + later others  │
└──────────────────────┘   └──────────────────────┘  └────────────────────────┘
```

### 7.2 Architectural reading of the component map

The API is the authoritative request boundary. Postgres is the authoritative state store. Prefect owns workflow ordering. Dramatiq owns execution of discrete units of work. Redis is the queue and transient coordination layer. MinIO holds all important binaries. The Asset Registry sits at the heart of cost control and creative freshness. Runway is an external generation provider, not a state store.

### 7.3 Data plane vs control plane

The architecture works best when separated into two conceptual planes.

**Control plane:**
- API calls
- run creation
- workflow scheduling
- task state transitions
- policy reads/writes
- outbox notifications
- audit and integrity events

**Data plane:**
- asset storage
- package storage
- generation inputs/outputs
- editing intermediates
- keyframes, covers, and derived media

This distinction keeps package generation operationally traceable without turning storage into an ad hoc metadata database.

---

## 8. Service architecture and responsibility boundaries

### 8.1 `apps/api` — API boundary

The API service owns:

- authentication and authorisation;
- input validation;
- CRUD for pages, reel families, reels, assets, runs, and policy;
- manual triggering of flows;
- retrieval of package and artifact metadata;
- consistent error responses;
- write-audit logging of mutating actions.

The API should not perform the full reel generation pipeline inline. It records intent, validates input, and triggers orchestrated work.

### 8.2 `apps/orchestrator` — workflow boundary

The orchestrator owns:

- named Prefect flows;
- scheduling;
- dependency graph sequencing;
- parent-child workflow visibility;
- top-level retries and failure semantics;
- flow-level bookkeeping in the relational model.

Prefect is therefore responsible for orchestration logic, but not for executing every heavy step itself.

### 8.3 `apps/worker` — execution boundary

The worker service owns the discrete operational units of work, including:

- provider submissions;
- provider polling or reconciliation;
- asset staging and registration;
- editing and cover generation;
- QA evaluation;
- package writing;
- outbox dispatch;
- integrity checks;
- later feature extraction and ingestion tasks.

Dramatiq actors must remain idempotent, retry-safe, and narrow in responsibility.

### 8.4 `apps/web` — operator UI boundary

The web service owns the operator surface for:

- page views;
- reel-family and reel tracking;
- run visibility;
- package visibility;
- approval workflows;
- mark-posted actions;
- bounded policy editing.

The web app is an operational client of the API, not an alternate state authority.

---

## 9. Package-level architecture and domain boundaries

### 9.1 `packages/shared/py`

This is the shared cross-app Python foundation. It should continue to house:

- shared settings;
- structured logging setup;
- shared error schemas;
- other genuinely cross-app primitives.

It should remain small and stable.

### 9.2 `packages/core`

Core domain primitives that are broader than a single subsystem:

- enums;
- canonical identifiers;
- time/UUID helpers;
- shared domain-level schemas;
- core utilities that do not belong to a single package.

### 9.3 `packages/auth`

Auth and authorisation helpers:

- RBAC utilities;
- API-key hashing and validation helpers;
- request-context identity primitives.

### 9.4 `packages/storage`

Object storage abstractions and canonical path handling:

- MinIO/S3 wrapper;
- upload/download/presign logic;
- storage-key builders;
- checksum handling;
- package upload helpers;
- integrity verification helpers.

### 9.5 `packages/assets`

The Asset Registry and related media memory logic:

- prompt/parameter canonicalisation;
- AssetKey hashing;
- registry resolve logic;
- content-hash tracking;
- reuse-with-transform decisioning;
- similarity gate entry points;
- asset provenance helpers.

### 9.6 `packages/creative`

Creative planning and text generation surfaces:

- director logic;
- concept and brief shaping;
- hook and caption generation;
- overlay plan generation;
- posting-plan shaping;
- persona-aware content constraints.

### 9.7 `packages/editing`

Deterministic media assembly:

- ffprobe/ffmpeg wrappers;
- clip reframing;
- overlay rendering;
- cover extraction;
- export presets;
- editing template versions.

### 9.8 `packages/qa`

Quality gates:

- media format validation;
- provenance validation;
- repetition/cooldown checks;
- package completeness checks;
- page/persona constraint checks.

### 9.9 `packages/runs`

Operational state helpers:

- run logging;
- task logging;
- idempotency helpers;
- provider job linkage;
- flow/task state transitions.

### 9.10 `packages/outbox`

Event emission and dispatch helpers:

- event creation;
- backoff/retry semantics;
- notification sinks.

### 9.11 Later-phase packages

`packages/features`, `packages/ingestion`, and `packages/intelligence` remain valid architecture surfaces but are intentionally phase-gated so the reel factory can ship before advanced intelligence is required.

---

## 10. Runtime topology

### 10.1 Local runtime topology

The local architecture is designed around Docker Compose and a small number of app processes:

- Postgres
- Redis
- MinIO
- MinIO bucket-init container
- API service
- Worker service
- Orchestrator service
- Web app, typically run via pnpm in development unless containerised explicitly

### 10.2 Network and interaction model

The dominant local interactions are:

- API -> Postgres
- API -> Prefect flow trigger / run creation
- API -> storage presign helpers
- Orchestrator -> Postgres
- Orchestrator -> Dramatiq enqueue
- Worker -> Redis
- Worker -> Postgres
- Worker -> MinIO
- Worker -> Runway
- Web -> API

### 10.3 Why this topology is correct for the scaffold

This topology mirrors the actual scaffold choices:

- Docker Compose already provisions Postgres, Redis, and MinIO;
- app Dockerfiles already exist for API, worker, and orchestrator;
- the web stack is intentionally separate under pnpm;
- no Kubernetes or managed-control-plane assumptions are required to make progress.

---

## 11. Data architecture

### 11.1 Data-system principle

Postgres is the source of truth for metadata, control state, idempotency, and operator-visible state. MinIO is the source of truth for large binary artifacts. Redis is not a long-term system of record.

### 11.2 Current implemented baseline

The current baseline stores starter records for:

- assets
- runs
- asset-to-run linkage
- outbox events

This is useful but insufficient for the full product.

### 11.3 Phase-1 target data domains

The required phase-1 target expands the model into five groups.

**A. Auth and tenancy**
- orgs
- users
- org_memberships
- api_keys

**B. Pages and content lifecycle**
- pages
- reel_families
- reels
- reel_metrics
- audio
- features

**C. Asset Registry**
- asset_families
- assets
- asset_gen_params
- asset_usage

**D. Policy and experimentation**
- experiments
- policy_state

**E. Operational reliability**
- runs
- tasks
- provider_jobs
- outbox_events
- audit_log
- storage_integrity_checks

### 11.4 Why the model is split this way

This split cleanly separates:

- who can operate the system;
- what content objects exist;
- which media assets were created or reused;
- how policy and experiments drive behaviour;
- and how the system remains operationally trustworthy.

### 11.5 Source-of-truth rules

- Postgres stores identifiers, state, relationships, URIs, hashes, and metadata.
- MinIO stores raw/derived binary artifacts and final packages.
- Redis stores queue state and transient coordination only.
- Runway stores external job state temporarily, but the system mirrors that state into `provider_jobs`.

---

## 12. Canonical content and workflow entities

### 12.1 Pages

A page represents a managed or observed account in the portfolio. It stores ownership type, niche/persona information, and constraints that shape creative generation and review rules.

### 12.2 Reel families

A reel family represents a concept or hypothesis instance. It is the shared context for variants so the system can reason about A/B/C outputs without flattening everything into disconnected reels.

### 12.3 Reels

A reel represents a concrete content variant or an observed reel record. Generated reels move through an explicit lifecycle. Observed reels remain observational entries tied to ingestion and analytics logic.

### 12.4 Assets

Assets represent raw or derived media objects. They need to support:

- exact memoisation keys;
- content hashes;
- similarity metadata;
- storage URIs;
- generation parameters;
- usage history.

### 12.5 Runs and tasks

Runs represent human-meaningful workflow executions such as `daily_reel_factory` or `process_reel`. Tasks represent idempotent substeps such as provider submission, edit, or QA.

### 12.6 Provider jobs

Provider jobs mirror long-running external provider work, especially Runway job submission and reconciliation.

### 12.7 Outbox events

Outbox events are the reliable notification surface. They keep package-ready, failure, and integrity alerts decoupled from the main transaction path.

---

## 13. State models

### 13.1 Generated reel lifecycle

The canonical generated-reel lifecycle is:

```text
draft -> planning -> generating -> editing -> qa -> ready
                                              └-> qa_failed
ready -> posted
ready -> archived
```

This separation matters because operators need to distinguish:

- reels still being processed;
- reels that failed QA;
- reels ready for human review;
- reels already posted;
- reels intentionally retired.

### 13.2 Observed reel model

Observed reels do not flow through the generated-reel lifecycle. They represent externally observed or ingested content records and should be modelled distinctly from generated variants.

### 13.3 Asset lifecycle

A minimum useful asset lifecycle is:

```text
staged -> ready
staged -> failed
ready  -> deleted   (retention/cleanup path, usually deferred)
```

The key architectural rule is that an asset should not become `ready` until the storage object exists and integrity metadata has been written.

### 13.4 Task lifecycle

A useful task lifecycle is:

```text
queued -> running -> succeeded
queued -> running -> failed
queued -> running -> retrying -> running
queued -> skipped
```

### 13.5 Provider-job lifecycle

A provider-job lifecycle should remain separate from task state:

```text
submitted -> running -> succeeded
submitted -> running -> failed
submitted -> running -> cancelled
```

This distinction prevents loss of fidelity when an external provider is still progressing even if local orchestration context changes.

---

## 14. Asset Registry architecture

### 14.1 Why the registry is central

Without an Asset Registry, the system cannot control generation costs, cannot avoid obvious repetition, and cannot explain provenance well enough for operator trust. The registry is therefore a core architectural subsystem.

### 14.2 Exact memoisation

The system must canonicalise generation parameters into a stable AssetKey. Equivalent generation requests must generate the same canonical payload and therefore the same hash.

A minimum AssetKey payload includes:

- provider
- model
- canonical prompt
- canonical negative prompt
- seed
- duration
- fps
- ratio
- motion parameters
- init image hash if present
- relevant reference asset identifiers if present

### 14.3 Exact resolution outcomes

The registry must be able to return at least:

- `reuse_exact`
- `reuse_with_transform`
- `generate`
- `blocked`

### 14.4 Reuse-with-transform path

The architecture explicitly supports mutation rather than forcing a binary reuse-or-regenerate decision. Reuse-with-transform may include:

- crop/reframe or motion changes;
- timing/speed changes;
- overlay changes;
- audio replacement;
- colour or texture treatment;
- sequence composition changes.

These transforms must be logged deterministically so provenance remains meaningful.

### 14.5 Near-duplicate roadmap

Phase 1 needs exact memoisation first. Similarity deepening can progress in stages:

1. content hashes and basic keyframe pHash;
2. usage cooldown and family reuse caps;
3. embeddings with pgvector when sufficient volume exists;
4. more advanced similarity gating later.

### 14.6 Integrity requirements

The registry must associate assets with:

- storage URI
- content SHA-256
- relevant generation parameters
- usage history
- provenance linkage

Without these, the system cannot safely reason about reuse or cleanup.

---

## 15. Workflow architecture

### 15.1 Primary flow set

The architecture requires two main flows in phase 1:

- `daily_reel_factory`
- `process_reel`

### 15.2 `process_reel` canonical sequence

The canonical sequence is:

1. validate reel and page context;
2. transition reel into `planning`;
3. create or confirm creative brief and overlay/caption plan;
4. resolve assets through the Asset Registry;
5. generate or transform assets where required;
6. edit the final reel and extract the cover;
7. run QA checks;
8. build and upload the package;
9. mark the reel `ready`;
10. emit notification events.

### 15.3 `daily_reel_factory` canonical sequence

The daily factory should:

1. choose target owned pages;
2. load applicable policy;
3. decide concept/family count and variant strategy;
4. create reel families and concrete reels;
5. invoke `process_reel` for each target;
6. enforce budget guardrails and stop early when limits are hit.

### 15.4 Secondary phase-1 operational flows

Even in phase 1, the architecture benefits from secondary flows such as:

- `provider_job_sweeper`
- `outbox_dispatcher`
- `storage_integrity_check`
- `retention_cleanup` in dry-run or guarded mode
- `budget_guardrail_enforcer`

### 15.5 Later-phase flows

Later phases may add:

- `ingest_observed_reels`
- `extract_features`
- `cluster_patterns`
- `score_candidates`
- `policy_tune`

These must build on the same run/task/asset/reel architecture rather than inventing separate parallel pipelines.

---

## 16. API architecture

### 16.1 Current API baseline

The current scaffold already has:

- FastAPI app bootstrap
- `/health`
- shared logging
- structured error responses for unhandled exceptions
- starter ORM/Pydantic surfaces around `assets`, `runs`, and `outbox_events`

### 16.2 Required phase-1 API surface

The phase-1 architecture needs endpoints for at least:

- auth or API-key mediated access
- pages create/list/get/update
- reel families create/get
- reels create/get
- reel trigger
- mark-posted
- runs create/get
- asset get/resolve
- policy get/update

### 16.3 API design rules

The API must obey these rules:

- it maps cleanly to the canonical data model;
- it validates enums and constrained states explicitly;
- it returns conflict semantics for uniqueness and idempotency issues;
- it does not perform heavy background work inline;
- it writes audit entries for meaningful mutations.

### 16.4 Error model rules

Error responses should remain consistent and operator-readable. The shared error model already present in `packages/shared/py` should remain the foundation rather than being replaced with per-route improvisation.

---

## 17. Web architecture

### 17.1 Role of the web surface

The web app is not required to be feature-rich before the factory works, but it is the natural operator surface for real usage. It should therefore evolve as a thin, reliable operational console.

### 17.2 Minimum operator views

Phase 1 should support web/API visibility for:

- owned pages and competitor pages;
- reel families and variants;
- run lists and run detail;
- ready packages and package metadata;
- QA-failed reels;
- mark-posted action;
- bounded policy configuration.

### 17.3 Web architecture rule

The web app consumes the API. It must not become a second orchestration plane or a source of private business logic that bypasses backend policy/state handling.

---

## 18. Storage and packaging architecture

### 18.1 Canonical storage layout

The canonical object layout is:

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

### 18.2 Package-completeness rule

A reel is not `ready` until all required package objects have been written and registered successfully. Package writing therefore sits after successful media creation and QA, and before readiness notification.

### 18.3 Why storage is structured this way

This structure keeps:

- reusable media assets separate from final deliverables;
- per-reel deliverables collocated under a stable package path;
- logs and diagnostics separable from product outputs;
- migration from MinIO to S3 operationally simple.

### 18.4 Integrity rule

Storage objects should be traceable via database URIs and integrity metadata. Final package files should be eligible for manifest-level verification.

---

## 19. Security architecture

### 19.1 Authentication

MVP may begin with API keys and/or simple user auth, but keys must be hashed at rest and revocable. The architecture should not leak raw secret values into the database or logs.

### 19.2 Authorisation

The architecture assumes org-scoped RBAC with role shapes such as:

- owner
- admin
- operator
- reviewer
- readonly

Fine-grained role enforcement belongs at the API boundary.

### 19.3 Secret handling

Local MVP may use `.env`, but:

- secrets must never be committed;
- provider keys must be redacted from logs;
- container environments should receive secrets via environment or managed secret systems later.

### 19.4 Auditability

Mutating actions, provider submissions, package finalisation, integrity failures, and deletions should be auditable. This is both a security and an operational trust requirement.

### 19.5 Input hardening

The architecture should enforce:

- strict request schemas;
- enum validation;
- bounded prompt lengths;
- upload size and MIME restrictions where uploads exist;
- safe storage URI handling;
- no arbitrary SSRF-style remote-fetch surfaces.

---

## 20. Observability and operations architecture

### 20.1 Current scaffold baseline

The scaffold already includes structured logging in shared Python code. That is the correct starting point for operational consistency.

### 20.2 Required phase-1 observability surface

Phase 1 needs visibility through:

- run records
- task records
- provider-job records
- outbox-event records
- package readiness state
- QA failure reasons
- storage integrity findings

### 20.3 Why relational observability matters

This architecture favours product-grade operational observability that operators can query through the same application model, rather than treating observability as only external dashboards.

### 20.4 Outbox pattern

The outbox exists so notifications are reliable and decoupled. Package-ready and failure notifications should be emitted transactionally and dispatched asynchronously with retry/backoff semantics.

### 20.5 Integrity checks

The architecture should support independent integrity verification of stored assets and packages to prevent ghost records and silent corruption.

### 20.6 External telemetry later

Prometheus, Grafana, Loki, or OpenTelemetry remain valid launch-plus observability extensions, but they are not required to define the core phase-1 architecture correctly.

---

## 21. Local deployment architecture

### 21.1 Local development contract

The local development path is:

- Docker Compose for data services and optionally app services;
- Poetry-managed Python apps/packages;
- pnpm-managed web app;
- FFmpeg installed in the local runtime or app image.

### 21.2 Why local-first is architecturally important

Local-first development ensures:

- the reel factory can be tested without cloud spend on infrastructure;
- integration issues surface early;
- the team can validate the product loop before hardening distributed deployment.

### 21.3 Local environment alignment rule

New services or package assumptions should not be introduced in a way that breaks the existing `infra/docker-compose.yml` model without a deliberate architecture change.

---

## 22. Production migration path

### 22.1 Migration principle

The architecture is designed so the core code and domain model do not have to be rewritten when moving to managed infrastructure.

### 22.2 Straight-through substitutions

The main substitutions should be:

- MinIO -> S3
- local Postgres -> managed Postgres
- local Redis -> managed Redis
- local containers -> managed container runtime
- local secrets -> managed secret store
- local logging/metrics -> managed observability stack

### 22.3 What should not change during migration

The following should remain stable across local and production environments:

- API contracts
- package contract
- data model semantics
- Asset Registry semantics
- provider adapter boundaries
- run/task/provider-job logic

---

## 23. Risks and mitigations

### 23.1 Duplicate generation spend

**Risk:** identical generation requests call Runway multiple times.  
**Mitigation:** canonical AssetKey, relational uniqueness, idempotent task execution, reuse-first registry resolution.

### 23.2 Repetition fatigue

**Risk:** content becomes stale or visibly repetitive.  
**Mitigation:** asset-family tracking, cooldowns, reuse caps, similarity checks, reuse-with-transform paths.

### 23.3 Provider volatility

**Risk:** Runway throttles, delays, or fails jobs.  
**Mitigation:** provider-job persistence, sweeper/reconciliation flows, retry/backoff, budget guardrails.

### 23.4 Broken packages or ghost assets

**Risk:** metadata exists but storage objects are missing or corrupt.  
**Mitigation:** staged-to-ready rules, integrity checks, package-manifest verification, storage-integrity flow.

### 23.5 Over-architecting before the factory works

**Risk:** too much effort is spent on ingestion/scoring before the reel factory is dependable.  
**Mitigation:** phase separation, strict baseline vs target-state framing, shipping the package loop first.

### 23.6 Security and secret leakage

**Risk:** provider keys or sensitive URLs leak into logs or source control.  
**Mitigation:** secret redaction, hashed API keys, `.env` discipline, later managed secret storage.

### 23.7 Architectural drift

**Risk:** new work reintroduces alternate repo structures or ambiguous tool choices.  
**Mitigation:** this architecture, the scaffold-aligned charter/stack, and backlog enforcement against the current repo model.

---

## 24. Explicit non-goals and anti-patterns

The following are not acceptable under this architecture:

- inventing a second repo layout alongside the scaffold;
- replacing Prefect, Dramatiq, FastAPI, or the package-manager split without a deliberate architecture decision;
- bypassing the Asset Registry for expensive generation paths;
- storing product outputs only in ad hoc local folders instead of canonical package storage;
- treating autonomous posting as an MVP dependency;
- collapsing the entire system into a single opaque agent with no persistence, workflow states, or provenance;
- pretending the current scaffold already implements the full phase-1 schema when it does not.

---

## 25. Final architecture statement

The authoritative reading of this architecture is:

- the **current scaffold** is the implementation baseline;
- the **phase-1 target** is a real reel factory with registry, workflow, QA, packaging, and operator visibility;
- the **launch-plus layers** deepen intelligence and production hardening after the factory works;
- and every future backlog item must map cleanly to this scaffold-native architecture rather than redefining the system again.

This architecture therefore reconciles the product vision with the actual repository, preserves the intended long-term system design, and provides a clean build contract for implementation on top of the current zip scaffold.

---

## 26. Architecture acceptance checklist

A backlog item or code change is architecture-aligned only if all of the following are true:

- it fits the existing monorepo structure;
- it does not contradict the locked runtime and provider choices;
- it advances the reel factory, the Asset Registry, the operator platform, or an explicitly phased later subsystem;
- it respects the package output contract;
- it preserves determinism and idempotency where required;
- it keeps binary artifacts in canonical storage rather than in ad hoc local-only paths;
- and it does not quietly assume architecture that is not yet implemented.

---
