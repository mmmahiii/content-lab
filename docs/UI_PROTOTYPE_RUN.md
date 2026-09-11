# Open the operator prototype

Prerequisites: Node.js 24+ and pnpm 9. The prototype uses the existing Next.js application with a new interface and an injected local mock service. It requires no Python, Docker, API server, provider key, account connection or environment file.

From PowerShell:

```powershell
Set-Location 'C:\Users\islam\.codex\worktrees\924c\content-lab'
pnpm install --frozen-lockfile
pnpm dev
```

Dependencies are already installed in this worktree; subsequent openings only need `pnpm dev`. Keep that terminal running and open **http://127.0.0.1:3000**. Stop it with Ctrl+C. The dev server binds to the local loopback interface. Use the same hostname and port to retain browser drafts.

For a production build, stop the dev server first:

```powershell
pnpm --filter web build
pnpm --filter web start --hostname 127.0.0.1
```

## What to review

The nine navigation destinations are **Content, Pages, Ideas, Asset Registry, Asset packs, Review, Publication, Operations and Learning**. Each content item has Brief, Hook & blueprint, Ingredients, Scene editor, Execution, Review and Publication tabs. The three fixture families are layered product stories, graphic explainers and a narrated source-video composition.

Start with these five complete journeys:

1. In **Asset Registry**, select Warm white ceramic mug, Warm studio surface and Quiet studio tone. Create from selected assets. Edit the brief/copy, inspect the hook and blueprint, open the scene editor and make a visible edit. Create preview, open Execution and render the saved revision. Review, approve the exact package and prepare publication.
2. In **Asset packs**, plan four assets with mix `2 product, 1 environment, 1 music`. Authorise the acquisition scope and fulfil it. Inspect failures and missing items, retry an item or create from the ready subset.
3. In **Operations**, inspect “A second look at the table”. Retry its failed execution and review attempt 2; the original failed attempt remains in history. Separately reconcile the unknown provider outcome before considering another attempt.
4. In the mug's **Scene editor**, save a revision, select Ceramic mug, choose Replace object and compare Coral ceramic mug. Inspect preservation notes, apply, edit text or timing, create a new preview and simulated render. Compare the resulting package with its parent revision.
5. In **Publication**, prepare an approved package, download the handoff JSON and record a simulated external reference with an actual past timestamp in the displayed timezone. Follow View observations; values remain unavailable until supplied. Enter sample metrics to explore a provisional observation.

The [review guide](UI_PROTOTYPE_REVIEW.md) covers brand setup, ideas, intake, learning and judgement questions. The [audit](UI_PROTOTYPE_AUDIT.md) links the backend evidence and integration conflicts.

## Scenarios, roles and local storage

Use the top-right **Demo controls** button for owner, editor, reviewer and read-only role previews, plus working, loading, empty and unavailable service scenarios. The working fixtures include failed execution, unknown outcomes, a partial pack, quarantined/ineligible media and unavailable metrics. Invalid timing, missing mandatory assets and budget caps block the relevant command with recovery guidance.

Owner is the default. Editor can draft/edit and authorise illustrative acquisition. Owner/reviewer can approve packages, review rights and prepare/record publication. Read-only can inspect. These are mock service restrictions, not production authentication.

Drafts autosave in versioned browser storage under `content-laboratory.operator-prototype.v1`. Saved revisions and simulated jobs survive refresh. Reset requires a separate confirmation and replaces local sample work. Invalid storage restores the fixture portfolio with a visible recovery notice. Scenario changes also replace the portfolio; export important handoffs before resetting.

## Preview and simulation limits

- Composition playback responds to local scene, object, geometry, text and timing edits. It uses whole frames and rational FPS. Reference video/audio audition is separate; canvas footage is muted and a mixed soundtrack is unavailable.
- Save revision freezes the plan. Saving an unchanged plan reuses its revision. Preview and generation pin immutable revisions; editing never rewrites earlier output descriptors. Changed copy/cover/disclosures require a new exact package approval.
- Simulated rendering creates a frozen descriptor, **not an encoded edited video**. Handoff JSON contains the edited composition, pinned representation/version provenance, copy, cover frame, disclosures and simulated review/approval records. It never substitutes unrelated footage for an edited final render.
- Structural validation runs locally. Pixel, audio, identity, provider, protected-region and compiled/measured media QA remain simulated or unevaluated. Prototype approval is an interface decision, not production clearance.
- Monetary amounts are illustrative GBP minor units. Jobs, costs, account names, schedules, publications, metrics and experiments are simulated. No provider/API/publishing traffic is used by the UI.
- Publication times use the selected IANA timezone; nonexistent and ambiguous daylight-saving times require a different time. The manual post reference is supplied by the operator and is not verified externally.
- Extended research, persistent characters, 3D production, localisation, production security, real rendering and publishing integration remain deferred pending workflow approval.

## Automated checks

From the repository root:

```powershell
pnpm lint
pnpm typecheck
pnpm test
pnpm --filter web build
```

With a separate local server on port 3000:

```powershell
pnpm --filter web test:e2e
```

Browser tests use installed Google Chrome. Set `PROTOTYPE_BROWSER_CHANNEL=msedge` to use installed Edge. Chrome/Edge is needed only for automated browser verification, not for running the application. No Python/backend tests are required by the frontend-only change.

Representative screenshots are generated locally into `outputs/prototype/` by running `node scripts/inspect-prototype.mjs` from `apps/web`. The final check results and screenshots are recorded in [UI_PROTOTYPE_VERIFICATION.md](UI_PROTOTYPE_VERIFICATION.md).

## Demonstration media

The SVG illustrations in `apps/web/public/demo` were newly authored for this prototype. The included kitchen source video animates the original kitchen illustration and includes synthetic Windows SAPI narration; it is a deliberately simple source-media fixture. The tone WAV is a synthetic audio fixture. No purchased, fetched or provider-generated media is required.

`apps/web/scripts/create-prototype-media.mjs` and `create-prototype-narration.ps1` document the optional local fixture preparation. The already bundled files are sufficient to run the UI; media preparation tools are not startup dependencies.
