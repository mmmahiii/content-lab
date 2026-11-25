# UI Plan — Content Lab rebuild (draft, 2026-11-24)

Status: proposal for review. Builds on `docs/REPO_MAP.md` (what exists) and borrows selectively
from the external *Content Laboratory Master Plan* (treated as input, not as a spec).

## 1. What we're building

Two products on one rendering engine:

| Surface | Who | Job | Feel |
|---------|-----|-----|------|
| **Studio** (operator console) | You, running many pages | Pages → asset packs → plans → review → ready-to-post → posted | Calm, dense, fast. A control room. |
| **Quick Reel** (standalone creator) | Anyone on the team, minimal effort | One idea in → a finished, postable reel out in under a minute, via a few fun choices | Feels like *watching* reels, not editing them. |

Both render reels the same way (Remotion, §2), so what you preview is exactly what exports.

## 2. Rendering: Remotion

### Why

- **Templates as React components.** Each content style (list, reveal, before/after, story,
  explainer) is a component that takes plan data as props. Variety = more components, not
  more FFmpeg filter strings.
- **Instant in-browser preview.** `@remotion/player` plays a reel from JSON props with no server
  render. This is what makes Quick Reel possible: every creative choice updates the video live.
- **Motion quality.** Kinetic captions, word-by-word highlights, transitions, progress bars —
  cheap in React, painful in FFmpeg.

### Architecture

```
Python pipeline (plan, assets, QA)          Web (Next.js)
        │  ReelTimeline JSON                   │
        ▼                                      ▼
 packages/reel-templates  (React + Remotion compositions; shared by both)
        │                                      │
        ▼                                      ▼
 render service (Node, @remotion/renderer)   <Player> live preview
        │  MP4
        ▼
 FFmpeg: normalise inputs, final encode checks, covers  →  existing package builder + QA
```

- **New package `packages/reel-templates`**: Remotion compositions + a typed `ReelTimeline` props
  schema (zod), generated from / kept in sync with the Python timeline model
  (`reel_timeline.json` already exists in the pipeline).
- **Render service**: small Node process that the worker calls with a timeline → returns an MP4
  into MinIO. Runs locally first; Remotion Lambda only if volume demands it.
- **FFmpeg stays** for input normalisation, probing, covers and encode validation. FFmpeg overlay
  rendering (`packages/editing/overlays.py` etc.) is retired template-by-template, not in one go.
- **QA**: overlay/timing checks currently read FFmpeg render traces. Each Remotion template must
  emit an equivalent render trace (text boxes, visible intervals) so `packages/qa` keeps working.

### Constraints to accept

- Remotion is free for individuals and companies up to 3 people; larger teams need a company
  licence. Re-check terms before commercial use.
- Server rendering is heavier than raw FFmpeg (headless Chromium). Fine for tens–low hundreds
  per day on one machine.

### First proof (before committing)

Port **one** existing reel (an existing `reel_timeline.json`) to a Remotion composition, render
both, compare side by side. Go / no-go on quality, render time and QA-trace parity.

## 3. Quick Reel — the hook-first creator

### Core idea

The user experiences their reel the way a viewer would: **the hook plays first**. Right when
curiosity peaks — the moment after the hook — the video pauses and offers a choice about *what
happens next*. Each choice instantly plays the next segment. The reel builds itself as they
watch. Finishing feels like reaching the payoff of a video they were already into.

### The flow

```
 ① Seed          ② Hook reel        ③ Cliffhanger       ④ Next beat      ⑤ The drop       ⑥ Ship
 one tap/line ─▶ swipe 3 hooks  ─▶  pause + 2–3     ─▶  plays with   ─▶  full reel     ─▶ export /
                 (feed gesture)     choice cards        choice baked    plays start     post / remix
                                    (repeat 2–3×)       in              to finish
```

1. **Seed** — never a blank form. One of: type a topic ("crispy potatoes"), drop a photo/asset,
   pick a page, or tap a suggested idea. That's the only typing in the whole flow.
2. **Hook reel** — full-screen vertical. Three hook variants autoplay; **swipe up for the next
   hook**, exactly like scrolling a feed. Tap to pick. (Swiping hooks is the native gesture of
   the medium; picking feels like "stopping on" a video you liked.)
3. **Cliffhanger pause** — the chosen hook plays to its last frame, then the frame dims and
   2–3 **choice cards** slide up. Each card is a looping 1–2 s mini-preview, not a text label.
   The question is framed as story, not settings: *"Where does this go?"*
4. **Next beat** — tapping a card continues the video immediately with that choice applied.
   Story-style progress bars at the top show how far into the reel they are (e.g. 3 segments).
   2–3 choice moments total — never more.
5. **The drop** — the finished reel replays start to finish, full sound, no UI. This is the
   payoff moment.
6. **Ship** — Download MP4 · Copy caption · Send to a page's Review queue · **Remix** (reshuffles
   the choices, keeps the hook) · Change one thing (jumps back to a specific choice).

### What the choices are

Tailored per reel, entertaining, and always *shown* not described. Draw from a small set of
dimensions; pick the 2–3 that matter most for this content:

| Moment | Example question | Options (each a mini-preview) |
|--------|------------------|-------------------------------|
| After hook | "Where does this go?" | The secret reveal · The 3-step breakdown · The fail first, then the fix |
| Mid-reel | "Pick the energy" | Chill & satisfying · Fast & chaotic · Dramatic slow-mo |
| Before payoff | "How does it end?" | Big reveal · Before/after split · Cliffhanger "part 2?" |
| Anytime (optional) | "Sound" | 3 music/sound vibes previewed in place |

These map onto existing concepts: narrative structure ↔ creative paths / blueprint, energy ↔
pacing + template variant, ending ↔ payoff/CTA beat. In code, each choice is just a prop change
on the Remotion composition.

### Design rules

- **Zero dead time.** Something is always playing. Loading states are motion, not spinners.
- **One tap per step.** Every step has a default; a "Surprise me" skips to the drop.
- **Under 60 seconds** from seed to finished reel.
- **Pre-fetch branches.** While the hook plays, generate the plan variants for every visible
  choice, so tapping a card plays instantly.
- **Mobile-first**, works on desktop as a centred phone-frame with keyboard (↑/↓ hooks,
  1/2/3 choices).
- **Engaging, not manipulative.** Exit and save are always visible; no fake countdowns, no
  streak guilt. The pull comes from the content, not from tricks.

### What it needs from the backend

| Need | Exists today? |
|------|---------------|
| 3 distinct hooks for a seed | **No** — requires a real LLM (scripts are templates today) |
| Branch variants per choice | **No** — same LLM; small, fast calls returning timeline JSON |
| Asset selection for a topic | Partly — asset registry + combinator; cooking-only content |
| Instant preview | New — Remotion Player from timeline props |
| Final MP4 + caption | New render service; caption variants exist |

Quick Reel runs in **existing-assets mode only** (no paid video generation) so each reel is
cheap and fast. Runway can be an opt-in "upgrade this shot" later.

**Hard dependency:** Quick Reel's whole premise (tailored hooks and choices) needs the LLM
integration. Until then it can be prototyped with canned hooks/choices on fixture timelines to
validate the feel.

## 4. Studio — operator console

Trimmed from the master plan's 11 workspaces to what the backend can actually support now.

### v1 workspaces

| Workspace | Shows / decides | Backed by (existing API) |
|-----------|-----------------|--------------------------|
| **Pages** | Your pages, niche, policy (with clear inheritance: global → niche → page), today's output | `pages`, `policy` |
| **Library** | Assets & packs: previews, status, usage, gaps; approve/reject packs | `assets`, `asset-packs/*` |
| **Create** | Pick page + pack + objective → plan → live Remotion preview → render | `idea-plans`, `cinematic-plan-*`, `runs` |
| **Review** | Queue of rendered reels: preview, QA findings in plain language, approve / send back | `reels/*`, `runs/{id}` |
| **Ready & Posted** | Approved packages, caption picker, download, "Record manual post" | `packages`, `mark-posted` |

### Later

Operations (runs, retries, budgets), Learning (performance, experiments), Opportunities
(trends) — once the performance-feedback loop exists.

### Principles (kept from the master plan — these are good)

- Action labels say what they do and cost: "Create preview", "Render approved revision",
  "Approve package", "Record manual post". No single ambiguous "Generate".
- Every view has real loading / empty / partial / failed states. Never fake numbers.
- Default view is the creative (video, hook, copy); IDs, hashes, traces sit behind "Details".
- Review on mobile is fine; precise editing is desktop.

## 5. Web stack

- Keep **Next.js 15** and the existing **API proxy routes** in `apps/web/app/api/`.
- **Tailwind + Radix primitives (shadcn-style)** for the Studio; **Framer Motion** for Quick Reel
  transitions and gestures.
- **TanStack Query** for server state; **zod** schemas shared with `reel-templates`.
- `apps/web` hosts both surfaces: `/studio/*` and `/make` (Quick Reel), sharing the design system
  and the Player.

## 6. Build order

| Step | Outcome | Depends on |
|------|---------|------------|
| 1 | Remotion proof: one existing reel ported, rendered, compared | — |
| 2 | Design system + app shell (`/studio`, `/make`) | — |
| 3 | Quick Reel prototype on fixture timelines (canned hooks/choices) — validates the feel | 1, 2 |
| 4 | LLM integration: hooks, branch variants, real scripts (backend) | — (parallel) |
| 5 | Studio v1: Pages → Library → Create → Review → Ready | 1, 2 |
| 6 | Quick Reel on real LLM output + render service export | 3, 4 |
| 7 | Retire FFmpeg overlay templates as Remotion equivalents pass QA | 1, 5 |

Steps 1–3 are pure UI/render work and can start now. Step 4 is the biggest unlock for both
surfaces and should start in parallel.

## 7. What we took from the master plan, and what we didn't

**Took:** the workspace list (trimmed), clear action labels, honest empty/partial states,
existing-assets mode first, no single "Generate" button, cheap previews before expensive
renders, manual ChatGPT import as a stopgap.

**Didn't take (yet):** scene inspector / semantic object edits, 3D, topic clipper,
opportunities/trend workspace, learning workspace, publishing adapters. All need backend
capabilities that don't exist.

## 8. Open decisions

1. ~~Who uses Quick Reel?~~ **Decided (2026-11-24): internal team only.** No public sign-up,
   billing or moderation. It sits inside the same app and login as Studio, reels can be saved
   to a page's Review queue, and team usage counts against the org's existing budget policy.
2. **Which LLM provider** for hooks and scripts (cost and speed matter: Quick Reel makes many
   small calls per reel).
3. **Niches beyond cooking** for the first Quick Reel templates — pick 2–3 so variety is real.
4. **Remotion licence** fit for how the business will be structured.
