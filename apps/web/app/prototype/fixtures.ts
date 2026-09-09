import type {
  Composition,
  ContentItem,
  Family,
  Money,
  Revision,
  Run,
  Scenario,
  Scene,
  SceneInstance,
  WorkspaceState,
} from './domain';
import { validateComposition } from './validation';

const gbp = (minor: number): Money => ({ minor, currency: 'GBP' });
const copy = <T>(value: T): T => JSON.parse(JSON.stringify(value)) as T;

export function createFixtureComposition(family: Family = 'product', title?: string): Composition {
  const isVideo = family === 'video';
  const totalFrames = isVideo ? 360 : 720;
  const span = totalFrames / 3;
  const headings =
    family === 'product'
      ? [
          'Small rituals.\nBetter mornings.',
          'A little space\nfor yourself.',
          'Make room for\nthe everyday.',
        ]
      : family === 'graphic'
        ? [
            'One small change.\nA clearer picture.',
            'Show the difference.\nExplain the why.',
            'Take one idea\nwith you.',
          ]
        : [
            'A pause before\nthe evening rush.',
            'The small moments\nmake the story.',
            'A table worth\ncoming back to.',
          ];
  const scenes: Scene[] = headings.map((text, index) => {
    const startFrame = index * span;
    const endFrame = startFrame + span;
    const id = `${family}-scene-${index + 1}`;
    const base = {
      rotation: 0,
      opacity: 1,
      startFrame,
      endFrame,
      sourceInFrame: 0,
      relation: 'independent' as const,
      protectedProperties: [],
    };
    const subject: SceneInstance = {
      ...base,
      id: `${id}-subject`,
      name:
        family === 'product'
          ? 'Ceramic mug'
          : family === 'graphic'
            ? 'Illustrative diagram'
            : 'Source footage',
      assetId:
        family === 'product'
          ? 'asset-mug'
          : family === 'graphic'
            ? 'asset-graphic'
            : 'asset-footage',
      assetVersionId:
        family === 'product'
          ? 'version-mug-1'
          : family === 'graphic'
            ? 'version-graphic-1'
            : 'version-footage-1',
      representationId:
        family === 'product' ? 'rep-mug' : family === 'graphic' ? 'rep-graphic' : 'rep-footage',
      kind: isVideo ? 'video' : 'image',
      color: '#d99e73',
      x: isVideo ? 0 : 0.14,
      y: isVideo ? 0 : 0.33,
      width: isVideo ? 1 : 0.72,
      height: isVideo ? 1 : 0.49,
      layer: 2,
      sourceInFrame: isVideo ? index * span : 0,
      protectedProperties: ['identity', 'color'],
    };
    const instances: SceneInstance[] = [];
    if (family === 'product')
      instances.push({
        ...base,
        id: `${id}-desk`,
        name: 'Studio surface',
        kind: 'image',
        assetId: 'asset-desk',
        assetVersionId: 'version-desk-1',
        representationId: 'rep-desk',
        color: '#402a39',
        x: 0,
        y: 0.55,
        width: 1,
        height: 0.45,
        layer: 1,
      });
    instances.push(subject, {
      ...base,
      id: `${id}-title`,
      name: 'Headline',
      kind: 'text',
      text,
      color: '#fff4df',
      x: 0.09,
      y: 0.11,
      width: 0.82,
      height: 0.21,
      layer: 5,
      protectedProperties: ['text', 'position'],
    });
    return {
      id,
      name: ['Opening', 'Development', 'Payoff'][index],
      purpose: [
        'Introduce the audience promise',
        'Develop a clear visual idea',
        'Deliver the payoff',
      ][index],
      startFrame,
      endFrame,
      background:
        family === 'product'
          ? ['#2c1d2c', '#342333', '#382636'][index]
          : family === 'graphic'
            ? '#153c38'
            : '#282e28',
      instances,
      audio:
        family === 'product'
          ? [
              {
                id: `${id}-audio`,
                representationId: 'rep-tone',
                role: 'music',
                startFrame,
                endFrame,
                gain: 0.15,
              },
            ]
          : [],
    };
  });
  return {
    title:
      title ??
      (family === 'product'
        ? 'Small rituals. Better mornings.'
        : family === 'graphic'
          ? 'One small change, clearly explained'
          : 'A moment at the weeknight table'),
    brief: {
      objective:
        family === 'product'
          ? 'Introduce a tactile everyday object through a quiet morning ritual.'
          : family === 'graphic'
            ? 'Explain one useful concept with a simple visual sequence.'
            : 'Tell a short visual story about making time to gather.',
      audienceValue: 'A clear, original idea that feels useful and worth saving.',
      tone: 'Warm, deliberate and clear',
      claims: '',
      evidence:
        'Illustrative studio assets created for this prototype; no product performance or audience claims.',
      payoff: 'The opening promise resolves into one memorable final frame.',
    },
    hookId:
      family === 'graphic' ? 'hook-contrast' : family === 'video' ? 'hook-demo' : 'hook-question',
    blueprintId:
      family === 'graphic'
        ? 'blueprint-explainer'
        : family === 'video'
          ? 'blueprint-recipe'
          : 'blueprint-demonstration',
    mode: 'existing_assets',
    fps: { numerator: 30, denominator: 1 },
    canvas: { width: 1080, height: 1920 },
    totalFrames,
    scenes,
    selectedAssets: [
      {
        assetId:
          family === 'product'
            ? 'asset-mug'
            : family === 'graphic'
              ? 'asset-graphic'
              : 'asset-footage',
        mandatory: true,
      },
    ],
    caption:
      family === 'product'
        ? 'Small rituals. Better mornings. A quiet moment, made your own. Which everyday object makes your morning feel different?'
        : family === 'graphic'
          ? 'One idea, made a little clearer. Save this visual explanation for later.'
          : 'The story is in the small moments. A little space to pause, gather and begin again.',
    disclosures: 'Illustrative prototype content. No live campaign.',
    coverFrame: 30,
  };
}

/** All numbers, outcomes, rights decisions and brands in this dataset are illustrative. */
export function createFixtureState(
  scenario: Scenario = 'portfolio',
  now: number = Date.now(),
): WorkspaceState {
  const iso = (offset = 0) => new Date(now + offset).toISOString();
  const state: WorkspaceState = {
    schemaVersion: 1,
    scenario,
    role: 'owner',
    pages: [
      {
        id: 'page-objects',
        name: 'Object Stories',
        handle: '@objectstories',
        purpose: 'Thoughtful stories about the objects we live with.',
        audience: 'Design-conscious people who value everyday rituals.',
        voice: 'Warm, tactile and quietly confident',
        topics: ['Everyday rituals', 'Material stories', 'Thoughtful design'],
        color: '#c6775c',
        locale: 'en-GB',
        format: 'Vertical · 1080 × 1920',
        disclosures: 'Illustrative prototype content. No live campaign.',
        budgetMinor: 2500,
        policyOverride: false,
      },
      {
        id: 'page-explained',
        name: 'Everyday Explained',
        handle: '@everydayexplained',
        purpose: 'Make one useful idea easier to understand.',
        audience: 'Curious adults who enjoy concise visual explanations.',
        voice: 'Precise, friendly and evidence-aware',
        topics: ['Visual explainers', 'Small systems', 'Useful questions'],
        color: '#4f9785',
        locale: 'en-GB',
        format: 'Vertical · 1080 × 1920',
        disclosures: 'Illustrative prototype content. No live campaign.',
        budgetMinor: 3500,
        policyOverride: true,
      },
      {
        id: 'page-table',
        name: 'Weeknight Table',
        handle: '@weeknighttable',
        purpose: 'Visual stories about gathering around an everyday table.',
        audience: 'People looking for a calmer end to the working day.',
        voice: 'Welcoming, unhurried and practical',
        topics: ['Evening rituals', 'Shared tables', 'Kitchen stories'],
        color: '#c4a266',
        locale: 'en-GB',
        format: 'Vertical · 1080 × 1920',
        disclosures: 'Illustrative prototype content. No live campaign.',
        budgetMinor: 2500,
        policyOverride: false,
      },
    ],
    ideas: [
      {
        id: 'idea-ritual',
        pageId: 'page-objects',
        title: 'The object that starts your morning',
        summary: 'A close, tactile look at a familiar ceramic mug.',
        evidence:
          'Editorial hypothesis from the selected studio pack; no measured audience result.',
        freshness: 'fresh',
        fit: 'Strong material and ritual fit',
        status: 'drafted',
        family: 'product',
      },
      {
        id: 'idea-colour',
        pageId: 'page-objects',
        title: 'Same ritual, a different colour',
        summary:
          'Compare a warm white mug with a coral alternative while holding the composition steady.',
        evidence: 'Approved alternate asset is available. A controlled visual test is feasible.',
        freshness: 'fresh',
        fit: 'Reuses the morning pack',
        status: 'suggested',
        family: 'product',
      },
      {
        id: 'idea-system',
        pageId: 'page-explained',
        title: 'A small system, simply explained',
        summary: 'Turn one everyday process into three clear graphic beats.',
        evidence:
          'Illustrative planning note. Topic-specific claims require a source before production.',
        freshness: 'fresh',
        fit: 'Matches the graphic format',
        status: 'suggested',
        family: 'graphic',
      },
      {
        id: 'idea-evening',
        pageId: 'page-table',
        title: 'Before the evening rush',
        summary: 'A visual story about the transition from work to gathering.',
        evidence: 'Licensed-source eligibility is simulated; footage is an original demo clip.',
        freshness: 'expiring',
        fit: 'Available footage and a short story arc',
        status: 'held',
        family: 'video',
      },
      {
        id: 'idea-season',
        pageId: 'page-table',
        title: 'A late-summer table',
        summary: 'A seasonal visual treatment that now needs a freshness review.',
        evidence: 'Illustrative time-sensitive opportunity; no live trend source.',
        freshness: 'expired',
        fit: 'Seasonal relevance uncertain',
        status: 'suggested',
        family: 'video',
      },
    ],
    assets: [
      {
        id: 'asset-mug',
        name: 'Warm white ceramic mug',
        kind: 'product',
        tags: ['ceramic', 'hero', 'morning'],
        currentVersionId: 'version-mug-1',
        usageCount: 4,
        origin: 'demo',
      },
      {
        id: 'asset-coral',
        name: 'Coral ceramic mug',
        kind: 'product',
        tags: ['ceramic', 'alternate', 'coral'],
        currentVersionId: 'version-coral-1',
        usageCount: 1,
        origin: 'derived',
      },
      {
        id: 'asset-desk',
        name: 'Warm studio surface',
        kind: 'environment',
        tags: ['studio', 'warm', 'surface'],
        currentVersionId: 'version-desk-1',
        usageCount: 8,
        origin: 'demo',
      },
      {
        id: 'asset-graphic',
        name: 'Everyday graphic study',
        kind: 'graphic',
        tags: ['diagram', 'explainer'],
        currentVersionId: 'version-graphic-1',
        usageCount: 3,
        origin: 'demo',
      },
      {
        id: 'asset-footage',
        name: 'Weeknight source clip',
        kind: 'footage',
        tags: ['source clip', 'table', 'motion'],
        currentVersionId: 'version-footage-1',
        usageCount: 2,
        origin: 'demo',
      },
      {
        id: 'asset-tone',
        name: 'Quiet studio tone',
        kind: 'music',
        tags: ['ambient', 'demo audio'],
        currentVersionId: 'version-tone-1',
        usageCount: 5,
        origin: 'demo',
      },
      {
        id: 'asset-kitchen',
        name: 'Kitchen mood reference',
        kind: 'environment',
        tags: ['reference', 'rights review'],
        currentVersionId: 'version-kitchen-1',
        usageCount: 0,
        origin: 'uploaded',
      },
      {
        id: 'asset-old-mug',
        name: 'Archived mug treatment',
        kind: 'product',
        tags: ['withdrawn', 'archive'],
        currentVersionId: 'version-old-mug-1',
        usageCount: 2,
        origin: 'demo',
      },
    ],
    assetVersions: [
      {
        id: 'version-mug-1',
        assetId: 'asset-mug',
        number: 1,
        description: 'Original warm white studio illustration.',
      },
      {
        id: 'version-mug-2',
        assetId: 'asset-mug',
        number: 2,
        parentId: 'version-mug-1',
        description:
          'Alternate crop retained as a separate version; existing scenes stay pinned to v1.',
      },
      {
        id: 'version-coral-1',
        assetId: 'asset-coral',
        number: 1,
        description: 'Coral alternate for a controlled object comparison.',
      },
      {
        id: 'version-desk-1',
        assetId: 'asset-desk',
        number: 1,
        description: 'Studio support surface.',
      },
      {
        id: 'version-graphic-1',
        assetId: 'asset-graphic',
        number: 1,
        description: 'Original abstract explanatory diagram.',
      },
      {
        id: 'version-footage-1',
        assetId: 'asset-footage',
        number: 1,
        description: 'Original local demonstration video; not food preparation advice.',
      },
      {
        id: 'version-tone-1',
        assetId: 'asset-tone',
        number: 1,
        description: 'Original synthetic demonstration tone.',
      },
      {
        id: 'version-kitchen-1',
        assetId: 'asset-kitchen',
        number: 1,
        description: 'Illustrative upload awaiting a scoped rights review.',
      },
      {
        id: 'version-old-mug-1',
        assetId: 'asset-old-mug',
        number: 1,
        description: 'Withdrawn illustrative representation, retained for lineage.',
      },
    ],
    representations: [
      {
        id: 'rep-mug',
        assetVersionId: 'version-mug-1',
        mediaType: 'image',
        src: '/demo/mug.svg',
        width: 800,
        height: 900,
        readiness: 'ready',
        rights: 'eligible',
        rightsNote: 'Original demo illustration. Eligibility is a simulated operator decision.',
        capabilities: ['2D composition', 'object replacement', 'transparency'],
      },
      {
        id: 'rep-mug-v2',
        assetVersionId: 'version-mug-2',
        mediaType: 'image',
        src: '/demo/mug.svg',
        width: 800,
        height: 900,
        readiness: 'ready',
        rights: 'eligible',
        rightsNote: 'Original demo illustration; alternate version example.',
        capabilities: ['2D composition', 'transparency'],
        derivedFromId: 'rep-mug',
      },
      {
        id: 'rep-coral',
        assetVersionId: 'version-coral-1',
        mediaType: 'image',
        src: '/demo/mug-coral.svg',
        width: 800,
        height: 900,
        readiness: 'ready',
        rights: 'eligible',
        rightsNote: 'Original demo illustration. Colour variant for comparison.',
        capabilities: ['2D composition', 'object replacement', 'transparency'],
        derivedFromId: 'rep-mug',
      },
      {
        id: 'rep-desk',
        assetVersionId: 'version-desk-1',
        mediaType: 'image',
        src: '/demo/desk.svg',
        width: 1080,
        height: 864,
        readiness: 'ready',
        rights: 'eligible',
        rightsNote: 'Original demo artwork.',
        capabilities: ['2D composition', 'support surface'],
      },
      {
        id: 'rep-graphic',
        assetVersionId: 'version-graphic-1',
        mediaType: 'image',
        src: '/demo/graphic.svg',
        width: 900,
        height: 900,
        readiness: 'ready',
        rights: 'eligible',
        rightsNote: 'Original demo diagram; no measured data encoded in the artwork.',
        capabilities: ['2D composition', 'graphic explanation'],
      },
      {
        id: 'rep-footage',
        assetVersionId: 'version-footage-1',
        mediaType: 'video',
        src: '/demo/source.mp4',
        width: 540,
        height: 960,
        durationFrames: 360,
        readiness: 'ready',
        rights: 'eligible',
        rightsNote: 'Original local demo video. Not third-party source footage.',
        capabilities: ['trim', 'video playback'],
      },
      {
        id: 'rep-tone',
        assetVersionId: 'version-tone-1',
        mediaType: 'audio',
        src: '/demo/tone.wav',
        width: 0,
        height: 0,
        durationFrames: 720,
        readiness: 'ready',
        rights: 'eligible',
        rightsNote: 'Original synthetic demo tone; not a licensed commercial soundtrack.',
        capabilities: ['audio playback', 'gain'],
      },
      {
        id: 'rep-kitchen',
        assetVersionId: 'version-kitchen-1',
        mediaType: 'image',
        src: '/demo/kitchen.svg',
        width: 1080,
        height: 1920,
        readiness: 'quarantined',
        rights: 'review_required',
        rightsNote:
          'Simulated gap: distribution territory and permitted derivative use have not been recorded.',
        capabilities: ['reference only'],
      },
      {
        id: 'rep-old-mug',
        assetVersionId: 'version-old-mug-1',
        mediaType: 'image',
        src: '/demo/mug.svg',
        width: 800,
        height: 900,
        readiness: 'withdrawn',
        rights: 'restricted',
        rightsNote: 'Simulated withdrawal: retained for audit, unavailable for new production.',
        capabilities: [],
      },
    ],
    hooks: [
      {
        id: 'hook-question',
        name: 'The everyday ritual',
        text: 'Small rituals. Better mornings.',
        mechanism: 'Recognition and a specific audience promise',
        hypothesis: 'A familiar moment may earn attention. This is unvalidated.',
        color: '#c6775c',
      },
      {
        id: 'hook-contrast',
        name: 'See the difference',
        text: 'One small change. A clearer picture.',
        mechanism: 'A visible contrast before explanation',
        hypothesis: 'A clear comparison may improve comprehension; no uplift is claimed.',
        color: '#4f9785',
      },
      {
        id: 'hook-demo',
        name: 'Start with the moment',
        text: 'A pause before the evening rush.',
        mechanism: 'An action-led opening grounded in available footage',
        hypothesis: 'A recognisable transition may fit this audience; needs a controlled test.',
        color: '#c4a266',
      },
    ],
    blueprints: [
      {
        id: 'blueprint-demonstration',
        name: 'Object story',
        description: 'One hero object, a purposeful detail and a quiet payoff.',
        segments: ['Ritual', 'Detail', 'Payoff'],
        prerequisite: 'A ready hero object and a compatible environment.',
      },
      {
        id: 'blueprint-explainer',
        name: 'Visual explanation',
        description: 'Pose a question, make the mechanism visible, leave one useful idea.',
        segments: ['Question', 'Explanation', 'Takeaway'],
        prerequisite: 'A graphic representation and evidence for factual claims.',
      },
      {
        id: 'blueprint-recipe',
        name: 'Observed moment',
        description: 'Introduce a moment, develop the scene and resolve the visual story.',
        segments: ['Moment', 'Development', 'Resolution'],
        prerequisite: 'Ready footage long enough for every source range.',
      },
    ],
    contents: [],
    revisions: [],
    runs: [],
    packages: [],
    publications: [],
    packs: [
      {
        id: 'pack-morning',
        name: 'Morning objects',
        pageId: 'page-objects',
        requestedCount: 5,
        mix: '2 products · 1 environment · 1 music · 1 detail',
        style: 'Warm light, plum palette, tactile ceramic',
        budget: gbp(900),
        status: 'partial',
        items: [
          {
            id: 'pack-morning-mug',
            name: 'Warm white hero mug',
            kind: 'product',
            reason: 'The mandatory hero object anchors the story.',
            route: 'reuse',
            cost: gbp(0),
            status: 'ready',
            assetId: 'asset-mug',
          },
          {
            id: 'pack-morning-coral',
            name: 'Coral comparison mug',
            kind: 'product',
            reason: 'Changes one visible ingredient for a controlled comparison.',
            route: 'reuse',
            cost: gbp(0),
            status: 'ready',
            assetId: 'asset-coral',
          },
          {
            id: 'pack-morning-desk',
            name: 'Warm studio surface',
            kind: 'environment',
            reason: 'Provides a compatible support surface.',
            route: 'reuse',
            cost: gbp(0),
            status: 'ready',
            assetId: 'asset-desk',
          },
          {
            id: 'pack-morning-tone',
            name: 'Quiet ambient layer',
            kind: 'music',
            reason: 'Optional texture; content works without it.',
            route: 'reuse',
            cost: gbp(0),
            status: 'ready',
            assetId: 'asset-tone',
          },
          {
            id: 'pack-morning-detail',
            name: 'Handle detail alternate',
            kind: 'product',
            reason: 'Optional close detail is missing; use the hero crop for this first draft.',
            route: 'generate',
            cost: gbp(180),
            status: 'failed',
            error: 'Simulated provider timeout. No generated media was received.',
          },
        ],
      },
      {
        id: 'pack-table',
        name: 'An evening at the table',
        pageId: 'page-table',
        requestedCount: 3,
        mix: '1 footage · 1 environment · 1 music',
        style: 'Natural and unhurried',
        budget: gbp(600),
        status: 'planned',
        items: [
          {
            id: 'pack-table-footage',
            name: 'Opening table footage',
            kind: 'footage',
            reason: 'Existing original demo footage can establish the scene.',
            route: 'reuse',
            cost: gbp(0),
            status: 'ready',
            assetId: 'asset-footage',
          },
          {
            id: 'pack-table-room',
            name: 'Room reference',
            kind: 'environment',
            reason: 'Needs a rights decision before it can enter production.',
            route: 'upload',
            cost: gbp(0),
            status: 'missing',
            assetId: 'asset-kitchen',
            error: 'Rights review required.',
          },
          {
            id: 'pack-table-audio',
            name: 'Soft evening audio',
            kind: 'music',
            reason: 'Optional soundtrack; acquisition must stay inside the pack budget.',
            route: 'generate',
            cost: gbp(120),
            status: 'planned',
          },
        ],
      },
    ],
    metrics: [],
    experiments: [],
    suggestions: [],
  };
  const definitions: [string, string, Family, string, ContentItem['stage']][] = [
    ['content-mug', 'page-objects', 'product', 'Small rituals. Better mornings.', 'draft'],
    ['content-chart', 'page-explained', 'graphic', 'One small change, clearly explained', 'draft'],
    ['content-recipe', 'page-table', 'video', 'A moment at the weeknight table', 'review'],
    ['content-blocked', 'page-table', 'product', 'The room behind the ritual', 'blocked'],
    ['content-running', 'page-objects', 'product', 'A quieter start to the day', 'in_progress'],
    ['content-approved', 'page-explained', 'graphic', 'A useful idea in three frames', 'approved'],
    [
      'content-published',
      'page-objects',
      'product',
      'The shape of a familiar morning',
      'published',
    ],
    ['content-failed', 'page-table', 'video', 'A second look at the table', 'blocked'],
  ];
  state.contents = definitions.map(([id, pageId, family, title, stage]) => ({
    id,
    pageId,
    family,
    draft: createFixtureComposition(family, title),
    stage,
    updatedAt: iso(-3600000),
  }));
  const blocked = state.contents.find((c) => c.id === 'content-blocked')!;
  blocked.draft.selectedAssets.push({ assetId: 'asset-kitchen', mandatory: true });
  blocked.draft.scenes[0].instances[0] = {
    ...blocked.draft.scenes[0].instances[0],
    assetId: 'asset-kitchen',
    assetVersionId: 'version-kitchen-1',
    representationId: 'rep-kitchen',
  };
  for (const content of state.contents.filter(
    (c) => c.id !== 'content-mug' && c.id !== 'content-chart' && c.id !== 'content-blocked',
  )) {
    const revision: Revision = {
      id: `revision-${content.id}-1`,
      contentId: content.id,
      number: 1,
      createdAt: iso(-3600000),
      composition: copy(content.draft),
      previewCreated: true,
    };
    content.currentRevisionId = revision.id;
    state.revisions.push(revision);
    const status: Run['status'] =
      content.id === 'content-running'
        ? 'running'
        : content.id === 'content-failed'
          ? 'failed'
          : 'succeeded';
    const run: Run = {
      id: `run-${content.id}`,
      contentId: content.id,
      revisionId: revision.id,
      status,
      kind: 'render',
      attempt: 1,
      estimate: gbp(48),
      reserved: gbp(status === 'running' ? 48 : 0),
      spent: gbp(status === 'succeeded' ? 42 : status === 'failed' ? 12 : 0),
      uncertain: gbp(0),
      createdAt: iso(status === 'running' ? 0 : -3600000),
      ...(status === 'running' ? { completesAt: now + 12000 } : {}),
      ...(status === 'failed'
        ? { error: 'Simulated storage interruption. The pinned input is safe to retry.' }
        : {}),
      stages: ['Validate inputs', 'Compose preview', 'Check package'].map((name, index) => ({
        name,
        status:
          status === 'succeeded'
            ? 'succeeded'
            : status === 'failed' && index === 1
              ? 'failed'
              : status === 'running' && index === 0
                ? 'running'
                : index === 0
                  ? 'succeeded'
                  : 'pending',
        detail:
          status === 'succeeded' ? 'Simulated execution complete.' : 'Simulated execution stage.',
      })),
    };
    state.runs.push(run);
    if (status === 'succeeded')
      state.packages.push({
        id: `package-${content.id}`,
        contentId: content.id,
        revisionId: revision.id,
        runId: run.id,
        status:
          content.stage === 'approved' || content.stage === 'published' ? 'approved' : 'review',
        findings: validateComposition(revision.composition, state),
        copy: revision.composition.caption,
        disclosures: revision.composition.disclosures,
        coverFrame: revision.composition.coverFrame,
        ...(content.stage === 'approved' || content.stage === 'published'
          ? {
              approvalId: `approval-${content.id}`,
              approvedBy: 'owner' as const,
              approvedAt: iso(-1800000),
            }
          : {}),
      });
  }
  state.runs.push({
    id: 'run-unknown',
    contentId: 'content-failed',
    revisionId: 'revision-content-failed-1',
    status: 'outcome_unknown',
    kind: 'candidate',
    attempt: 1,
    estimate: gbp(65),
    reserved: gbp(0),
    spent: gbp(0),
    uncertain: gbp(65),
    createdAt: iso(-180000),
    error: 'Simulated submission timeout. A charge or result may exist; reconcile before retrying.',
    stages: [
      {
        name: 'Submit candidate',
        status: 'running',
        detail: 'Provider outcome unknown. Do not submit again.',
      },
      { name: 'Collect result', status: 'pending', detail: 'Awaiting reconciliation.' },
    ],
  });
  state.publications = [
    {
      id: 'publication-morning',
      packageId: 'package-content-published',
      contentId: 'content-published',
      approvalId: 'approval-content-published',
      account: '@objectstories',
      timezone: 'Europe/London',
      status: 'published',
      externalReference: 'demo-post-morning-001',
      postedAt: iso(-86400000 * 8),
      simulated: true,
    },
  ];
  state.metrics = [
    {
      id: 'metric-morning',
      publicationId: 'publication-morning',
      views: 18420,
      retention: 62.4,
      maturity: 'mature',
      window: '7 days after publication',
      source: 'Illustrative fixture values; not connected platform data.',
    },
    {
      id: 'metric-unavailable',
      publicationId: 'publication-morning',
      views: null,
      retention: null,
      maturity: 'unavailable',
      window: '30 days after publication',
      source: 'Observation window has not matured. Missing values are not zero.',
    },
  ];
  state.experiments = [
    {
      id: 'experiment-hook',
      name: 'Ritual opening vs detail opening',
      contentIds: ['content-mug', 'content-running'],
      metric: '3-second hold rate',
      windowDays: 7,
      stoppingRule: 'Review after both arms reach seven days; no early winner declaration.',
      status: 'planned',
      conclusion:
        'No evidence yet. The comparison changes the opening while holding the body constant.',
    },
  ];
  state.suggestions = [
    {
      id: 'suggestion-pace',
      title: 'Test a little more time on the object detail',
      pageId: 'page-objects',
      reason:
        'An illustrative review note suggests the detail could use more breathing room. This is not a measured performance finding.',
      status: 'proposed',
      change:
        'Propose a separate variant with a longer development beat; do not rewrite existing approvals.',
    },
    {
      id: 'suggestion-fatigue',
      title: 'Rotate the warm studio background',
      pageId: 'page-objects',
      reason:
        'The asset has eight illustrative uses. Reuse count alone does not prove audience fatigue.',
      status: 'proposed',
      change: 'Plan an environment alternative and compare it in a future controlled experiment.',
    },
  ];
  if (scenario === 'empty') {
    state.pages = [];
    state.ideas = [];
    state.assets = [];
    state.assetVersions = [];
    state.representations = [];
    state.contents = [];
    state.revisions = [];
    state.runs = [];
    state.packages = [];
    state.publications = [];
    state.packs = [];
    state.metrics = [];
    state.experiments = [];
    state.suggestions = [];
  }
  return state;
}
