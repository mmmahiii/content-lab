import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Command, CommandResult, OperatorService, WorkspaceState } from './domain';
import { createFixtureState } from './fixtures';
import { createMockOperatorService, PROTOTYPE_STORAGE_KEY } from './mock-service';
import { validateComposition } from './validation';

const NOW = Date.parse('2026-09-09T12:00:00Z');
const clone = <T>(value: T): T => JSON.parse(JSON.stringify(value)) as T;
const services: OperatorService[] = [];
function setup(seed?: WorkspaceState) {
  let clock = NOW;
  const data = new Map<string, string>();
  if (seed) data.set(PROTOTYPE_STORAGE_KEY, JSON.stringify({ state: seed, packDeadlines: {} }));
  const storage = {
    getItem: (key: string) => data.get(key) ?? null,
    setItem: (key: string, value: string) => {
      data.set(key, value);
    },
    removeItem: (key: string) => {
      data.delete(key);
    },
  };
  const service = createMockOperatorService({ storage, latencyMs: 0, now: () => clock });
  services.push(service);
  return {
    service,
    storage,
    data,
    advance: (ms: number) => {
      clock += ms;
    },
    now: () => clock,
  };
}
function success(result: CommandResult) {
  if (!result.ok) throw new Error(`${result.kind}: ${result.message}`);
  return result;
}
async function command(service: OperatorService, value: Command) {
  return success(await service.execute(value));
}
afterEach(() => {
  services.splice(0).forEach((service) => service.dispose());
  vi.useRealTimers();
});

describe('fixture integrity and structural validation', () => {
  it('covers three composition families, eight contents and distinct stable identity layers', () => {
    const state = createFixtureState('portfolio', NOW);
    expect(state.pages).toHaveLength(3);
    expect(state.contents).toHaveLength(8);
    expect(new Set(state.contents.map((content) => content.family)).size).toBe(3);
    for (const content of state.contents.filter((c) => c.id !== 'content-blocked'))
      expect(
        validateComposition(content.draft, state).filter((f) => f.severity === 'fail'),
      ).toEqual([]);
    expect(state.runs.some((run) => run.status === 'failed')).toBe(true);
    expect(state.runs.some((run) => run.status === 'outcome_unknown')).toBe(true);
    expect(state.metrics.some((metric) => metric.views === null && metric.retention === null)).toBe(
      true,
    );
    expect(state.representations.every((rep) => rep.src.startsWith('/demo/'))).toBe(true);
    expect(state.assetVersions.filter((v) => v.assetId === 'asset-mug')).toHaveLength(2);
    expect(
      state.contents[0].draft.scenes
        .flatMap((s) => s.instances)
        .filter((i) => i.assetId === 'asset-mug'),
    ).toHaveLength(3);
  });

  it('detects timing, source, mandatory-asset, rights, relation and version blockers locally', () => {
    const state = createFixtureState('portfolio', NOW);
    const comp = clone(state.contents.find((c) => c.id === 'content-recipe')!.draft);
    comp.scenes[1].startFrame += 1;
    const subject = comp.scenes[0].instances[0];
    subject.sourceInFrame = 350;
    subject.assetVersionId = 'version-mug-1';
    subject.relation = 'on_surface';
    subject.targetInstanceId = 'another-scene-instance';
    comp.selectedAssets.push({ assetId: 'asset-coral', mandatory: true });
    state.representations.find((r) => r.id === 'rep-footage')!.rights = 'restricted';
    const findings = validateComposition(comp, state);
    for (const title of [
      'There is a gap between scenes',
      'Source footage is too short',
      'Asset version binding is invalid',
      'Relationship target is missing',
      'A mandatory ingredient is missing',
      'Rights need review',
    ])
      expect(
        findings.some(
          (f) => f.title === title && f.severity === 'fail' && f.evidence === 'local_check',
        ),
      ).toBe(true);
    expect(
      findings
        .filter((f) => f.category === 'identity')
        .every((f) => f.evidence === 'simulated' && f.severity === 'not_evaluated'),
    ).toBe(true);
  });
});

describe('state, permissions and immutable revisions', () => {
  it('guards every mutation family and permits reviewers only for explicit review actions', async () => {
    const { service } = setup();
    const state = await service.load();
    await command(service, { type: 'setRole', role: 'viewer' });
    const mutations: Command[] = [
      { type: 'savePage', page: state.pages[0] },
      { type: 'setIdeaStatus', ideaId: 'idea-colour', status: 'held' },
      { type: 'createContent', pageId: 'page-objects' },
      { type: 'updateDraft', contentId: 'content-mug', draft: state.contents[0].draft },
      ...(
        ['saveRevision', 'createPreview', 'renderRevision', 'repairPlan', 'newCandidate'] as const
      ).map((type) => ({ type, contentId: 'content-mug' })),
      { type: 'retryRun', runId: 'run-content-failed' },
      { type: 'reconcileRun', runId: 'run-unknown' },
      { type: 'approvePackage', packageId: 'package-content-recipe' },
      { type: 'rejectPackage', packageId: 'package-content-recipe', reason: 'Needs attention' },
      {
        type: 'preparePublication',
        packageId: 'package-content-approved',
        account: '@demo',
        timezone: 'Europe/London',
      },
      {
        type: 'recordPost',
        publicationId: 'publication-morning',
        externalReference: 'demo',
        postedAt: new Date(NOW).toISOString(),
      },
      {
        type: 'planPack',
        name: 'Test',
        pageId: 'page-objects',
        count: 1,
        mix: '1 product',
        style: 'Warm',
        budgetMinor: 200,
      },
      { type: 'authorizePack', packId: 'pack-table' },
      { type: 'fulfillPack', packId: 'pack-table' },
      { type: 'retryPackItem', packId: 'pack-morning', itemId: 'pack-morning-detail' },
      {
        type: 'registerAsset',
        name: 'Asset',
        kind: 'product',
        mediaType: 'image',
        rightsNote: 'Review',
      },
      { type: 'reviewAsset', representationId: 'rep-kitchen', eligible: true },
      {
        type: 'createExperiment',
        name: 'Study',
        contentIds: ['content-mug', 'content-running'],
        metric: 'Hold',
        windowDays: 7,
        stoppingRule: 'Seven days',
      },
      { type: 'reviewSuggestion', suggestionId: 'suggestion-pace', decision: 'accepted' },
      { type: 'recordMetrics', publicationId: 'publication-morning', views: 10, retention: null },
    ];
    for (const mutation of mutations)
      expect(await service.execute(mutation)).toMatchObject({ ok: false, kind: 'permission' });
    await command(service, { type: 'setRole', role: 'reviewer' });
    expect(await service.execute({ type: 'createContent', pageId: 'page-objects' })).toMatchObject({
      ok: false,
      kind: 'permission',
    });
    expect(
      (
        await command(service, {
          type: 'reviewAsset',
          representationId: 'rep-kitchen',
          eligible: true,
        })
      ).state.representations.find((r) => r.id === 'rep-kitchen')?.rights,
    ).toBe('eligible');
    await command(service, { type: 'setRole', role: 'editor' });
    expect(
      await service.execute({ type: 'approvePackage', packageId: 'package-content-recipe' }),
    ).toMatchObject({ ok: false, kind: 'permission' });
  });

  it('keeps saved and render-pinned revisions immutable when a draft or caller snapshot changes', async () => {
    const { service, advance } = setup();
    let state = await service.load();
    const saved = await command(service, { type: 'saveRevision', contentId: 'content-mug' });
    const frozen = clone(saved.state.revisions.find((r) => r.id === saved.entityId)!);
    const preview = await command(service, { type: 'createPreview', contentId: 'content-mug' });
    expect(preview.state.revisions.find((r) => r.id === preview.entityId)?.previewCreated).toBe(
      true,
    );
    const render = await command(service, { type: 'renderRevision', contentId: 'content-mug' });
    const pinned = render.state.runs.find((r) => r.id === render.entityId)!.revisionId;
    state = render.state;
    const draft = clone(state.contents.find((c) => c.id === 'content-mug')!.draft);
    draft.caption = 'A changed caption that requires a new approval.';
    await command(service, { type: 'updateDraft', contentId: 'content-mug', draft });
    draft.caption = 'Caller mutation after the save';
    advance(5000);
    state = await service.load();
    expect(state.revisions.find((r) => r.id === frozen.id)).toEqual(frozen);
    expect(state.revisions.find((r) => r.id === pinned)?.composition.caption).not.toBe(
      'A changed caption that requires a new approval.',
    );
    expect(state.contents.find((c) => c.id === 'content-mug')?.draft.caption).toBe(
      'A changed caption that requires a new approval.',
    );
    expect(state.contents.find((c) => c.id === 'content-mug')?.stage).toBe('draft');
    state.contents[0].draft.title = 'Mutating a returned snapshot';
    expect((await service.load()).contents[0].draft.title).not.toBe('Mutating a returned snapshot');
    const pkg = state.packages.find((p) => p.runId === render.entityId)!;
    expect(await service.execute({ type: 'approvePackage', packageId: pkg.id })).toMatchObject({
      ok: false,
      kind: 'blocked',
    });
  });

  it('rolls back failed commands and preserves the prior draft when structural repair cannot act', async () => {
    const { service } = setup();
    const before = await service.load();
    expect(
      await service.execute({ type: 'renderRevision', contentId: 'content-blocked' }),
    ).toMatchObject({ ok: false, kind: 'blocked' });
    expect(await service.execute({ type: 'repairPlan', contentId: 'content-mug' })).toMatchObject({
      ok: false,
      kind: 'blocked',
    });
    const after = await service.load();
    expect(after.revisions).toEqual(before.revisions);
    expect(after.contents).toEqual(before.contents);
  });

  it('saves structural repairs as new revisions while keeping rights blockers explicit', async () => {
    const { service } = setup();
    const state = await service.load();
    const draft = clone(state.contents.find((c) => c.id === 'content-blocked')!.draft);
    draft.scenes[0].instances[1].x = 1.2;
    draft.scenes[1].startFrame = 260;
    await command(service, { type: 'updateDraft', contentId: 'content-blocked', draft });
    const repaired = await command(service, { type: 'repairPlan', contentId: 'content-blocked' });
    expect(
      repaired.state.revisions.find((r) => r.id === repaired.entityId)?.composition.scenes[1]
        .startFrame,
    ).toBe(240);
    expect(repaired.state.contents.find((c) => c.id === 'content-blocked')?.stage).toBe('blocked');
    expect(
      await service.execute({ type: 'createPreview', contentId: 'content-blocked' }),
    ).toMatchObject({ ok: false, kind: 'blocked' });
  });
});

describe('execution, budget and recovery', () => {
  it('reserves whole pence atomically, rejects duplicate starts, and settles once after a reload', async () => {
    const context = setup();
    const { service, storage, advance, now } = context;
    const started = await command(service, { type: 'renderRevision', contentId: 'content-mug' });
    const run = started.state.runs.find((r) => r.id === started.entityId)!;
    expect(Number.isSafeInteger(run.reserved.minor)).toBe(true);
    expect(run.spent.minor).toBe(0);
    expect(
      await service.execute({ type: 'renderRevision', contentId: 'content-mug' }),
    ).toMatchObject({ ok: false, kind: 'blocked' });
    service.dispose();
    advance(5000);
    const recovered = createMockOperatorService({ storage, now, latencyMs: 0 });
    services.push(recovered);
    const state = await recovered.load();
    const settled = state.runs.find((r) => r.id === run.id)!;
    expect(settled.status).toBe('succeeded');
    expect(settled.reserved.minor).toBe(0);
    expect(settled.spent.minor).toBeGreaterThan(0);
    expect(settled.spent.minor).toBeLessThanOrEqual(settled.estimate.minor);
    expect(state.packages.filter((p) => p.runId === run.id)).toHaveLength(1);
    expect((await recovered.load()).packages.filter((p) => p.runId === run.id)).toHaveLength(1);
  });

  it('accounts for uncertain charges and blocks over-budget starts without saving a revision', async () => {
    const { service } = setup();
    const state = await service.load();
    const page = clone(state.pages.find((p) => p.id === 'page-table')!);
    page.budgetMinor = 100;
    await command(service, { type: 'savePage', page });
    const created = await command(service, {
      type: 'createContent',
      pageId: page.id,
      family: 'video',
    });
    const before = await service.load();
    expect(
      await service.execute({ type: 'renderRevision', contentId: created.entityId! }),
    ).toMatchObject({ ok: false, kind: 'blocked' });
    expect((await service.load()).revisions).toEqual(before.revisions);
  });

  it('reconciles an unknown result without resubmitting, then retries a failure with the same input revision', async () => {
    const { service, advance } = setup();
    const before = await service.load();
    expect(await service.execute({ type: 'retryRun', runId: 'run-unknown' })).toMatchObject({
      ok: false,
      kind: 'blocked',
    });
    const reconciled = await command(service, { type: 'reconcileRun', runId: 'run-unknown' });
    expect(reconciled.state.runs).toHaveLength(before.runs.length);
    expect(reconciled.state.runs.find((r) => r.id === 'run-unknown')).toMatchObject({
      status: 'succeeded',
      uncertain: { minor: 0 },
      reserved: { minor: 0 },
    });
    const retry = await command(service, { type: 'retryRun', runId: 'run-content-failed' });
    const run = retry.state.runs.find((r) => r.id === retry.entityId)!;
    expect(run.revisionId).toBe('revision-content-failed-1');
    expect(run.attempt).toBe(2);
    advance(5000);
    expect((await service.load()).runs.find((r) => r.id === run.id)?.status).toBe('succeeded');
  });

  it('publishes deadline progress to subscribers, stops timers on dispose, and never uses a network', async () => {
    vi.useFakeTimers();
    const { service, advance } = setup();
    const listener = vi.fn();
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    const unsubscribe = service.subscribe(listener);
    await command(service, { type: 'newCandidate', contentId: 'content-chart' });
    advance(4500);
    await vi.advanceTimersByTimeAsync(300);
    expect(
      listener.mock.calls
        .at(-1)?.[0]
        .runs.some(
          (run: RunLike) => run.contentId === 'content-chart' && run.status === 'succeeded',
        ),
    ).toBe(true);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
    unsubscribe();
    service.dispose();
    expect(vi.getTimerCount()).toBe(0);
  });
});
type RunLike = { contentId: string; status: string };

describe('review and publication', () => {
  it('requires exact package approval, validates handoff fields, and records a real reference only when explicitly supplied', async () => {
    const { service } = setup();
    expect(
      await service.execute({
        type: 'preparePublication',
        packageId: 'package-content-recipe',
        account: '@table',
        timezone: 'Europe/London',
      }),
    ).toMatchObject({ ok: false, kind: 'blocked' });
    await command(service, { type: 'approvePackage', packageId: 'package-content-recipe' });
    expect(
      await service.execute({
        type: 'preparePublication',
        packageId: 'package-content-recipe',
        account: '',
        timezone: 'invalid',
      }),
    ).toMatchObject({ ok: false, kind: 'validation' });
    const handoff = await command(service, {
      type: 'preparePublication',
      packageId: 'package-content-recipe',
      account: '@weeknighttable',
      timezone: 'Europe/London',
      scheduledAt: new Date(NOW + 3600000).toISOString(),
    });
    expect(handoff.state.publications.find((p) => p.id === handoff.entityId)).toMatchObject({
      status: 'scheduled',
      simulated: true,
    });
    expect(
      await service.execute({
        type: 'recordPost',
        publicationId: handoff.entityId!,
        externalReference: '',
        postedAt: new Date(NOW).toISOString(),
      }),
    ).toMatchObject({ ok: false, kind: 'validation' });
    expect(
      await service.execute({
        type: 'recordPost',
        publicationId: handoff.entityId!,
        externalReference: 'post-42',
        postedAt: new Date(NOW + 1000).toISOString(),
      }),
    ).toMatchObject({ ok: false, kind: 'validation' });
    const posted = await command(service, {
      type: 'recordPost',
      publicationId: handoff.entityId!,
      externalReference: 'post-42',
      postedAt: new Date(NOW).toISOString(),
    });
    expect(posted.state.publications.find((p) => p.id === handoff.entityId)).toMatchObject({
      status: 'published',
      externalReference: 'post-42',
    });
    expect(
      await service.execute({
        type: 'recordPost',
        publicationId: handoff.entityId!,
        externalReference: 'post-43',
        postedAt: new Date(NOW).toISOString(),
      }),
    ).toMatchObject({ ok: false, kind: 'blocked' });
  });

  it('blocks tampered copy bindings and rights withdrawn after approval', async () => {
    const seed = createFixtureState('portfolio', NOW);
    seed.packages.find((p) => p.id === 'package-content-approved')!.copy = 'Unapproved copy';
    const first = setup(seed).service;
    expect(
      await first.execute({
        type: 'preparePublication',
        packageId: 'package-content-approved',
        account: '@explain',
        timezone: 'Europe/London',
      }),
    ).toMatchObject({ ok: false, kind: 'blocked' });
    const second = setup().service;
    await command(second, {
      type: 'reviewAsset',
      representationId: 'rep-graphic',
      eligible: false,
    });
    expect(
      await second.execute({
        type: 'preparePublication',
        packageId: 'package-content-approved',
        account: '@explain',
        timezone: 'Europe/London',
      }),
    ).toMatchObject({ ok: false, kind: 'blocked' });
  });

  it('records rejection notes without modifying a frozen creative revision', async () => {
    const { service } = setup();
    const before = await service.load();
    expect(
      await service.execute({
        type: 'rejectPackage',
        packageId: 'package-content-recipe',
        reason: '',
      }),
    ).toMatchObject({ ok: false, kind: 'validation' });
    const result = await command(service, {
      type: 'rejectPackage',
      packageId: 'package-content-recipe',
      reason: 'The opening needs a clearer payoff.',
    });
    expect(result.state.packages.find((p) => p.id === 'package-content-recipe')).toMatchObject({
      status: 'rejected',
      rejectionReason: 'The opening needs a clearer payoff.',
    });
    expect(result.state.revisions).toEqual(before.revisions);
  });
});

describe('pages, assets, packs and learning', () => {
  it('supports new page setup, idea decisions and creation from an idea or ready partial pack', async () => {
    const { service } = setup();
    const state = await service.load();
    const newPage = clone(state.pages[0]);
    newPage.id = '';
    newPage.name = 'A new property';
    const saved = await command(service, { type: 'savePage', page: newPage });
    expect(saved.state.pages.some((p) => p.id === saved.entityId)).toBe(true);
    expect(
      await service.execute({ type: 'savePage', page: { ...newPage, budgetMinor: 1.5 } }),
    ).toMatchObject({ ok: false, kind: 'validation' });
    await command(service, { type: 'setIdeaStatus', ideaId: 'idea-colour', status: 'held' });
    await command(service, { type: 'setIdeaStatus', ideaId: 'idea-colour', status: 'suggested' });
    const fromIdea = await command(service, {
      type: 'createContent',
      pageId: 'page-objects',
      ideaId: 'idea-colour',
    });
    expect(fromIdea.state.contents.find((c) => c.id === fromIdea.entityId)?.draft.title).toBe(
      'Same ritual, a different colour',
    );
    expect(
      await service.execute({ type: 'createContent', pageId: 'page-table', ideaId: 'idea-season' }),
    ).toMatchObject({ ok: false, kind: 'blocked' });
    const fromPack = await command(service, {
      type: 'createContent',
      pageId: 'page-objects',
      packId: 'pack-morning',
    });
    expect(
      fromPack.state.contents.find((c) => c.id === fromPack.entityId)?.draft.selectedAssets,
    ).toHaveLength(4);
  });

  it('honours explicit pack mix, gates acquisition by budget, and preserves partial failure instead of inventing media', async () => {
    const { service, advance } = setup();
    expect(
      await service.execute({
        type: 'planPack',
        pageId: 'page-objects',
        name: 'Wrong mix',
        count: 4,
        mix: '2 product, 1 music',
        style: 'Warm',
        budgetMinor: 600,
      }),
    ).toMatchObject({ ok: false, kind: 'validation' });
    const planned = await command(service, {
      type: 'planPack',
      pageId: 'page-objects',
      name: 'A five-piece pack',
      count: 5,
      mix: '2 product, 2 environment, 1 voice',
      style: 'Warm',
      budgetMinor: 100,
    });
    const pack = planned.state.packs.find((p) => p.id === planned.entityId)!;
    expect(pack.items.filter((i) => i.kind === 'product')).toHaveLength(2);
    expect(pack.items.filter((i) => i.kind === 'environment')).toHaveLength(2);
    expect(await service.execute({ type: 'fulfillPack', packId: pack.id })).toMatchObject({
      ok: false,
      kind: 'blocked',
    });
    expect(await service.execute({ type: 'authorizePack', packId: pack.id })).toMatchObject({
      ok: false,
      kind: 'blocked',
    });
    const enough = await command(service, {
      type: 'planPack',
      pageId: 'page-objects',
      name: 'An affordable scope',
      count: 5,
      mix: '2 product, 2 environment, 1 voice',
      style: 'Warm',
      budgetMinor: 600,
    });
    await command(service, { type: 'authorizePack', packId: enough.entityId! });
    await command(service, { type: 'fulfillPack', packId: enough.entityId! });
    advance(3000);
    const settled = (await service.load()).packs.find((p) => p.id === enough.entityId)!;
    expect(settled.status).toBe('partial');
    expect(settled.items.find((i) => i.kind === 'voice')?.status).toBe('failed');
    expect(settled.items.find((i) => i.kind === 'voice')?.assetId).toBeUndefined();
    expect(settled.items.filter((i) => i.status === 'ready')).toHaveLength(4);
    await command(service, {
      type: 'retryPackItem',
      packId: 'pack-morning',
      itemId: 'pack-morning-detail',
    });
    advance(3000);
    expect((await service.load()).packs.find((p) => p.id === 'pack-morning')?.status).toBe('ready');
  });

  it('quarantines a mock asset until rights review and records independent immutable version identity', async () => {
    const { service } = setup();
    const before = await service.load();
    const registered = await command(service, {
      type: 'registerAsset',
      name: 'New product reference',
      kind: 'product',
      mediaType: 'image',
      rightsNote: 'Review permitted channels and derivative use.',
    });
    const asset = registered.state.assets.find((a) => a.id === registered.entityId)!;
    const representation = registered.state.representations.find(
      (r) => r.assetVersionId === asset.currentVersionId,
    )!;
    expect(representation).toMatchObject({
      readiness: 'quarantined',
      rights: 'review_required',
      src: '/demo/mug.svg',
    });
    expect(representation.rightsNote).toContain('existing local demo sample');
    const reviewed = await command(service, {
      type: 'reviewAsset',
      representationId: representation.id,
      eligible: true,
    });
    expect(reviewed.state.representations.find((r) => r.id === representation.id)?.readiness).toBe(
      'ready',
    );
    expect(reviewed.state.assetVersions.filter((v) => v.assetId === 'asset-mug')).toEqual(
      before.assetVersions.filter((v) => v.assetId === 'asset-mug'),
    );
    expect(
      await service.execute({
        type: 'reviewAsset',
        representationId: 'rep-old-mug',
        eligible: true,
      }),
    ).toMatchObject({ ok: false, kind: 'blocked' });
  });

  it('keeps observations, experiment protocol and accepted suggestions separate from performance claims or policy changes', async () => {
    const { service } = setup();
    const before = await service.load();
    const observed = await command(service, {
      type: 'recordMetrics',
      publicationId: 'publication-morning',
      views: 0,
      retention: null,
    });
    expect(observed.state.metrics.find((m) => m.id === observed.entityId)).toMatchObject({
      views: 0,
      retention: null,
      maturity: 'mature',
    });
    expect(
      await service.execute({
        type: 'recordMetrics',
        publicationId: 'publication-morning',
        views: 20,
        retention: 101,
      }),
    ).toMatchObject({ ok: false, kind: 'validation' });
    expect(
      await service.execute({
        type: 'createExperiment',
        name: 'Cross-page',
        contentIds: ['content-mug', 'content-chart'],
        metric: 'Hold',
        windowDays: 7,
        stoppingRule: 'Seven days',
      }),
    ).toMatchObject({ ok: false, kind: 'validation' });
    const experiment = await command(service, {
      type: 'createExperiment',
      name: 'Opening comparison',
      contentIds: ['content-mug', 'content-running'],
      metric: '3-second hold rate',
      windowDays: 7,
      stoppingRule: 'Both arms complete a seven-day observation window.',
    });
    expect(experiment.state.experiments.find((e) => e.id === experiment.entityId)?.status).toBe(
      'planned',
    );
    const accepted = await command(service, {
      type: 'reviewSuggestion',
      suggestionId: 'suggestion-pace',
      decision: 'accepted',
    });
    expect(accepted.state.pages).toEqual(before.pages);
    expect(accepted.state.contents).toEqual(before.contents);
    await command(service, {
      type: 'reviewSuggestion',
      suggestionId: 'suggestion-fatigue',
      decision: 'dismissed',
    });
  });
});

describe('scenario and persistence failures', () => {
  it('supports empty setup and outage recovery without fabricating a successful load', async () => {
    const { service } = setup();
    expect((await service.reset('empty')).pages).toEqual([]);
    expect((await service.load()).metrics).toEqual([]);
    await service.reset('unavailable');
    await expect(service.load()).rejects.toThrow('Simulated workspace outage');
    expect(await service.execute({ type: 'createContent', pageId: 'page-objects' })).toMatchObject({
      ok: false,
      kind: 'failed',
    });
    expect((await service.reset('portfolio')).contents).toHaveLength(8);
    expect((await service.load()).pages).toHaveLength(3);
  });

  it('makes the loading scenario observable and restores malformed stored state with a notice', async () => {
    vi.useFakeTimers();
    const { service, data } = setup();
    await service.reset('loading');
    let resolved = false;
    const loading = service.load().then(() => {
      resolved = true;
    });
    await vi.advanceTimersByTimeAsync(1000);
    expect(resolved).toBe(false);
    await vi.advanceTimersByTimeAsync(500);
    await loading;
    expect(resolved).toBe(true);
    service.dispose();
    data.set(PROTOTYPE_STORAGE_KEY, '{not-json');
    const recovery = createMockOperatorService({
      storage: {
        getItem: (key) => data.get(key) ?? null,
        setItem: (key, value) => {
          data.set(key, value);
        },
        removeItem: (key) => {
          data.delete(key);
        },
      },
      latencyMs: 0,
      now: () => NOW,
    });
    services.push(recovery);
    expect((await recovery.load()).recoveryNotice).toContain('could not be read');
  });

  it('continues in memory when browser persistence is unavailable', async () => {
    const service = createMockOperatorService({
      storage: {
        getItem: () => null,
        setItem: () => {
          throw new Error('Quota exceeded');
        },
        removeItem: () => undefined,
      },
      latencyMs: 0,
      now: () => NOW,
    });
    services.push(service);
    const result = await command(service, {
      type: 'setIdeaStatus',
      ideaId: 'idea-colour',
      status: 'held',
    });
    expect(result.state.recoveryNotice).toContain('will not survive a reload');
    expect((await service.load()).ideas.find((i) => i.id === 'idea-colour')?.status).toBe('held');
  });
});
