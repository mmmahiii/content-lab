# Content Laboratory — Comprehensive Tech Stack v2.0 (Scaffold-Aligned Master Stack)

**Owner:** Ryan  
**Date:** 18 March 2026  
**Status:** Authoritative working stack definition  
**Scope:** Current monorepo scaffold baseline -> build-ready MVP Reel Factory -> launch hardening  
**Supersedes:** Content Laboratory — Comprehensive Tech Stack (Calculated, AI-Friendly) v1

---

## 0. Document purpose

This document defines the full technology stack for Content Laboratory in a way that is consistent with the repository scaffold that already exists.

It replaces older stack language that was directionally right but no longer fully matched the actual repo shape, package boundaries, implementation conventions, and local runtime assumptions in the zip scaffold.

This document is designed to serve four purposes at once:

1. define the authoritative technology choices for v1;
2. distinguish clearly between what the scaffold already implements and what is only a target-state build requirement;
3. give engineering and AI coding agents an unambiguous execution surface; and
4. align the stack with the scaffold-aligned project charter and the intended production architecture.

The stack must therefore be read as both a **technology definition** and a **build constraint document**.

---

## 1. Executive summary

Content Laboratory is a **local-first monorepo** for producing **ready-to-post reel packages** with deterministic asset reuse, anti-repetition controls, human-review-first packaging, and a clear upgrade path to a more intelligence-heavy system.

The actual scaffold already locks the core implementation shape:

- **API:** FastAPI
- **Workflow orchestration:** Prefect 2
- **Execution queue:** Dramatiq + Redis
- **Database:** Postgres 16 + pgvector
- **Object storage:** MinIO locally, S3-compatible in production
- **Web application:** Next.js 15 + React 19
- **Python packaging:** Poetry per app/package
- **Node packaging:** pnpm workspace
- **Media processing:** FFmpeg
- **Video generation provider for v1:** Runway API using `gen4.5`
- **MVP posting model:** human approval and human posting

The scaffold is structurally correct, but the implemented codebase is still a starter slice. That means the stack must be understood in two layers:

1. **current scaffold baseline** — what is already present and runnable now; and
2. **required build target** — what must be implemented on top of that scaffold without changing the stack contract.

The purpose of this document is to remove all ambiguity around those two layers.

---

## 2. Stack philosophy

The stack is designed around six operating principles.

### 2.1 Local-first before cloud-first

The system must be fully buildable, testable, and operable on a local machine before any production migration is attempted. That is why Postgres, Redis, and MinIO are first-class local services and why Docker Compose is part of the scaffold rather than an afterthought.

### 2.2 The reel package is the product surface

The first shipping surface is not a dashboard, a model, or a trend classifier. It is a **complete output package** containing the final video, cover, caption variants, plan, and provenance. The stack must prioritise deterministic generation, media handling, storage, and packaging accordingly.

### 2.3 Determinism matters wherever cost exists

Expensive external calls must be idempotent. Equivalent inputs must resolve to equivalent generation keys. The stack therefore treats canonicalisation, hashing, idempotency, and registry lookups as infrastructure concerns rather than optional utility logic.

### 2.4 Repo shape is part of the stack

The stack is not only a list of tools. It includes the monorepo topology, package manager split, migration location, Docker layout, and test/lint/typecheck conventions. A design that ignores the actual repo structure is not considered aligned.

### 2.5 The stack must separate baseline from target-state

The repo currently contains starter implementations. The stack must not pretend that every later table, endpoint, or worker path already exists. This document therefore labels **implemented baseline**, **required MVP build**, and **launch-plus** expectations explicitly.

### 2.6 Anti-repetition is a platform capability, not a feature add-on

The Asset Registry, content hashing, reuse policy, cooldown logic, and similarity controls are fundamental to cost control and creative quality. The stack must support them natively across the database, storage, workers, and package design.

---

## 3. Coherence locks and non-negotiable technology choices

The following decisions are locked for v1.

### 3.1 Application and runtime locks

- **FastAPI** is the only API framework for v1.
- **Prefect 2** is the only workflow orchestrator for v1.
- **Dramatiq** is the only background execution framework for v1.
- **Redis** is the only queue backend for v1.
- **Postgres 16** is the primary system of record.
- **pgvector** is the vector extension strategy for v1.
- **MinIO** is the local object store and the S3-compatibility baseline.
- **Next.js 15** is the admin web application framework.
- **FFmpeg** is the deterministic media processing engine.

### 3.2 Language and package management locks

- Python is locked to **3.11** across the Python services and packages.
- Python dependency and environment management is **Poetry per project**.
- Node dependency management is **pnpm**.
- The JavaScript workspace is intentionally narrow: only `apps/web` and `packages/shared/ts` are in the pnpm workspace.
- There is **no top-level Python monolith package**. Python code remains distributed across apps and Poetry-managed packages.

### 3.3 Provider locks

- AI video generation in v1 is **Runway API only**.
- The v1 model lock is **`gen4.5`**.
- Provider adapter design is permitted, but no second video provider is allowed into the MVP execution path unless explicitly approved.

### 3.4 Product boundary locks

- Output must be a ready-to-post package.
- Posting remains human-driven in MVP.
- Competitor ingestion is useful but must not be required for the reel factory to function.
- The Asset Registry is mandatory.

### 3.5 Ambiguities removed from older versions

The following older ambiguities are explicitly removed:

- no `Prefect or Dagster` split; it is **Prefect 2 only**;
- no `Dramatiq or Celery` split; it is **Dramatiq only**;
- no `dashboard` as the primary web location; the scaffold uses **`apps/web`**;
- no vague provider set for v1 video generation; it is **Runway `gen4.5` only**;
- no assumption of a top-level shared Python repo package; the scaffold uses **multiple Poetry projects plus path dependencies**;
- no assumption that the full production schema already exists in code.

---

## 4. What the actual scaffold contains today

This section documents the real scaffold baseline.

### 4.1 Applications already present

The scaffold contains four app-level surfaces:

- `apps/api` — FastAPI service
- `apps/worker` — Dramatiq worker service
- `apps/orchestrator` — Prefect flow service
- `apps/web` — Next.js admin UI

### 4.2 Shared packages already present

The scaffold contains two shared foundations:

- `packages/shared/py` — shared Python settings, logging, and error primitives
- `packages/shared/ts` — shared TypeScript package

### 4.3 Domain package directories already scaffolded

The scaffold already includes package directories for the following Python domains:

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

These are part of the repo contract even where implementation remains minimal.

### 4.4 Infra already present

The scaffold already contains:

- Docker Compose definitions for Postgres, Redis, MinIO, and app profile services;
- a MinIO bucket init step;
- Dockerfiles for API, worker, and orchestrator in `infra/`;
- an `.env.example` template;
- Alembic configuration under `apps/api`.

### 4.5 Engineering controls already present

The repo already includes:

- CI workflow on GitHub Actions;
- ESLint, Prettier, TypeScript, Vitest on the web side;
- Ruff, mypy, pytest on the Python side;
- pre-commit configuration;
- contributing rules;
- AI rules;
- local-run docs;
- scaffold verification scripts;
- worktree workflow scripts.

### 4.6 Current implementation depth

The current scaffold implements only a starter slice:

- the API exposes health handling and starter database models;
- the worker exposes a starter `ping` actor;
- the orchestrator exposes an example Prefect flow;
- the web app exposes a starter admin page;
- the database implementation is currently much narrower than the full target schema.

This matters because the stack must not overstate what is already implemented.

---

## 5. Monorepo topology and package-management stack

### 5.1 Canonical repo topology

The scaffold-native repo shape is:

```text
content-lab/
  apps/
    api/
    worker/
    orchestrator/
    web/
  packages/
    shared/
      py/
      ts/
    core/
    auth/
    storage/
    assets/
    creative/
    editing/
    features/
    ingestion/
    intelligence/
    outbox/
    qa/
    runs/
  infra/
  docs/
  scripts/
```

This topology is authoritative. Any future docs, backlog tasks, or implementation plans must conform to this structure.

### 5.2 Python package-management model

The Python side is intentionally **multi-project Poetry**, not a single root Python project.

This means:

- `apps/api`, `apps/worker`, and `apps/orchestrator` each have their own `pyproject.toml`;
- each domain package under `packages/` also has its own `pyproject.toml`;
- `packages/shared/py` acts as the current shared Python dependency surface;
- apps consume shared code through **path dependencies**, not through an external package registry.

This design is scaffold-aligned because it matches what is already in the zip.

### 5.3 Node package-management model

The Node side is intentionally narrow.

The pnpm workspace includes only:

- `apps/web`
- `packages/shared/ts`

That means the web application and the shared TypeScript package are versioned and installed through the workspace, while the rest of the repo remains Python-first.

### 5.4 Compatibility layout note

The repository includes scripts that create `packages/<name>/py` compatibility paths for scaffold verification tooling. These compatibility paths are **verification aids**, not the conceptual source of truth for the stack. The real source of truth remains the actual package directories plus their Poetry project definitions.

### 5.5 Root-level tooling contract

At the root of the repo:

- `pnpm` is the JavaScript package manager;
- Node is pinned through engine constraints and `.nvmrc`;
- root scripts operate on `web` and `shared-ts`;
- Python validation is driven by shell scripts that iterate across Poetry projects.

This is an important stack characteristic: the repo is monorepo-structured, but it is **not** managed through one universal cross-language package manifest.

---

## 6. Application stack by layer

### 6.1 Web application layer

**Framework:** Next.js 15  
**Runtime UI stack:** React 19 + React DOM 19  
**Language:** TypeScript 5.x  
**Current role:** admin UI scaffold  
**Target MVP role:** operator console for viewing pages, runs, reels, assets, packages, and status

The web layer is intentionally an admin surface, not the execution engine. It should remain thin and consume data from the FastAPI service rather than embedding business logic.

Current scaffold expectations:

- app-router structure under `apps/web/app`
- linted by ESLint
- formatted by Prettier
- typechecked by `tsc --noEmit`
- tested by Vitest

### 6.2 API layer

**Framework:** FastAPI  
**Runtime:** Uvicorn  
**Language:** Python 3.11  
**Packaging:** Poetry  
**Current role:** starter API surface  
**Target MVP role:** HTTP control plane for pages, reel families, reels, policies, runs, assets, and package visibility

The API is the main synchronous control boundary for the system. It owns:

- request validation;
- CRUD operations;
- trigger endpoints for workflows;
- retrieval endpoints for status and artifacts;
- auth and policy enforcement;
- operator-safe control over the production pipeline.

Alembic lives inside `apps/api`, so the API project is also the database migration home.

### 6.3 Worker layer

**Framework:** Dramatiq  
**Queue backend:** Redis  
**Language:** Python 3.11  
**Packaging:** Poetry  
**Current role:** starter actor host  
**Target MVP role:** execution engine for generation, editing, QA, packaging, outbox dispatch, and auxiliary jobs

The worker layer is where expensive or asynchronous steps belong. It must remain idempotent and task-oriented. It is not the place for orchestration logic. Orchestration belongs to Prefect.

### 6.4 Orchestrator layer

**Framework:** Prefect 2  
**Language:** Python 3.11  
**Packaging:** Poetry  
**Current role:** starter flow host  
**Target MVP role:** scheduling, flow state, dependency sequencing, retries policy, and run-level coordination

The orchestrator decides **what sequence should happen**. The worker performs **the actual step execution**. This separation is a critical stack contract and must not be blurred.

### 6.5 Shared Python layer

`packages/shared/py` currently provides the real shared Python primitives used by the apps:

- settings loading;
- logging configuration;
- shared error objects.

It currently acts as the smallest common dependency surface across Python services.

### 6.6 Shared TypeScript layer

`packages/shared/ts` is the shared TypeScript package for types and reusable web-facing contracts. It is the only current non-app JS package in the pnpm workspace.

### 6.7 Domain package layer

The remaining Python package directories exist to hold business-domain logic outside the app shells. The intended split is:

- `core` — generic repo-wide Python infrastructure
- `auth` — authentication and permission helpers
- `storage` — MinIO/S3 wrappers and storage contracts
- `assets` — Asset Registry, canonicalisation, hashing, provider adapters
- `creative` — planning, persona, concept and script logic
- `editing` — FFmpeg composition, overlays, covers, packaging media steps
- `features` — extracted reel/audio/content features
- `ingestion` — observed reel and metrics ingestion
- `intelligence` — clustering, scoring, policy learning
- `outbox` — reliable notification/event dispatch
- `qa` — format, provenance, repetition, and readiness gates
- `runs` — run/task logging and execution metadata

This split is already implied by the scaffold and should be retained.

---

## 7. Data and persistence stack

### 7.1 Primary operational database

**Engine:** Postgres 16  
**Extension strategy:** pgvector  
**Access layer:** SQLAlchemy + Psycopg  
**Migration tool:** Alembic under `apps/api`

Postgres is the source of truth for:

- application entities;
- run and task state;
- policy state;
- assets and provenance metadata;
- idempotency keys;
- references into object storage;
- optional vector data where similarity and clustering require it.

### 7.2 pgvector role

`pgvector` is the v1 vector strategy for:

- similarity lookups;
- future feature embeddings;
- near-duplicate control;
- asset-family or content-family representation where needed.

It is part of the data stack contract even if the current starter schema uses it only minimally.

### 7.3 Current implemented database baseline

The current scaffold includes only a starter schema surface. It is not yet the full production-grade schema. This is important because the stack document must remain honest:

- the database technology choice is locked;
- the target schema is larger;
- the existing code only implements part of it.

### 7.4 Queue and transient state

**Engine:** Redis 7

Redis exists in the stack for:

- Dramatiq broker state;
- short-lived locks;
- retry timing and queue semantics;
- ephemeral task coordination where appropriate.

Redis is not the durable system of record.

### 7.5 Object storage

**Local engine:** MinIO  
**Production-compatible model:** S3-compatible object storage

Object storage is the canonical location for binary outputs:

- raw generated assets;
- derived frames or stems;
- final package artifacts;
- future manifests and integrity metadata.

The database stores URIs and metadata, not binary media bodies.

---

## 8. Media-processing stack

### 8.1 Deterministic media engine

**Tool:** FFmpeg

FFmpeg is a core stack dependency because the product output is a reel package. It is responsible for:

- clip normalisation;
- audio handling;
- overlays and subtitle-like choreography;
- cover extraction;
- deterministic export to target dimensions;
- package-ready media generation.

### 8.2 Output format target

The canonical MVP export target is vertical social video suitable for Instagram-style reels.

Minimum output expectations:

- 1080 x 1920 final video;
- final MP4 output;
- valid audio track presence;
- cover image generation;
- packaging alongside non-media artifacts.

### 8.3 Why FFmpeg is non-optional in the stack

The stack requires a deterministic media layer that can be run locally, scripted, tested, and reproduced. FFmpeg provides that layer. Editing is therefore not outsourced to an opaque platform step.

---

## 9. AI provider and creative-generation stack

### 9.1 Video generation provider

**Provider lock:** Runway API  
**Model lock for v1:** `gen4.5`

The old stack language that allowed several video-generation options is no longer acceptable for v1. The scaffold-aligned stack uses one provider path for the MVP. That keeps the Asset Registry, canonicalisation rules, provider-job tracking, and cost controls coherent.

### 9.2 LLM usage pattern

The system may use language-model calls for:

- concept generation;
- hook and caption generation;
- persona-aware writing;
- planning and rationale generation;
- optional later QA support.

However, the stack does **not** require a single locked LLM provider in the same way it locks the video provider for v1. The key stack requirement is instead that the LLM boundary be abstracted cleanly enough to support deterministic prompts, versioning, and later provider changes.

### 9.3 Provider adapter expectation

Even though only Runway is allowed for v1 video generation, provider integration must still be implemented through a controlled adapter boundary. That allows:

- job submission abstraction;
- provider-job persistence;
- retries and backoff;
- secure logging;
- future provider extension without changing higher-level business logic.

### 9.4 Anti-provider-sprawl rule

The v1 build must not introduce a second production video path. Additional providers may exist only as later adapters outside the MVP execution path.

---

## 10. Asset Registry and anti-repetition stack

### 10.1 Purpose

The Asset Registry is a first-class stack subsystem whose job is to stop wasteful regeneration, manage reuse, and support controlled variation.

### 10.2 Required layers inside the stack

The registry depends on several stack layers working together:

- prompt and parameter canonicalisation;
- stable hashing for AssetKey generation;
- persistent asset metadata in Postgres;
- object storage for asset bytes;
- provider-job linkage;
- usage tracking across reels and pages;
- later similarity controls via hashes and/or embeddings.

### 10.3 Exact-match prevention

Equivalent generation inputs must resolve to the same AssetKey and therefore to reuse rather than regeneration.

This is not optional optimisation. It is part of the stack design because it affects:

- cost;
- reproducibility;
- reliability;
- testability.

### 10.4 Near-duplicate controls

The target stack includes near-duplicate controls using perceptual hashes and later vector similarity where necessary. These may be phased in, but the data and storage choices already need to support them.

### 10.5 Reuse-with-transform expectation

The stack must allow an asset-resolution decision model that returns one of the following classes of outcome:

- reuse exact;
- reuse with transform;
- generate fresh;
- block.

This decision model influences the database schema, worker jobs, policy layer, and QA layer.

---

## 11. Workflow and asynchronous execution stack

### 11.1 Responsibility split

The workflow stack is intentionally split in two:

- **Prefect 2** owns scheduling, flow structure, retries policy, and run coordination.
- **Dramatiq** owns individual job execution.

This split is locked and should not be collapsed into one tool.

### 11.2 Why this split matters

The reel factory needs both:

- clear run-level orchestration with visibility into the larger process; and
- simple, queue-backed task execution for expensive or retryable units of work.

Prefect is the run brain. Dramatiq is the execution muscle.

### 11.3 Typical execution path

A scaffold-aligned MVP execution path looks like this:

1. a reel or daily factory run is triggered;
2. Prefect creates and coordinates the flow;
3. Dramatiq executes expensive or asynchronous steps;
4. Postgres stores durable state transitions;
5. Redis carries broker and transient queue state;
6. MinIO stores resulting assets and packages;
7. the API and web surface expose status and outputs.

### 11.4 Idempotency expectation

Because generation is expensive, the workflow stack must support idempotent external operations. That requirement affects task design, DB constraints, and provider integration.

---

## 12. API and interface-contract stack

### 12.1 API role

The API is the synchronous control layer for operators, automations, and the web app. It should not be treated as a worker replacement.

### 12.2 Contract expectations for v1

The MVP API surface is expected to grow to cover:

- pages;
- reel families;
- reels;
- asset resolution;
- policy state;
- runs and status;
- package visibility;
- posting metadata.

### 12.3 Validation model

FastAPI plus Pydantic is the input/output contract layer. Validation belongs at the API boundary first, with additional business-rule enforcement inside the service and worker layers.

### 12.4 Error-contract expectation

The scaffold already centralises shared error primitives. The stack expectation is that APIs return structured, predictable error payloads rather than ad hoc exception output.

---

## 13. Configuration, environment, and secret-management stack

### 13.1 Environment loading baseline

The current shared Python settings loader walks upward to find the repo-root `.env`, allowing both normal checkouts and Docker-based runs to resolve configuration consistently.

### 13.2 Local config model

The local stack expects configuration for at least:

- database URL;
- Redis URL;
- MinIO endpoint and bucket;
- MinIO credentials;
- Runway API key.

### 13.3 Secret-management rule

Secrets must never be committed. The stack treats `.env.example` as a template only.

### 13.4 Production-minded design without overengineering

The local-first stack uses environment variables and `.env` files for development, while keeping the design compatible with later migration to a managed secret store.

---

## 14. Local infrastructure stack

### 14.1 Docker Compose baseline

The local infrastructure stack is Docker Compose-based and already scaffolded.

Core local services:

- Postgres
- Redis
- MinIO
- MinIO bucket initialiser

Optional app profile services:

- API
- worker
- orchestrator

### 14.2 App-container build layout

The scaffold stores Dockerfiles in `infra/` rather than inside each app directory. This is part of the repo-native stack contract and should not be silently rewritten in future docs.

### 14.3 Bucket bootstrap contract

The Compose stack includes bucket initialisation. That is important because object storage is not optional in this product. The local stack must come up ready for binary output rather than requiring manual storage bootstrapping every time.

### 14.4 Why MinIO matters in development

Using MinIO locally ensures that the database/media/storage contract behaves like a real object-storage system instead of a local temp-folder shortcut.

---

## 15. Developer tooling and engineering-operations stack

### 15.1 Source formatting and linting

The scaffold already defines a split-by-language quality stack.

Python side:

- Ruff for linting and formatting checks
- mypy for type checking
- pytest for tests

TypeScript side:

- ESLint for linting
- Prettier for formatting
- TypeScript compiler for type checking
- Vitest for tests

### 15.2 CI model

The CI pipeline is already split into:

- a Node job for workspace install, lint, typecheck, and test;
- a Python job for Poetry installation and repo-wide Python checks.

This split reflects the monorepo’s actual language boundary and is therefore part of the stack, not only part of operations.

### 15.3 Pre-commit and repo hygiene

The scaffold includes pre-commit and editor config files. These should be treated as part of the development stack because they help maintain consistency across AI-assisted contributions.

### 15.4 Worktree workflow support

The repo includes worktree scripts and AI workflow guidance. This is operationally important because the intended usage pattern includes parallel AI task execution. The stack therefore includes not only runtime tools but also the change-management tooling used to develop safely inside the repo.

---

## 16. Reliability and observability stack

### 16.1 What is currently present

The scaffold currently provides basic logging primitives through the shared Python package and starter logging configuration in the API.

### 16.2 What the MVP stack requires next

The required MVP observability baseline is:

- structured logging across services;
- correlation across runs, tasks, and errors;
- durable run/task state in Postgres;
- enough visibility to diagnose failed generation, storage, packaging, or queue behaviour.

### 16.3 Launch-ready observability direction

A fuller observability layer may later include richer metrics and dashboards, but those are not allowed to distort the MVP stack priorities. The MVP should first ensure that flow state, task state, provider state, and package state are inspectable and debuggable.

### 16.4 Reliability design expectations

The stack must support:

- retries where safe;
- idempotent expensive operations;
- durable status transitions;
- storage integrity checks;
- package completeness gates;
- safe failure reporting.

---

## 17. Security and governance stack

### 17.1 Current baseline

The scaffold already includes explicit AI rules and repo-level expectations around secrets, testing, and deterministic behaviour.

### 17.2 Security expectations for the application layer

The build must add a security layer that supports:

- operator-safe API access;
- hashed or otherwise protected key storage;
- route-level auth and permission rules;
- redaction of secrets in logs;
- auditable mutation paths for high-impact operations.

### 17.3 Governance boundary

The product boundary is human-posting-first and platform-safe. That means the stack is not designed around fake engagement, covert automation, or unauditable posting actions.

### 17.4 Provenance as a governance mechanism

Provenance is not just an output nicety. It is part of the governance stack because it records:

- source assets;
- prompts and parameters;
- provider/model versions;
- timestamps;
- package lineage.

---

## 18. Current scaffold baseline versus required build target

This section is critical.

### 18.1 Current baseline

The scaffold already gives the repo the correct skeleton:

- app boundaries;
- package directories;
- package management split;
- infra services;
- local run commands;
- CI and repo controls.

### 18.2 What is still only target-state

The following are stack-aligned targets, not current implementation facts:

- the full content-domain schema;
- asset-registry behaviour beyond the starter slice;
- full reel-family and reel lifecycle APIs;
- package builder and package manifest logic;
- complete worker execution set;
- complete policy-state and experimentation system;
- mature ingestion, features, and intelligence services.

### 18.3 Why this distinction matters

If the stack document fails to distinguish baseline from target-state, implementation work becomes confused. Teams start coding against a document that describes a future architecture as if it already exists.

This v2 stack intentionally avoids that mistake.

---

## 19. MVP stack requirements

The MVP build, using the current scaffold, must produce a working reel factory with the following stack behaviours.

### 19.1 Runtime behaviours

- the API can create and track the core production entities;
- the orchestrator can coordinate a reel-processing run;
- the worker can execute the expensive steps;
- the database can persist durable state and package references;
- object storage can hold raw assets and final package outputs.

### 19.2 Product behaviours

- a reel can move from creation through package-ready state;
- asset resolution can avoid duplicate generation for identical inputs;
- FFmpeg can produce deterministic export artifacts;
- QA can block incomplete or invalid outputs;
- the system can surface package-ready status to operators.

### 19.3 Governance behaviours

- packages include provenance;
- output contracts are stable;
- logs do not leak secrets;
- human approval and human posting remain the MVP boundary.

---

## 20. Launch-plus stack direction

The scaffold-aligned stack also supports later hardening without changing its foundations.

### 20.1 Expected launch-plus extensions

- richer auth and role handling;
- fuller run/task/provider job tracking;
- outbox and notification workers;
- competitor and own-account ingestion;
- feature extraction;
- clustering and scoring;
- richer similarity and reuse intelligence;
- admin UI expansion.

### 20.2 What should not change later

Even as the product matures, the following foundational stack choices should remain stable unless a deliberate architecture change is approved:

- FastAPI API
- Prefect 2 orchestration
- Dramatiq + Redis execution
- Postgres + pgvector persistence
- MinIO/S3-style storage model
- Next.js admin app
- Poetry per Python project
- pnpm workspace for JS side
- FFmpeg for deterministic media exports

---

## 21. Cost and performance assumptions for the stack

### 21.1 Why the stack is cost-sensitive

The system’s most expensive surface is external video generation. That is why deterministic asset reuse sits inside the stack design.

### 21.2 Cost-control layers in the stack

The stack controls cost through:

- exact-match AssetKey reuse;
- reuse-with-transform rather than blind regeneration;
- queue-based execution rather than uncontrolled parallelism;
- policy and budget surfaces stored in durable state;
- human-review-first packaging rather than automatic posting loops.

### 21.3 Performance assumptions

The local-first stack assumes a machine strong enough to run:

- Docker Compose infra;
- API, worker, and orchestrator processes;
- web dev server when needed;
- FFmpeg processing;
- normal test and lint cycles.

The stack does not assume local GPU dependence for the MVP because video generation is provider-hosted.

---

## 22. Production migration path

The stack is deliberately designed so local MVP infrastructure maps cleanly to production-minded equivalents.

### 22.1 Storage migration path

- MinIO locally -> S3-compatible production storage

### 22.2 Database migration path

- local Postgres -> managed Postgres

### 22.3 Queue migration path

- local Redis -> managed Redis

### 22.4 App deployment migration path

- Compose-based local services -> container deployment environment of choice

### 22.5 What should stay constant during migration

The application contract, package boundaries, object-storage model, and workflow split should remain constant. Production migration should swap infrastructure implementation, not invalidate the repo shape.

---

## 23. Explicit v1 prohibitions

The following are out of bounds for the scaffold-aligned v1 stack unless explicitly approved:

- replacing Prefect 2 with another orchestrator;
- replacing Dramatiq with Celery or another queue framework;
- introducing a second production video-generation provider into the MVP path;
- moving the web surface out of `apps/web`;
- collapsing the Python side into one root package that ignores the existing Poetry structure;
- treating local disk folders as a substitute for object storage;
- bypassing provenance generation in package output;
- making competitor ingestion a hard dependency for reel-factory operation.

---

## 24. Acceptance checklist for stack alignment

A future implementation should only be described as “stack-aligned” if all of the following are true:

1. it fits the existing monorepo topology;
2. it uses FastAPI, Prefect 2, Dramatiq, Redis, Postgres, MinIO, FFmpeg, and Next.js in the roles defined here;
3. it respects Poetry-per-project and pnpm-workspace boundaries;
4. it keeps Alembic under `apps/api`;
5. it uses object storage for media artifacts rather than hidden local-only shortcuts;
6. it treats the Asset Registry as a first-class subsystem;
7. it distinguishes current scaffold baseline from target-state build scope;
8. it preserves the ready-to-post package as the primary output contract;
9. it maintains human approval and human posting as the MVP boundary;
10. it does not reintroduce technology ambiguities already removed in this version.

---

## Appendix A. Canonical repo shape summary

```text
content-lab/
  apps/
    api/                     # FastAPI, Alembic, DB-facing service layer
    worker/                  # Dramatiq actors
    orchestrator/            # Prefect 2 flows
    web/                     # Next.js 15 admin UI
  packages/
    shared/
      py/                    # shared Python settings/logging/errors
      ts/                    # shared TypeScript package
    core/                    # generic Python infrastructure
    auth/                    # auth helpers
    storage/                 # MinIO/S3 abstractions
    assets/                  # registry, canonicalisation, provider adapters
    creative/                # planning, persona, captions, concepts
    editing/                 # ffmpeg wrappers, overlays, covers
    features/                # extracted feature logic
    ingestion/               # observed data ingestion
    intelligence/            # clustering and scoring
    outbox/                  # event dispatch
    qa/                      # quality gates
    runs/                    # run/task state helpers
  infra/                     # compose + Dockerfiles + env template
  docs/                      # rules, run guides, workflow docs
  scripts/                   # verification, py checks, worktree helpers
```

---

## Appendix B. Canonical local stack summary

### Python side

- Python 3.11
- Poetry
- FastAPI
- Uvicorn
- SQLAlchemy
- Psycopg
- pgvector
- Alembic
- Prefect 2
- Dramatiq
- Redis client

### JavaScript side

- Node 24+
- pnpm 9
- Next.js 15
- React 19
- TypeScript 5.x
- ESLint
- Prettier
- Vitest

### Infra side

- Docker Compose
- Postgres 16
- Redis 7
- MinIO
- FFmpeg

### External AI side

- Runway API (`gen4.5`) for v1 video generation

---

## Appendix C. Ready-to-post package contract

Every MVP reel package must be able to include, at minimum:

- `final_video.mp4`
- `cover.png`
- `caption_variants.txt`
- `posting_plan.json`
- `provenance.json`

Optional companion artifacts may include:

- hashtag sets
- pinned comment suggestions
- alt text
- package manifest

The stack is considered successful only if it can produce and store this package reliably.
