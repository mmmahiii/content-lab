# Operator prototype review guide

Use this guide to review the principal workflows and information architecture before backend implementation. The application labels simulated service activity and uses sample brands, assets and observations. It is a working interface prototype, not an operating publishing or media-generation system.

See [local startup and five complete journeys](UI_PROTOTYPE_RUN.md) and [verification / screenshots](UI_PROTOTYPE_VERIFICATION.md).

## Workspace map

| Workspace      | Decisions to review                                                                                                                     |
| -------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| Content        | Find current work and open a story. Follow Brief → Hook & blueprint → Ingredients → Scene editor → Execution → Review → Publication.    |
| Pages          | Create a brand profile and production constraints; understand inherited policy and an explicit page override.                           |
| Ideas          | Evaluate evidence, freshness and page fit; create a brief, hold, reject or reconsider a suggestion.                                     |
| Asset Registry | Inspect readiness, rights, versions and representations; select eligible assets; register a sample asset and review it.                 |
| Asset packs    | Plan a count and mix, inspect acquisition routes and cost, authorise, fulfil, repair failures or use a ready subset.                    |
| Review         | Investigate failed or unevaluated checks, compare candidate output and approve/reject an exact package.                                 |
| Publication    | Prepare an approved package, select handoff details and separately confirm a simulated manual post.                                     |
| Operations     | Inspect stages, attempts and costs; distinguish a known execution failure from an unknown provider outcome.                             |
| Learning       | Record sample metrics, distinguish missing observations from zero, compare content in an experiment and review shadow policy proposals. |

## Suggested review journeys

### 1. Establish a recognisable page

Open **Pages** and inspect Object Stories, Everyday Explained and Weeknight Table. Edit a profile's audience, purpose, voice, topics and required disclosures. Compare the inherited production budget with an explicit page override. Create another page, including its locale and format.

Consider whether this is enough brand context to guide your creative choices. Sample spending limits are prototype defaults, not recommendations for a real pilot budget.

### 2. Turn an idea into an editable story

Open **Ideas**. Filter by page, inspect the source/evidence note and freshness, and put a suggestion on hold. Reconsider it and create a brief. An expired opportunity should explain why creating a brief is blocked.

Use **New idea** to enter your own premise, evidence note, page fit, freshness and production family. Creating a brief carries that editorial context forward.

In the resulting content detail, edit the objective, audience takeaway, claims, evidence and payoff. Choose a hook and blueprint. Inspect the ingredients and distinguish optional selected assets from mandatory assets that must appear in the composition.

### 3. Create with known ingredients

Open **Asset Registry**. Filter for ready, eligible assets and inspect a current representation, rights note and version history. Select a useful group and choose the target page. Create content from that selection.

Register a sample asset to exercise intake. Its record starts without an eligible production representation. Use an authorised review role to inspect the source note and decide whether it may be used. This is simulated intake; the form does not upload a real file.

### 4. Plan and fulfil a partial asset pack

Open **Asset packs**. Specify a page, count, mix, style and budget. Review the proposed items, the reason for each and the acquisition route. Planning should not acquire anything.

Authorise the visible scope, then fulfil it. Inspect the resulting item states and any failure or gap. Try creating from the ready eligible subset. Retry a failed item only after seeing the additional cost and unresolved condition. Confirm that partial fulfilment never implies every requested asset is available.

### 5. Inspect and change a scene

Open a content item's **Scene editor**. Scrub the timeline, select a scene, inspect its purpose and select an object. Make a visible text, position, size, layer or timing edit. Preview the change and compare it with the saved revision.

Try selecting a replacement asset for an instance and identify which properties should remain unchanged. Inspect supported route information and candidate findings. The intended review boundary is a changed candidate or revision; previously approved package content must remain stable.

### 6. Investigate a failed output

Use **Operations** or the content **Execution** tab to inspect a failed or unknown-outcome run. Read its stage, attempt and cost breakdown. A normal retry and reconciliation of an unknown provider outcome should have different meanings.

Use the associated QA finding to locate the affected scene/object or missing artifact. Distinguish repairing the creative plan from retrying an execution failure. Required checks that were not evaluated must remain visible; they are not successful checks.

### 7. Review, approve and prepare publication

Open **Review** and inspect the exact output and its copy. Compare a candidate when available. Approve a package only when the required findings permit it, or reject it with a reason.

Make a subsequent creative change and confirm that the old approval still describes the old revision. Prepare publication from an approved package. Export the prototype handoff, if desired, and inspect its actual contents. It contains the edited plan and simulated records, not a fabricated final movie.

Record a sample manual post reference and timestamp as a separate action. Downloading or preparing a package must not silently mark it as published. Publisher integration remains unavailable in this prototype.

### 8. Observe before learning

Open **Learning**. Compare rows with missing metrics, explicitly observed zero values and provisional or mature windows. Record a sample metric observation against a confirmed simulated post; leave retention blank when unknown.

Create an experiment with at least two variants from the same page, a primary metric, observation window and stopping rule. Review its current conclusion without assuming the prototype establishes a winner. Accept or dismiss a learning proposal in shadow mode and confirm that doing so does not change production policy.

## Edge-state review

Open **Demo controls** to change the preview role and service scenario. These controls are for exploring the prototype, not production account management.

- **Loading:** workspace skeletons explain the pending state and provide a route back to the working portfolio.
- **Empty:** create the first page or start the next useful step; missing collections do not display fabricated performance.
- **Unavailable:** a simulated service failure offers an explicit recovery action.
- **Validation:** submit missing or incompatible values, such as an invalid mix or unsupported comparison, and inspect the field-level explanation.
- **Blocked:** select an ineligible or missing mandatory ingredient, inspect a failed requirement or try to publish without exact approval.
- **Partial/failed:** inspect pack gaps and a failed execution attempt without assuming the entire workflow succeeded.
- **Permission limited:** use editor, reviewer and read-only roles. Creation, review and publication decisions should expose their required authority.

Resetting the demo replaces locally edited sample data. Use the explicit reset control when you want to return to the original portfolio.

## Major UX choices to assess

- One global production workspace with page-aware content, rather than separate disconnected tools per generation mode.
- A structured content detail flow from intent through editing and execution to exact review and publication.
- A media-first editor with technical identifiers behind an inspection surface; raw JSON is not required for the main journey.
- Assets, asset versions, representations and scene instances are distinct concepts so readiness, rights and edits can be inspected at the level that matters.
- Separate actions for planning, acquisition authorisation, fulfilment, preview, rendering, package approval and post confirmation.
- Partial packs are useful when their ready subset supports a composition. Mandatory selected objects are constraints, not suggestions.
- Local composition controls are interactive; provider outcomes, cost accounting and performance observations are explicitly simulated.
- Learning is observational and human-reviewed. Missing data, immature windows and causal uncertainty remain visible.

## Questions requiring product judgement

1. Does the global navigation match how you organise daily production, or should the page be a stronger, persistent context across all workspaces?
2. Are the brand fields sufficient for your actual editorial choices? Which constraints must be required before the first preview?
3. Do the hook/blueprint and scene-editing controls cover the changes you make most often, or is an additional high-frequency editing action missing?
4. What acquisition scope should an editor be permitted to authorise, and when should a separate reviewer or owner be required?
5. Is exact package approval the right boundary for copy, cover and disclosures, or do you need separately scoped approvals for any of them?
6. Which performance metrics and observation windows should be primary for your first real page and experiment?
7. Does the preview/review distinction communicate the cost and confidence of the next step clearly enough?
8. Which real brands and first platform (Instagram, TikTok, YouTube Shorts or another destination) should drive the pilot fixtures and publishing requirements?
9. What per-page and per-acquisition pilot budgets should replace the illustrative GBP amounts?
10. Is lightweight frame/position editing sufficient, or do you need precise masks, keyframes, audio mixing or other controls before reviewing backend integration?

This guide describes review scenarios. It is not a claim that all scenarios were browser-tested. The integrated delivery report should identify the checks actually performed and their results.
