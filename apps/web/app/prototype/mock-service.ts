import {
  canEdit,
  canReview,
  type AssetKind,
  type Command,
  type CommandResult,
  type Composition,
  type ContentItem,
  type Family,
  type Finding,
  type OperatorService,
  type PackageRecord,
  type PackItem,
  type Revision,
  type Run,
  type Scenario,
  type WorkspaceState,
} from './domain';
import { createFixtureComposition, createFixtureState } from './fixtures';
import { validateComposition } from './validation';

export const PROTOTYPE_STORAGE_KEY = 'content-laboratory.operator-prototype.v1';
type StorageLike = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;
interface Options {
  storage?: StorageLike;
  latencyMs?: number;
  now?: () => number;
}
interface Persisted {
  state: WorkspaceState;
  packDeadlines: Record<string, number>;
}
const clone = <T>(value: T): T => JSON.parse(JSON.stringify(value)) as T;
const money = (minor: number) => ({ minor, currency: 'GBP' as const });
const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);
const roles = ['owner', 'editor', 'reviewer', 'viewer'];
const scenarios = ['portfolio', 'empty', 'unavailable', 'loading'];
const isWhole = (n: number) => Number.isSafeInteger(n) && n >= 0;

class ServiceFailure extends Error {
  constructor(
    public kind: 'validation' | 'blocked' | 'permission' | 'failed',
    message: string,
    public fields?: Record<string, string>,
  ) {
    super(message);
  }
}
function requireValue<T>(value: T | null | undefined, message: string): T {
  if (value === undefined || value === null) throw new ServiceFailure('validation', message);
  return value;
}

/** Entirely local mock boundary. It makes no HTTP, provider, storage-upload or publishing calls. */
export function createMockOperatorService(options: Options = {}): OperatorService {
  const now = options.now ?? Date.now;
  const latency = options.latencyMs ?? 180;
  let storage = options.storage;
  try {
    if (!storage && typeof window !== 'undefined') storage = window.localStorage;
  } catch {
    /* In-memory mode remains usable. */
  }
  let state = createFixtureState('portfolio', now());
  let packDeadlines: Record<string, number> = {};
  let initialized = false;
  let disposed = false;
  let sequence = 0;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let queue: Promise<unknown> = Promise.resolve();
  const listeners = new Set<(snapshot: WorkspaceState) => void>();
  const delay = (ms: number) =>
    ms > 0 ? new Promise<void>((resolve) => setTimeout(resolve, ms)) : Promise.resolve();
  const timestamp = () => new Date(now()).toISOString();
  const fail = (
    kind: ServiceFailure['kind'],
    message: string,
    fields?: Record<string, string>,
  ): never => {
    throw new ServiceFailure(kind, message, fields);
  };
  const findContent = (id: string) =>
    requireValue(
      state.contents.find((c) => c.id === id),
      'This content item is unavailable.',
    );
  const findPage = (id: string) =>
    requireValue(
      state.pages.find((p) => p.id === id),
      'Choose an available page.',
    );
  const findRun = (id: string) =>
    requireValue(
      state.runs.find((r) => r.id === id),
      'This execution is unavailable.',
    );
  const findPackage = (id: string) =>
    requireValue(
      state.packages.find((p) => p.id === id),
      'This package is unavailable.',
    );
  const id = (prefix: string): string => {
    let value: string;
    const all = Object.values(state)
      .flatMap((v) => (Array.isArray(v) ? v : []))
      .filter((v) => v && typeof v === 'object' && 'id' in v);
    do {
      value = `${prefix}-${now()}-${++sequence}`;
    } while (all.some((v) => v.id === value));
    return value;
  };
  const snapshot = () => clone(state);
  const persist = () => {
    if (!storage) return;
    try {
      storage.setItem(
        PROTOTYPE_STORAGE_KEY,
        JSON.stringify({ state, packDeadlines } satisfies Persisted),
      );
    } catch {
      state.recoveryNotice =
        'Browser storage is unavailable. Changes remain usable in this tab but will not survive a reload.';
    }
  };
  const notify = () => {
    for (const listener of listeners) {
      try {
        listener(snapshot());
      } catch {
        /* A view cannot interrupt service progress. */
      }
    }
  };
  const validState = (value: unknown): value is WorkspaceState => {
    if (!value || typeof value !== 'object') return false;
    const candidate = value as WorkspaceState;
    return (
      candidate.schemaVersion === 1 &&
      roles.includes(candidate.role) &&
      scenarios.includes(candidate.scenario) &&
      [
        'pages',
        'ideas',
        'assets',
        'assetVersions',
        'representations',
        'hooks',
        'blueprints',
        'contents',
        'revisions',
        'runs',
        'packages',
        'publications',
        'packs',
        'metrics',
        'experiments',
        'suggestions',
      ].every((key) => Array.isArray((candidate as unknown as Record<string, unknown>)[key])) &&
      candidate.contents.every((c) => c.id && c.draft?.scenes && c.draft?.brief) &&
      candidate.runs.every((r) => r.id && r.estimate && r.reserved && r.spent && r.uncertain)
    );
  };
  const initialize = () => {
    if (initialized) return;
    initialized = true;
    if (!storage) return;
    try {
      const raw = storage.getItem(PROTOTYPE_STORAGE_KEY);
      if (!raw) return;
      const data = JSON.parse(raw) as Persisted;
      if (!validState(data.state)) throw new Error('Invalid stored schema');
      state = data.state;
      packDeadlines =
        data.packDeadlines && typeof data.packDeadlines === 'object' ? data.packDeadlines : {};
    } catch {
      state = createFixtureState('portfolio', now());
      state.recoveryNotice =
        'Saved prototype data could not be read. A fresh illustrative portfolio has been restored.';
      packDeadlines = {};
    }
  };
  const assertPermission = (command: Command) => {
    if (command.type === 'setRole') return;
    const review = [
      'approvePackage',
      'rejectPackage',
      'reviewAsset',
      'reviewSuggestion',
      'preparePublication',
      'recordPost',
    ].includes(command.type);
    if (review ? !canReview(state.role) : !canEdit(state.role))
      fail(
        'permission',
        review
          ? 'Package and rights decisions require an owner or reviewer role. Change the simulated role to review this decision.'
          : 'This action requires an owner or editor role. The current simulated role can inspect this workspace.',
      );
  };
  const structuralFailures = (composition: Composition): Finding[] =>
    validateComposition(composition, state).filter((f) => f.severity === 'fail');
  const assertComposition = (composition: Composition) => {
    const failures = structuralFailures(composition);
    if (failures.length)
      fail(
        'blocked',
        failures[0].title + ': ' + failures[0].detail,
        Object.fromEntries(
          failures.map((f) => [f.instanceId ?? f.sceneId ?? f.category, f.detail]),
        ),
      );
  };
  const saveRevision = (content: ContentItem, preview = false, force = false): Revision => {
    const current = state.revisions.find((r) => r.id === content.currentRevisionId);
    if (
      !force &&
      current &&
      same(current.composition, content.draft) &&
      (!preview || current.previewCreated)
    )
      return current;
    const revision: Revision = {
      id: id('revision'),
      contentId: content.id,
      number:
        Math.max(
          0,
          ...state.revisions.filter((r) => r.contentId === content.id).map((r) => r.number),
        ) + 1,
      ...(current ? { parentId: current.id } : {}),
      createdAt: timestamp(),
      composition: clone(content.draft),
      previewCreated: preview,
    };
    state.revisions.push(revision);
    content.currentRevisionId = revision.id;
    content.updatedAt = timestamp();
    return revision;
  };
  const draftMatches = (pkg: PackageRecord) => {
    const content = findContent(pkg.contentId);
    const revision = requireValue(
      state.revisions.find((r) => r.id === pkg.revisionId),
      'The package revision is missing.',
    );
    if (!same(content.draft, revision.composition) || content.currentRevisionId !== revision.id)
      fail(
        'blocked',
        'This package belongs to an earlier content revision. Render and approve the current draft before preparing publication.',
      );
    if (
      pkg.copy !== revision.composition.caption ||
      pkg.disclosures !== revision.composition.disclosures ||
      pkg.coverFrame !== revision.composition.coverFrame
    )
      fail(
        'blocked',
        'Package copy, disclosures or cover no longer match the pinned revision. A new package and approval are required.',
      );
    return revision;
  };
  const pageCommitted = (pageId: string) =>
    state.runs
      .filter((r) => findContent(r.contentId).pageId === pageId)
      .reduce((sum, r) => sum + r.spent.minor + r.reserved.minor + r.uncertain.minor, 0);
  const assertBudget = (pageId: string, additional: number) => {
    const page = findPage(pageId);
    if (!isWhole(additional))
      fail('validation', 'Cost must be a nonnegative whole number of pence.');
    const available = Math.max(0, page.budgetMinor - pageCommitted(pageId));
    if (additional > available)
      fail(
        'blocked',
        `This action needs £${(additional / 100).toFixed(2)}; only £${(available / 100).toFixed(2)} remains after spend, reservations and uncertain charges. Adjust the page budget or reconcile an unknown result.`,
      );
  };
  const estimateFor = (composition: Composition, kind: Run['kind']) =>
    Math.ceil(
      ((composition.totalFrames * composition.fps.denominator) / composition.fps.numerator) *
        (kind === 'candidate' ? 2 : 1.5),
    ) + 12;
  const startRun = (content: ContentItem, revision: Revision, kind: Run['kind'], attempt = 1) => {
    assertComposition(revision.composition);
    if (
      state.runs.some(
        (r) =>
          r.contentId === content.id && ['queued', 'running', 'outcome_unknown'].includes(r.status),
      )
    )
      fail(
        'blocked',
        'An execution is already active or has an unknown outcome for this content. Wait for it or reconcile it before submitting another.',
      );
    const estimate = estimateFor(revision.composition, kind);
    assertBudget(content.pageId, estimate);
    const run: Run = {
      id: id('run'),
      contentId: content.id,
      revisionId: revision.id,
      status: 'queued',
      kind,
      attempt,
      stages: [
        'Validate pinned inputs',
        kind === 'candidate' ? 'Compose comparison candidate' : 'Compose browser preview',
        'Run local structural QA',
      ].map((name) => ({
        name,
        status: 'pending',
        detail: 'Simulated execution; no provider request or encoded export.',
      })),
      estimate: money(estimate),
      reserved: money(estimate),
      spent: money(0),
      uncertain: money(0),
      createdAt: timestamp(),
      completesAt: now() + 4000,
    };
    state.runs.push(run);
    content.stage = 'in_progress';
    content.updatedAt = timestamp();
    return run;
  };
  const finishRun = (run: Run) => {
    const content = findContent(run.contentId);
    const revision = requireValue(
      state.revisions.find((r) => r.id === run.revisionId),
      'The run revision is unavailable.',
    );
    const findings = validateComposition(revision.composition, state);
    const blocked = findings.some((f) => f.severity === 'fail');
    run.status = blocked ? 'failed' : 'succeeded';
    run.spent = money(
      Math.min(
        run.estimate.minor,
        Math.max(1, Math.round(run.estimate.minor * (blocked ? 0.2 : 0.85))),
      ),
    );
    run.reserved = money(0);
    run.uncertain = money(0);
    delete run.completesAt;
    run.stages = run.stages.map((stage, index) => ({
      ...stage,
      status: blocked && index === run.stages.length - 1 ? 'failed' : 'succeeded',
      detail:
        blocked && index === run.stages.length - 1
          ? 'Local structural checks found a blocker.'
          : index === run.stages.length - 1
            ? 'Local structural checks completed. Identity and encoded media remain unmeasured.'
            : 'Simulated execution complete; no encoded video was created.',
    }));
    if (blocked) run.error = findings.find((f) => f.severity === 'fail')?.detail;
    else delete run.error;
    if (!state.packages.some((p) => p.runId === run.id))
      state.packages.push({
        id: id('package'),
        contentId: content.id,
        revisionId: revision.id,
        runId: run.id,
        status: 'review',
        findings,
        copy: revision.composition.caption,
        disclosures: revision.composition.disclosures,
        coverFrame: revision.composition.coverFrame,
      });
    if (content.currentRevisionId === revision.id && same(content.draft, revision.composition))
      content.stage = blocked ? 'blocked' : 'review';
  };
  const sampleAsset = (kind: AssetKind) =>
    state.assets.find(
      (a) =>
        a.kind === kind &&
        state.representations.some(
          (r) =>
            r.assetVersionId === a.currentVersionId &&
            r.rights === 'eligible' &&
            r.readiness === 'ready',
        ),
    );
  const finishPack = (packId: string) => {
    const pack = state.packs.find((p) => p.id === packId);
    if (!pack) return;
    for (const item of pack.items.filter((i) => i.status === 'processing')) {
      const asset = sampleAsset(item.kind);
      if (!asset) {
        item.status = 'failed';
        item.error =
          'No ready local demo asset can represent this need. Register or select an eligible asset; no placeholder was produced.';
      } else {
        item.assetId = asset.id;
        item.status = 'ready';
        delete item.error;
        item.reason += ' Fulfilment simulated using an explicitly identified existing demo asset.';
      }
    }
    pack.status = pack.items.every((i) => i.status === 'ready') ? 'ready' : 'partial';
    delete packDeadlines[pack.id];
  };
  const settle = () => {
    let changed = false;
    for (const run of state.runs) {
      if (!['queued', 'running'].includes(run.status) || run.completesAt === undefined) continue;
      if (now() >= run.completesAt) {
        finishRun(run);
        changed = true;
      } else {
        const progress = Math.max(
          0,
          Math.min(
            0.99,
            1 -
              (run.completesAt - now()) / Math.max(1, run.completesAt - Date.parse(run.createdAt)),
          ),
        );
        const active = Math.min(run.stages.length - 1, Math.floor(progress * run.stages.length));
        const next = run.stages.map((s, i) => ({
          ...s,
          status:
            i < active
              ? ('succeeded' as const)
              : i === active
                ? ('running' as const)
                : ('pending' as const),
        }));
        if (run.status !== 'running' || !same(next, run.stages)) {
          run.status = 'running';
          run.stages = next;
          changed = true;
        }
      }
    }
    for (const [packId, deadline] of Object.entries(packDeadlines))
      if (now() >= deadline) {
        finishPack(packId);
        changed = true;
      }
    if (changed) {
      persist();
      notify();
    }
    return changed;
  };
  const schedule = () => {
    if (timer) clearTimeout(timer);
    if (disposed || !listeners.size || state.scenario === 'unavailable') return;
    if (
      state.runs.some(
        (r) => ['queued', 'running'].includes(r.status) && r.completesAt !== undefined,
      ) ||
      Object.keys(packDeadlines).length
    ) {
      timer = setTimeout(() => {
        settle();
        schedule();
      }, 250);
    }
  };
  const operation = (command: Command): { message: string; entityId?: string } => {
    if (command.type === 'setRole') {
      if (!roles.includes(command.role)) fail('validation', 'Choose a supported simulated role.');
      state.role = command.role;
      return { message: `Simulated role changed to ${command.role}.` };
    }
    if (state.scenario === 'unavailable')
      fail(
        'failed',
        'The mock workspace is unavailable in this scenario. Reset to Portfolio to recover.',
      );
    switch (command.type) {
      case 'savePage': {
        const page = clone(command.page);
        if (!page.name.trim() || !page.purpose.trim() || !page.audience.trim())
          fail('validation', 'Add the page name, purpose and intended audience.', {
            name: !page.name.trim() ? 'Name is required.' : '',
            purpose: !page.purpose.trim() ? 'Purpose is required.' : '',
            audience: !page.audience.trim() ? 'Audience is required.' : '',
          });
        if (!isWhole(page.budgetMinor))
          fail('validation', 'Budget must be a nonnegative amount in whole pence.', {
            budgetMinor: 'Use a nonnegative amount with at most two decimal places.',
          });
        if (!page.locale.trim())
          fail('validation', 'Choose a locale.', { locale: 'Locale is required.' });
        if (page.id && !state.pages.some((p) => p.id === page.id))
          fail('validation', 'This page no longer exists.');
        if (!page.id) page.id = id('page');
        const index = state.pages.findIndex((p) => p.id === page.id);
        if (index >= 0) state.pages[index] = page;
        else state.pages.push(page);
        return {
          message: 'Page profile saved locally. Budget and policy are simulated.',
          entityId: page.id,
        };
      }
      case 'setIdeaStatus': {
        const idea = requireValue(
          state.ideas.find((i) => i.id === command.ideaId),
          'This idea is unavailable.',
        );
        idea.status = command.status;
        return { message: `Idea marked ${command.status}.`, entityId: idea.id };
      }
      case 'createContent': {
        findPage(command.pageId);
        const idea = command.ideaId
          ? requireValue(
              state.ideas.find((i) => i.id === command.ideaId),
              'This idea is unavailable.',
            )
          : undefined;
        if (idea && idea.pageId !== command.pageId)
          fail('validation', 'The idea belongs to another page.');
        if (idea?.freshness === 'expired')
          fail(
            'blocked',
            'This opportunity has expired. Review its evidence and freshness before starting production.',
          );
        const family: Family =
          command.family ??
          idea?.family ??
          (command.pageId === 'page-table'
            ? 'video'
            : command.pageId === 'page-explained'
              ? 'graphic'
              : 'product');
        const draft = createFixtureComposition(family, command.title?.trim() || idea?.title);
        let selected = command.assetIds;
        if (command.packId) {
          const pack = requireValue(
            state.packs.find((p) => p.id === command.packId),
            'This pack is unavailable.',
          );
          if (pack.pageId !== command.pageId)
            fail('validation', 'This pack belongs to another page.');
          selected = pack.items
            .filter((i) => i.status === 'ready' && i.assetId)
            .map((i) => i.assetId!);
          if (!selected.length)
            fail(
              'blocked',
              'This pack has no ready ingredients. Fulfil or select an eligible asset first.',
            );
        }
        if (selected?.length) {
          selected.forEach((assetId) =>
            requireValue(
              state.assets.find((a) => a.id === assetId),
              'A selected asset is unavailable.',
            ),
          );
          draft.selectedAssets = selected.map((assetId) => ({ assetId, mandatory: false }));
          const heroId = selected.find(
            (assetId) =>
              state.assets.find((a) => a.id === assetId)?.kind ===
              (family === 'video' ? 'footage' : family === 'graphic' ? 'graphic' : 'product'),
          );
          if (heroId) {
            const asset = state.assets.find((a) => a.id === heroId)!;
            const rep = state.representations.find(
              (r) =>
                r.assetVersionId === asset.currentVersionId &&
                (family === 'video' ? r.mediaType === 'video' : r.mediaType === 'image'),
            );
            if (rep)
              for (const scene of draft.scenes)
                for (const instance of scene.instances.filter((i) => i.id.endsWith('-subject')))
                  Object.assign(instance, {
                    assetId: asset.id,
                    assetVersionId: asset.currentVersionId,
                    representationId: rep.id,
                    name: asset.name,
                  });
            draft.selectedAssets.find((s) => s.assetId === heroId)!.mandatory = true;
          }
        }
        const content: ContentItem = {
          id: id('content'),
          pageId: command.pageId,
          family,
          draft,
          stage: structuralFailures(draft).length ? 'blocked' : 'draft',
          updatedAt: timestamp(),
        };
        state.contents.unshift(content);
        if (idea) idea.status = 'drafted';
        return {
          message:
            'Draft created. Review the brief, mandatory ingredients and local checks before previewing.',
          entityId: content.id,
        };
      }
      case 'updateDraft': {
        const content = findContent(command.contentId);
        if (!command.draft || !Array.isArray(command.draft.scenes) || !command.draft.brief)
          fail('validation', 'The draft must contain a brief and scene list.');
        if (same(content.draft, command.draft))
          return { message: 'This draft is already saved.', entityId: content.id };
        content.draft = clone(command.draft);
        content.updatedAt = timestamp();
        content.stage = structuralFailures(content.draft).length ? 'blocked' : 'draft';
        return {
          message:
            'Draft saved locally. Existing packages still point to their original frozen revisions.',
          entityId: content.id,
        };
      }
      case 'saveRevision': {
        const content = findContent(command.contentId);
        if (!content.draft.title.trim()) fail('validation', 'Give this revision a title.');
        const revision = saveRevision(content, false, true);
        return {
          message: `Revision ${revision.number} saved as an immutable snapshot.`,
          entityId: revision.id,
        };
      }
      case 'createPreview': {
        const content = findContent(command.contentId);
        assertComposition(content.draft);
        const revision = saveRevision(content, true);
        return {
          message: `Browser preview created for revision ${revision.number}. No paid generation or final encoding occurred.`,
          entityId: revision.id,
        };
      }
      case 'renderRevision':
      case 'newCandidate': {
        const content = findContent(command.contentId);
        assertComposition(content.draft);
        const revision = saveRevision(content, false);
        const run = startRun(
          content,
          revision,
          command.type === 'newCandidate' ? 'candidate' : 'render',
        );
        return {
          message: `${command.type === 'newCandidate' ? 'Comparison candidate' : 'Render'} simulation queued with frozen revision ${revision.number}. £${(run.reserved.minor / 100).toFixed(2)} reserved in the illustrative budget.`,
          entityId: run.id,
        };
      }
      case 'repairPlan': {
        const content = findContent(command.contentId);
        const composition = clone(content.draft);
        if (!composition.scenes.length)
          fail('blocked', 'Add a scene before requesting a structural repair.');
        let cursor = 0;
        for (const scene of composition.scenes) {
          const span = Math.max(30, Math.round(scene.endFrame - scene.startFrame) || 30);
          const shift = cursor - scene.startFrame;
          scene.startFrame = cursor;
          scene.endFrame = cursor + span;
          cursor += span;
          for (const item of scene.instances) {
            item.startFrame = Math.max(
              scene.startFrame,
              Math.min(scene.endFrame - 1, Math.round(item.startFrame + shift)),
            );
            item.endFrame = Math.max(
              item.startFrame + 1,
              Math.min(scene.endFrame, Math.round(item.endFrame + shift)),
            );
            item.width = Math.max(0.02, Math.min(1, item.width));
            item.height = Math.max(0.02, Math.min(1, item.height));
            item.x = Math.max(0, Math.min(1 - item.width, item.x));
            item.y = Math.max(0, Math.min(1 - item.height, item.y));
            item.opacity = Math.max(0, Math.min(1, item.opacity));
          }
          for (const audio of scene.audio) {
            audio.startFrame = scene.startFrame;
            audio.endFrame = scene.endFrame;
          }
        }
        composition.totalFrames = cursor;
        composition.coverFrame = Math.max(0, Math.min(cursor - 1, composition.coverFrame));
        if (same(composition, content.draft))
          fail(
            'blocked',
            'No safe structural repair is available. Rights, missing assets and editorial choices require an operator decision.',
          );
        content.draft = composition;
        content.stage = structuralFailures(composition).length ? 'blocked' : 'draft';
        content.updatedAt = timestamp();
        const revision = saveRevision(content, false, true);
        return {
          message:
            'Saved a new revision with contiguous scenes and bounded object positions. Rights and missing-media blockers still require review.',
          entityId: revision.id,
        };
      }
      case 'retryRun': {
        const previous = findRun(command.runId);
        if (previous.status === 'outcome_unknown')
          fail(
            'blocked',
            'Reconcile the unknown provider outcome before retrying. A second submission could duplicate the result or charge.',
          );
        if (previous.status !== 'failed')
          fail('blocked', 'Only a failed execution can be retried.');
        const revision = requireValue(
          state.revisions.find((r) => r.id === previous.revisionId),
          'Pinned revision missing.',
        );
        const run = startRun(
          findContent(previous.contentId),
          revision,
          previous.kind,
          previous.attempt + 1,
        );
        return {
          message:
            'Retry queued using the same frozen creative revision. A separate attempt and reservation were recorded.',
          entityId: run.id,
        };
      }
      case 'reconcileRun': {
        const run = findRun(command.runId);
        if (run.status !== 'outcome_unknown')
          fail('blocked', 'This execution does not need unknown-outcome reconciliation.');
        finishRun(run);
        return {
          message:
            'Simulated reconciliation found the existing result. The uncertain amount was settled without another submission.',
          entityId: run.id,
        };
      }
      case 'approvePackage': {
        const pkg = findPackage(command.packageId);
        if (pkg.status === 'approved') fail('blocked', 'This exact package is already approved.');
        const revision = draftMatches(pkg);
        const run = findRun(pkg.runId);
        if (run.status !== 'succeeded')
          fail('blocked', 'The package execution must succeed before approval.');
        const findings = validateComposition(revision.composition, state);
        if ([...pkg.findings, ...findings].some((f) => f.severity === 'fail'))
          fail(
            'blocked',
            'This package has blocking QA or rights findings. Repair the draft and produce a new package.',
          );
        const page = findPage(findContent(pkg.contentId).pageId);
        if (page.disclosures.trim() && !pkg.disclosures.includes(page.disclosures.trim()))
          fail(
            'blocked',
            'The package is missing the required page disclosure. Update the draft and render a new revision.',
          );
        pkg.status = 'approved';
        pkg.approvalId = id('approval');
        pkg.approvedBy = state.role;
        pkg.approvedAt = timestamp();
        delete pkg.rejectionReason;
        findContent(pkg.contentId).stage = 'approved';
        return {
          message:
            'Prototype package approved for its exact revision, copy, disclosures and cover. Encoded-media and identity checks remain explicitly unmeasured.',
          entityId: pkg.id,
        };
      }
      case 'rejectPackage': {
        const pkg = findPackage(command.packageId);
        if (!command.reason.trim())
          fail('validation', 'Add a reason so the next revision can address it.', {
            reason: 'A rejection reason is required.',
          });
        if (pkg.status === 'approved')
          fail(
            'blocked',
            'This package already has an exact approval. Create a changed draft and a new package; the historical approval is retained.',
          );
        pkg.status = 'rejected';
        pkg.rejectionReason = command.reason.trim();
        findContent(pkg.contentId).stage = 'draft';
        return {
          message: 'Package rejected with a review note. Its frozen revision remains available.',
          entityId: pkg.id,
        };
      }
      case 'preparePublication': {
        const pkg = findPackage(command.packageId);
        draftMatches(pkg);
        if (pkg.status !== 'approved' || !pkg.approvalId)
          fail('blocked', 'Approve this exact package before preparing publication.');
        if (
          validateComposition(
            requireValue(
              state.revisions.find((r) => r.id === pkg.revisionId),
              'Revision missing.',
            ).composition,
            state,
          ).some((f) => f.severity === 'fail')
        )
          fail(
            'blocked',
            'Media readiness or rights have changed since approval. Resolve the new blocker before publication.',
          );
        if (!command.account.trim())
          fail('validation', 'Choose the destination account.', {
            account: 'Account is required.',
          });
        try {
          new Intl.DateTimeFormat('en-GB', { timeZone: command.timezone }).format(new Date());
        } catch {
          fail('validation', 'Use a valid IANA timezone, such as Europe/London.', {
            timezone: 'Timezone is invalid.',
          });
        }
        if (
          command.scheduledAt &&
          (!Number.isFinite(Date.parse(command.scheduledAt)) ||
            Date.parse(command.scheduledAt) <= now())
        )
          fail('validation', 'Choose a future publication time.', {
            scheduledAt: 'Schedule must be a valid future date.',
          });
        const existing = state.publications.find(
          (p) =>
            p.packageId === pkg.id &&
            p.account === command.account.trim() &&
            p.status !== 'published',
        );
        if (existing) {
          existing.timezone = command.timezone;
          existing.scheduledAt = command.scheduledAt;
          existing.status = command.scheduledAt ? 'scheduled' : 'prepared';
          return {
            message:
              'Manual publication preparation updated. The schedule is a local reminder record only.',
            entityId: existing.id,
          };
        }
        const publication = {
          id: id('publication'),
          packageId: pkg.id,
          contentId: pkg.contentId,
          approvalId: requireValue(pkg.approvalId, 'An exact approval is required.'),
          account: command.account.trim(),
          timezone: command.timezone,
          scheduledAt: command.scheduledAt,
          status: command.scheduledAt ? ('scheduled' as const) : ('prepared' as const),
          simulated: true as const,
        };
        state.publications.push(publication);
        return {
          message: 'Manual handoff prepared. No account was contacted and nothing has been posted.',
          entityId: publication.id,
        };
      }
      case 'recordPost': {
        const publication = requireValue(
          state.publications.find((p) => p.id === command.publicationId),
          'Prepare publication before recording a post.',
        );
        const pkg = findPackage(publication.packageId);
        draftMatches(pkg);
        if (pkg.status !== 'approved' || pkg.approvalId !== publication.approvalId)
          fail('blocked', 'This handoff no longer has a matching exact approval.');
        if (publication.status === 'published')
          fail('blocked', 'A post is already recorded for this handoff.');
        if (!command.externalReference.trim())
          fail('validation', 'Enter the actual external post ID or reference.', {
            externalReference: 'External post reference is required.',
          });
        const postedTime = Date.parse(command.postedAt);
        if (!Number.isFinite(postedTime) || postedTime > now())
          fail('validation', 'Enter the actual posting time, at or before now.', {
            postedAt: 'Posting time must be a valid past or current timestamp.',
          });
        if (
          state.publications.some(
            (p) =>
              p.account === publication.account &&
              p.externalReference === command.externalReference.trim(),
          )
        )
          fail('validation', 'That external post reference is already recorded for this account.');
        publication.status = 'published';
        publication.externalReference = command.externalReference.trim();
        publication.postedAt = new Date(postedTime).toISOString();
        findContent(publication.contentId).stage = 'published';
        return {
          message:
            'Manual post reference recorded locally. The prototype has not verified it with a platform.',
          entityId: publication.id,
        };
      }
      case 'planPack': {
        findPage(command.pageId);
        if (!command.name.trim())
          fail('validation', 'Give this pack a name.', { name: 'Name is required.' });
        if (!Number.isSafeInteger(command.count) || command.count < 1 || command.count > 30)
          fail('validation', 'Plan between 1 and 30 items.', {
            count: 'Use a whole number from 1 to 30.',
          });
        if (!isWhole(command.budgetMinor))
          fail('validation', 'Pack budget must be nonnegative whole pence.');
        let kinds: AssetKind[] =
          command.mix.toLowerCase().includes('footage') || command.pageId === 'page-table'
            ? ['footage', 'environment', 'music']
            : command.mix.toLowerCase().includes('graphic') || command.pageId === 'page-explained'
              ? ['graphic', 'environment', 'music']
              : ['product', 'environment', 'product', 'music'];
        if (/\d/.test(command.mix)) {
          const explicit: AssetKind[] = [];
          for (const part of command.mix
            .split(/[,;·\n]+/)
            .map((value) => value.trim())
            .filter(Boolean)) {
            const match =
              /^(\d+)\s+(product|environment|footage|music|voice|graphic|audio|detail)s?$/i.exec(
                part,
              );
            if (!match)
              fail(
                'validation',
                'Describe the mix as counts and asset kinds, for example: 2 product, 2 environment, 1 music.',
                { mix: 'Use product, environment, footage, music, voice or graphic.' },
              );
            const [, rawCount, rawKind] = requireValue(match, 'Invalid pack mix.');
            const quantity = Number(rawCount);
            if (quantity < 1 || quantity > 30)
              fail('validation', 'Each mix quantity must be between 1 and 30.');
            const kind =
              rawKind.toLowerCase() === 'audio'
                ? 'music'
                : rawKind.toLowerCase() === 'detail'
                  ? 'product'
                  : (rawKind.toLowerCase() as AssetKind);
            explicit.push(...Array.from({ length: quantity }, () => kind));
          }
          if (explicit.length !== command.count)
            fail(
              'validation',
              `The mix totals ${explicit.length} items, but the requested count is ${command.count}.`,
              { mix: 'Mix quantities must add up to the requested count.' },
            );
          kinds = explicit;
        }
        const assignedAssets = new Set<string>();
        const items: PackItem[] = Array.from({ length: command.count }, (_, index) => {
          const kind = kinds[index % kinds.length];
          const asset = state.assets.find(
            (a) =>
              a.kind === kind &&
              !assignedAssets.has(a.id) &&
              state.representations.some(
                (r) =>
                  r.assetVersionId === a.currentVersionId &&
                  r.rights === 'eligible' &&
                  r.readiness === 'ready',
              ),
          );
          if (asset) assignedAssets.add(asset.id);
          return {
            id: id('pack-item'),
            name:
              asset?.name ??
              `${kind.charAt(0).toUpperCase() + kind.slice(1)} variation ${index + 1}`,
            kind,
            reason: asset
              ? 'A ready registry ingredient can fulfil this role without new generation.'
              : 'A proposed missing ingredient; review the need and cost before authorising acquisition.',
            route: asset ? 'reuse' : 'generate',
            cost: money(asset ? 0 : kind === 'footage' ? 250 : 120),
            status: asset ? 'ready' : 'planned',
            assetId: asset?.id,
          };
        });
        const pack = {
          id: id('pack'),
          name: command.name.trim(),
          pageId: command.pageId,
          requestedCount: command.count,
          mix: command.mix,
          style: command.style,
          budget: money(command.budgetMinor),
          status: 'planned' as const,
          items,
        };
        state.packs.unshift(pack);
        return {
          message:
            'Pack planned. Ready ingredients and missing needs are counted separately; acquisition has not started.',
          entityId: pack.id,
        };
      }
      case 'authorizePack': {
        const pack = requireValue(
          state.packs.find((p) => p.id === command.packId),
          'This pack is unavailable.',
        );
        const cost = pack.items
          .filter((i) => i.status !== 'ready')
          .reduce((sum, i) => sum + i.cost.minor, 0);
        if (cost > pack.budget.minor)
          fail(
            'blocked',
            `The proposed acquisition costs £${(cost / 100).toFixed(2)}, above this pack's £${(pack.budget.minor / 100).toFixed(2)} limit. Replan a smaller scope or a higher limit.`,
          );
        if (pack.status === 'ready') fail('blocked', 'This pack is already ready.');
        pack.status = 'authorised';
        return {
          message:
            'Acquisition scope authorised in the simulation. Start fulfilment to run the mock acquisition.',
          entityId: pack.id,
        };
      }
      case 'fulfillPack':
      case 'retryPackItem': {
        const pack = requireValue(
          state.packs.find((p) => p.id === command.packId),
          'This pack is unavailable.',
        );
        if (command.type === 'fulfillPack' && pack.status !== 'authorised')
          fail('blocked', 'Authorise this pack acquisition scope before starting fulfilment.');
        const items =
          command.type === 'retryPackItem'
            ? [
                requireValue(
                  pack.items.find((i) => i.id === command.itemId),
                  'This pack item is unavailable.',
                ),
              ]
            : pack.items.filter((i) => i.status !== 'ready');
        if (command.type === 'retryPackItem' && !['failed', 'missing'].includes(items[0].status))
          fail('blocked', 'Only a failed or missing pack item can be retried.');
        const cost = items.reduce((sum, item) => sum + item.cost.minor, 0);
        if (cost > pack.budget.minor)
          fail(
            'blocked',
            'This acquisition exceeds the approved pack budget. Replan the pack before retrying.',
          );
        let started = 0;
        for (const item of items) {
          const rep = item.assetId
            ? state.representations.find(
                (r) =>
                  r.assetVersionId ===
                  state.assets.find((a) => a.id === item.assetId)?.currentVersionId,
              )
            : undefined;
          if (rep && (rep.rights !== 'eligible' || rep.readiness === 'withdrawn')) {
            item.status = 'missing';
            item.error =
              'Rights are not eligible. Review or replace this ingredient before fulfilment.';
            continue;
          }
          item.status = 'processing';
          delete item.error;
          started++;
        }
        if (started) {
          packDeadlines[pack.id] = now() + 2500;
          pack.status = 'authorised';
        } else {
          pack.status = pack.items.every((i) => i.status === 'ready') ? 'ready' : 'partial';
        }
        return {
          message: started
            ? 'Mock fulfilment started. Ready results reuse labelled demo assets; no new media is generated.'
            : 'No acquisition can start. Inspect the remaining rights or readiness gaps.',
          entityId: pack.id,
        };
      }
      case 'registerAsset': {
        if (!command.name.trim() || !command.rightsNote.trim())
          fail('validation', 'Add an asset name and a source/rights note.', {
            name: !command.name.trim() ? 'Name is required.' : '',
            rightsNote: !command.rightsNote.trim() ? 'Source and rights context are required.' : '',
          });
        const assetId = id('asset'),
          versionId = id('asset-version'),
          repId = id('representation');
        const sample =
          command.mediaType === 'video'
            ? '/demo/source.mp4'
            : command.mediaType === 'audio'
              ? '/demo/tone.wav'
              : command.kind === 'product'
                ? '/demo/mug.svg'
                : command.kind === 'environment'
                  ? '/demo/kitchen.svg'
                  : '/demo/graphic.svg';
        state.assets.unshift({
          id: assetId,
          name: command.name.trim(),
          kind: command.kind,
          tags: ['mock registration', 'review required'],
          currentVersionId: versionId,
          usageCount: 0,
          origin: 'demo',
        });
        state.assetVersions.push({
          id: versionId,
          assetId,
          number: 1,
          description:
            'Mock registration using an existing local sample. No file was uploaded or generated.',
        });
        state.representations.push({
          id: repId,
          assetVersionId: versionId,
          mediaType: command.mediaType,
          src: command.mediaType === 'text' ? '' : sample,
          width: command.mediaType === 'audio' ? 0 : 1080,
          height: command.mediaType === 'audio' ? 0 : 1920,
          ...(command.mediaType === 'video'
            ? { durationFrames: 360 }
            : command.mediaType === 'audio'
              ? { durationFrames: 720 }
              : {}),
          readiness: 'quarantined',
          rights: 'review_required',
          rightsNote: `${command.rightsNote.trim()} · Simulated registration; media preview is an existing local demo sample.`,
          capabilities: ['demo registration'],
        });
        return {
          message:
            'Demo registry record created and quarantined for rights review. No file upload occurred.',
          entityId: assetId,
        };
      }
      case 'reviewAsset': {
        const rep = requireValue(
          state.representations.find((r) => r.id === command.representationId),
          'This representation is unavailable.',
        );
        if (rep.readiness === 'withdrawn' && command.eligible)
          fail(
            'blocked',
            'A withdrawn representation cannot be silently restored. Register a new version with fresh evidence.',
          );
        if (command.eligible && !rep.src)
          fail(
            'blocked',
            'This representation has no media attached. Register a supported demo media type.',
          );
        rep.rights = command.eligible ? 'eligible' : 'restricted';
        rep.readiness = command.eligible ? 'ready' : 'quarantined';
        rep.rightsNote += ` · Simulated ${state.role} decision: ${command.eligible ? 'eligible for the prototype' : 'restricted'}.`;
        return {
          message:
            'Simulated representation eligibility updated. Existing versions and package bindings are preserved.',
          entityId: rep.id,
        };
      }
      case 'createExperiment': {
        if (!command.name.trim() || !command.metric.trim() || !command.stoppingRule.trim())
          fail('validation', 'Name the experiment, primary metric and stopping rule.');
        if (new Set(command.contentIds).size < 2)
          fail('validation', 'Choose at least two distinct content variants for a comparison.');
        command.contentIds.forEach(findContent);
        if (
          new Set(command.contentIds.map((contentId) => findContent(contentId).pageId)).size !== 1
        )
          fail(
            'validation',
            'Compare variants within one page so the audience context stays explicit.',
          );
        if (
          !Number.isSafeInteger(command.windowDays) ||
          command.windowDays < 1 ||
          command.windowDays > 90
        )
          fail('validation', 'Choose an observation window from 1 to 90 days.');
        const experiment = {
          id: id('experiment'),
          name: command.name.trim(),
          contentIds: [...new Set(command.contentIds)],
          metric: command.metric.trim(),
          windowDays: command.windowDays,
          stoppingRule: command.stoppingRule.trim(),
          status: 'planned' as const,
          conclusion:
            'No result yet. Assignment, exposure and outcomes are not connected to a platform.',
        };
        state.experiments.push(experiment);
        return {
          message: 'Experiment protocol saved. No winner or causal effect has been inferred.',
          entityId: experiment.id,
        };
      }
      case 'reviewSuggestion': {
        const suggestion = requireValue(
          state.suggestions.find((s) => s.id === command.suggestionId),
          'This suggestion is unavailable.',
        );
        if (suggestion.status !== 'proposed')
          fail('blocked', 'This suggestion has already been reviewed.');
        suggestion.status = command.decision;
        return {
          message:
            command.decision === 'accepted'
              ? 'Suggestion accepted into the planning backlog. No production policy or existing content was changed.'
              : 'Suggestion dismissed with existing policy unchanged.',
          entityId: suggestion.id,
        };
      }
      case 'recordMetrics': {
        const publication = requireValue(
          state.publications.find((p) => p.id === command.publicationId),
          'This publication is unavailable.',
        );
        if (publication.status !== 'published')
          fail('blocked', 'Record a confirmed manual post reference before adding observations.');
        if (!isWhole(command.views))
          fail('validation', 'Views must be a nonnegative whole number.', {
            views: 'Use a nonnegative whole number.',
          });
        if (
          command.retention !== null &&
          (!Number.isFinite(command.retention) || command.retention < 0 || command.retention > 100)
        )
          fail('validation', 'Retention must be unavailable or a percentage from 0 to 100.', {
            retention: 'Use a percentage from 0 to 100, or leave unavailable.',
          });
        const ageDays = Math.max(0, (now() - Date.parse(publication.postedAt!)) / 86400000);
        const metric = {
          id: id('metric'),
          publicationId: publication.id,
          views: command.views,
          retention: command.retention,
          maturity: ageDays >= 7 ? ('mature' as const) : ('maturing' as const),
          window: `${Math.floor(ageDays)} days since publication; recorded ${timestamp()}`,
          source:
            'Manually entered prototype observation; not independently verified platform data.',
        };
        state.metrics.push(metric);
        return {
          message:
            'Observation recorded with its age and missingness. No experiment winner was inferred.',
          entityId: metric.id,
        };
      }
    }
  };
  return {
    async load() {
      initialize();
      await delay(state.scenario === 'loading' ? Math.max(latency, 1500) : latency);
      if (disposed) throw new Error('This mock service has been disposed.');
      if (state.scenario === 'unavailable')
        throw new Error(
          'Simulated workspace outage. Reset to Portfolio to recover; no real API was contacted.',
        );
      settle();
      persist();
      schedule();
      return snapshot();
    },
    execute(command) {
      const execute = async (): Promise<CommandResult> => {
        initialize();
        await delay(latency);
        if (disposed)
          return { ok: false, kind: 'failed', message: 'This mock service has been disposed.' };
        settle();
        const before = clone(state),
          deadlinesBefore = { ...packDeadlines };
        try {
          assertPermission(command);
          const result = operation(command);
          persist();
          notify();
          schedule();
          return { ok: true, state: snapshot(), ...result };
        } catch (error) {
          state = before;
          packDeadlines = deadlinesBefore;
          if (error instanceof ServiceFailure)
            return {
              ok: false,
              kind: error.kind,
              message: error.message,
              ...(error.fields ? { fields: error.fields } : {}),
            };
          return {
            ok: false,
            kind: 'failed',
            message:
              'The local mock could not complete this action. Your previous state has been preserved.',
          };
        }
      };
      const pending = queue.then(execute, execute);
      queue = pending;
      return pending;
    },
    async reset(scenario: Scenario = 'portfolio') {
      await queue;
      if (!scenarios.includes(scenario)) throw new Error('Unsupported fixture scenario.');
      if (timer) clearTimeout(timer);
      initialized = true;
      state = createFixtureState(scenario, now());
      packDeadlines = {};
      persist();
      notify();
      schedule();
      return snapshot();
    },
    subscribe(listener) {
      listeners.add(listener);
      initialize();
      schedule();
      return () => {
        listeners.delete(listener);
        schedule();
      };
    },
    dispose() {
      disposed = true;
      listeners.clear();
      if (timer) clearTimeout(timer);
    },
  };
}
