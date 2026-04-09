import type {
  PackageDetailOut,
  PageOut,
  PolicyStateOut,
  ReelOut,
  RunDetailOut,
  SignedDownloadOut,
} from '../../../../packages/shared/ts/src/types';

export const demoIds = {
  orgId: '7d3d7599-820e-4c8d-9c74-3d3b6d6f2785',
  pageId: '495d0d7e-acde-4c1d-b7ef-e5bc0d8ba3f4',
  reelId: '0aa013bd-717d-43d0-9c88-d08b8f9ce3b3',
  runId: '52c8d1fa-1092-4d3e-8b7b-6b5bbf1cf4df',
} as const;

type PageDetailRecord = {
  page: PageOut;
  policy: PolicyStateOut | null;
  recentReels: ReelOut[];
};

type ReelDetailRecord = {
  page: PageOut;
  reel: ReelOut;
  relatedRun: RunDetailOut | null;
  packageDetail: PackageDetailOut | null;
};

type RunDetailRecord = {
  run: RunDetailOut;
  page: PageOut | null;
  reel: ReelOut | null;
  packageDetail: PackageDetailOut | null;
};

type PackageRecord = {
  packageDetail: PackageDetailOut;
  run: RunDetailOut;
  page: PageOut | null;
  reel: ReelOut | null;
};

type WorkspaceSummary = {
  orgId: string;
  pages: PageOut[];
  runs: RunDetailOut[];
  packages: PackageDetailOut[];
};

const page: PageOut = {
  id: demoIds.pageId,
  org_id: demoIds.orgId,
  platform: 'instagram',
  display_name: 'Northwind Ops',
  external_page_id: 'ig-northwind-ops',
  handle: '@northwind.ops',
  ownership: 'owned',
  metadata: {
    persona: {
      label: 'Calm educator',
      audience: 'Busy founders',
      brand_tone: ['clear', 'grounded'],
      content_pillars: ['operations', 'positioning', 'systems'],
      differentiators: ['operator-led advice', 'real delivery examples'],
      primary_call_to_action: 'Book a strategy call',
      extensions: {
        voice: 'plainspoken and specific',
        banned_motifs: ['stock trading charts'],
        cta_posture: 'soft_sell',
      },
    },
    constraints: {
      banned_topics: ['politics'],
      blocked_phrases: ['guaranteed results'],
      required_disclosures: ['Results vary'],
      prohibited_claims: ['instant growth'],
      preferred_languages: ['en'],
      allow_direct_cta: true,
      max_script_words: 180,
      max_hashtags: 6,
    },
    niche: 'b2b-services',
    market: 'uk',
  },
  created_at: '2026-04-08T08:15:00.000Z',
  updated_at: '2026-04-09T09:45:00.000Z',
};

const competitorPage: PageOut = {
  id: '782ce0da-4744-447f-a232-acde8ce3f00a',
  org_id: demoIds.orgId,
  platform: 'instagram',
  display_name: 'Rival Bench',
  external_page_id: 'ig-rival-bench',
  handle: '@rival.bench',
  ownership: 'competitor',
  metadata: {
    persona: null,
    constraints: {
      banned_topics: [],
      blocked_phrases: [],
      required_disclosures: [],
      prohibited_claims: [],
      preferred_languages: ['en'],
      allow_direct_cta: false,
      max_script_words: null,
      max_hashtags: null,
    },
    niche: 'competitor-tracking',
  },
  created_at: '2026-04-07T15:00:00.000Z',
  updated_at: '2026-04-09T07:10:00.000Z',
};

const pagePolicy: PolicyStateOut = {
  id: 'ed70ac85-b7d2-4c67-8f0d-c4ab9280eb54',
  org_id: demoIds.orgId,
  scope_type: 'page',
  scope_id: page.id,
  state: {
    mode_ratios: {
      exploit: 0.35,
      explore: 0.4,
      mutation: 0.15,
      chaos: 0.1,
    },
    budget: {
      per_run_usd_limit: 12,
      daily_usd_limit: 45,
      monthly_usd_limit: 900,
    },
    thresholds: {
      similarity: {
        warn_at: 0.72,
        block_at: 0.88,
      },
      min_quality_score: 0.62,
    },
  },
  updated_at: '2026-04-09T08:40:00.000Z',
};

const reels: ReelOut[] = [
  {
    id: demoIds.reelId,
    org_id: demoIds.orgId,
    page_id: page.id,
    reel_family_id: '0b8a36f8-6a89-4c2e-92ae-1dfc7d4e1894',
    origin: 'generated',
    status: 'posted',
    variant_label: 'Operator diary A',
    external_reel_id: null,
    metadata: {
      editor_template: 'hook-fast-cut',
      qa_score: 0.93,
      package_ready: true,
    },
    approved_at: '2026-04-09T11:25:00.000Z',
    approved_by: 'operator:reviewer',
    posted_at: '2026-04-09T12:10:00.000Z',
    posted_by: 'operator:publisher',
    created_at: '2026-04-09T09:00:00.000Z',
    updated_at: '2026-04-09T12:10:00.000Z',
  },
  {
    id: '7d7fe3c6-ceb0-4782-8fd6-acde3a1b94d1',
    org_id: demoIds.orgId,
    page_id: page.id,
    reel_family_id: '3f7f95bc-50f0-4059-9f6d-804fe1d7b8d8',
    origin: 'generated',
    status: 'qa_failed',
    variant_label: 'Compliance rewrite',
    external_reel_id: null,
    metadata: {
      editor_template: 'talking-head-cut',
      rejection_reason: 'missing disclosure',
    },
    approved_at: null,
    approved_by: null,
    posted_at: null,
    posted_by: null,
    created_at: '2026-04-09T10:30:00.000Z',
    updated_at: '2026-04-09T11:50:00.000Z',
  },
  {
    id: 'c6d2f721-70e0-4697-a9eb-11a63a7b6a3c',
    org_id: demoIds.orgId,
    page_id: page.id,
    reel_family_id: '8c33fa75-89db-4d15-ba17-f37f1f2246a0',
    origin: 'observed',
    status: 'active',
    variant_label: null,
    external_reel_id: 'obs-reel-001',
    metadata: {
      source: 'competitor_ingest',
      surfaced_reason: 'hook benchmark',
    },
    approved_at: null,
    approved_by: null,
    posted_at: null,
    posted_by: null,
    created_at: '2026-04-09T08:25:00.000Z',
    updated_at: '2026-04-09T08:25:00.000Z',
  },
];

function buildDownload(path: string): SignedDownloadOut {
  return {
    storage_uri: `s3://content-lab/${path}`,
    url: `https://downloads.content-lab.local/${path}?sig=demo`,
    expires_at: '2026-04-09T13:15:00.000Z',
  };
}

const packagedRun: RunDetailOut = {
  id: demoIds.runId,
  org_id: demoIds.orgId,
  workflow_key: 'process_reel',
  flow_trigger: 'reel_trigger',
  status: 'succeeded',
  idempotency_key: 'process-reel-0aa013bd',
  external_ref: 'prefect-flow-run-123',
  input_params: {
    org_id: demoIds.orgId,
    page_id: page.id,
    reel_id: demoIds.reelId,
    reel_family_id: reels[0].reel_family_id,
    priority: 'high',
  },
  output_payload: {
    package: {
      reel_id: demoIds.reelId,
      package_root_uri: `s3://content-lab/reels/packages/${demoIds.reelId}`,
      manifest_uri: `s3://content-lab/reels/packages/${demoIds.reelId}/package_manifest.json`,
      manifest: {
        version: 1,
        artifact_count: 6,
      },
      provenance_uri: `s3://content-lab/reels/packages/${demoIds.reelId}/provenance.json`,
      provenance: {
        source_run_id: demoIds.runId,
        asset_ids: ['asset-101', 'asset-102', 'asset-103'],
        provider_jobs: ['runway-job-22', 'ffmpeg-job-19'],
      },
      artifacts: [
        {
          name: 'final_video',
          storage_uri: `s3://content-lab/reels/packages/${demoIds.reelId}/final_video.mp4`,
          kind: 'video',
          content_type: 'video/mp4',
        },
        {
          name: 'cover',
          storage_uri: `s3://content-lab/reels/packages/${demoIds.reelId}/cover.png`,
          kind: 'image',
          content_type: 'image/png',
        },
        {
          name: 'caption_variants',
          storage_uri: `s3://content-lab/reels/packages/${demoIds.reelId}/caption_variants.txt`,
          kind: 'text',
          content_type: 'text/plain',
        },
        {
          name: 'posting_plan',
          storage_uri: `s3://content-lab/reels/packages/${demoIds.reelId}/posting_plan.json`,
          kind: 'json',
          content_type: 'application/json',
        },
        {
          name: 'package_manifest',
          storage_uri: `s3://content-lab/reels/packages/${demoIds.reelId}/package_manifest.json`,
          content_type: 'application/json',
        },
        {
          name: 'provenance',
          storage_uri: `s3://content-lab/reels/packages/${demoIds.reelId}/provenance.json`,
          content_type: 'application/json',
        },
      ],
    },
  },
  run_metadata: {
    submitted_via: 'api',
    flow_trigger: 'reel_trigger',
    actor: {
      id: 'operator:queue-manager',
      type: 'request_header',
    },
    request: {
      request_id: 'reel-trigger-001',
      method: 'POST',
      path: `/orgs/${demoIds.orgId}/pages/${page.id}/reels/${demoIds.reelId}/trigger`,
    },
    client: {
      source: 'operator-console',
    },
    target: {
      org_id: demoIds.orgId,
      page_id: page.id,
      reel_id: demoIds.reelId,
      reel_family_id: reels[0].reel_family_id,
    },
    orchestration: {
      backend: 'outbox',
      event_type: 'orchestration.flow.requested',
      outbox_event_id: '0f2cd117-ef4f-411f-9995-93f9a1456f1f',
    },
  },
  started_at: '2026-04-09T09:04:00.000Z',
  finished_at: '2026-04-09T09:18:00.000Z',
  created_at: '2026-04-09T09:03:30.000Z',
  updated_at: '2026-04-09T09:18:00.000Z',
  tasks: [
    {
      id: 'c38f1324-57c9-49ce-b561-7cb19c838e4c',
      task_type: 'plan_reels',
      status: 'succeeded',
      idempotency_key: 'task-plan-001',
      payload: {
        reel_id: demoIds.reelId,
        family_count: 1,
      },
      result: {
        planned: 1,
      },
      created_at: '2026-04-09T09:04:00.000Z',
      updated_at: '2026-04-09T09:05:00.000Z',
    },
    {
      id: '36f842d0-9e51-4d22-97a9-0ac8f20f960f',
      task_type: 'generate_assets',
      status: 'succeeded',
      idempotency_key: 'task-generate-001',
      payload: {
        prompt_count: 3,
      },
      result: {
        assets_created: 3,
      },
      created_at: '2026-04-09T09:05:00.000Z',
      updated_at: '2026-04-09T09:10:00.000Z',
    },
    {
      id: '5206b860-384f-44a5-aa5b-7620d6f5fe60',
      task_type: 'qa_review',
      status: 'succeeded',
      idempotency_key: 'task-qa-001',
      payload: {
        min_quality_score: 0.62,
      },
      result: {
        qa_score: 0.93,
      },
      created_at: '2026-04-09T09:10:00.000Z',
      updated_at: '2026-04-09T09:12:00.000Z',
    },
    {
      id: 'c8f01a90-9cb8-42e2-83dc-76b564e30cf7',
      task_type: 'package_outputs',
      status: 'succeeded',
      idempotency_key: 'task-package-001',
      payload: {
        include_manifest: true,
      },
      result: {
        artifact_count: 6,
      },
      created_at: '2026-04-09T09:12:00.000Z',
      updated_at: '2026-04-09T09:18:00.000Z',
    },
  ],
  task_status_counts: {
    succeeded: 4,
  },
};

const factoryRun: RunDetailOut = {
  id: '8cb7b6fe-1a89-412d-87cb-f7ce3bf59640',
  org_id: demoIds.orgId,
  workflow_key: 'daily_reel_factory',
  flow_trigger: 'manual',
  status: 'running',
  idempotency_key: 'factory-batch-2026-04-09-morning',
  external_ref: 'prefect-flow-run-451',
  input_params: {
    page_limit: 2,
  },
  output_payload: null,
  run_metadata: {
    submitted_via: 'api',
    flow_trigger: 'manual',
    actor: {
      id: 'operator:planner',
      type: 'request_header',
    },
    client: {
      operator_note: 'Morning batch',
    },
  },
  started_at: '2026-04-09T06:00:00.000Z',
  finished_at: null,
  created_at: '2026-04-09T05:59:20.000Z',
  updated_at: '2026-04-09T06:08:00.000Z',
  tasks: [
    {
      id: 'ea70d8b1-7ebe-4d80-9687-1305920abc8f',
      task_type: 'discover_pages',
      status: 'succeeded',
      idempotency_key: 'task-discover-001',
      payload: {
        page_limit: 2,
      },
      result: {
        pages: 2,
      },
      created_at: '2026-04-09T06:00:00.000Z',
      updated_at: '2026-04-09T06:03:00.000Z',
    },
    {
      id: '2e7df3ab-b92d-449d-b6a3-014e7ad1f2ec',
      task_type: 'plan_reels',
      status: 'running',
      idempotency_key: 'task-plan-batch-001',
      payload: {
        page_ids: [page.id, competitorPage.id],
      },
      result: null,
      created_at: '2026-04-09T06:03:00.000Z',
      updated_at: '2026-04-09T06:08:00.000Z',
    },
  ],
  task_status_counts: {
    running: 1,
    succeeded: 1,
  },
};

const packagedArtifactPath = `reels/packages/${demoIds.reelId}`;

const packageDetail: PackageDetailOut = {
  run_id: packagedRun.id,
  org_id: demoIds.orgId,
  status: packagedRun.status,
  workflow_key: packagedRun.workflow_key,
  reel_id: demoIds.reelId,
  package_root_uri: `s3://content-lab/${packagedArtifactPath}`,
  manifest_uri: `s3://content-lab/${packagedArtifactPath}/package_manifest.json`,
  manifest_metadata: {
    version: 1,
    artifact_count: 6,
  },
  manifest_download: buildDownload(`${packagedArtifactPath}/package_manifest.json`),
  provenance: {
    source_run_id: packagedRun.id,
    asset_ids: ['asset-101', 'asset-102', 'asset-103'],
    provider_jobs: ['runway-job-22', 'ffmpeg-job-19'],
  },
  provenance_uri: `s3://content-lab/${packagedArtifactPath}/provenance.json`,
  provenance_download: buildDownload(`${packagedArtifactPath}/provenance.json`),
  artifacts: [
    {
      name: 'final_video',
      storage_uri: `s3://content-lab/${packagedArtifactPath}/final_video.mp4`,
      kind: 'video',
      content_type: 'video/mp4',
      metadata: {
        slot: 'ready-to-post',
      },
      download: buildDownload(`${packagedArtifactPath}/final_video.mp4`),
    },
    {
      name: 'cover',
      storage_uri: `s3://content-lab/${packagedArtifactPath}/cover.png`,
      kind: 'image',
      content_type: 'image/png',
      metadata: {
        slot: 'thumbnail',
      },
      download: buildDownload(`${packagedArtifactPath}/cover.png`),
    },
    {
      name: 'caption_variants',
      storage_uri: `s3://content-lab/${packagedArtifactPath}/caption_variants.txt`,
      kind: 'text',
      content_type: 'text/plain',
      metadata: {
        variants: 3,
      },
      download: buildDownload(`${packagedArtifactPath}/caption_variants.txt`),
    },
    {
      name: 'posting_plan',
      storage_uri: `s3://content-lab/${packagedArtifactPath}/posting_plan.json`,
      kind: 'json',
      content_type: 'application/json',
      metadata: {
        timezone: 'Europe/London',
      },
      download: buildDownload(`${packagedArtifactPath}/posting_plan.json`),
    },
  ],
  created_at: packagedRun.created_at,
  updated_at: packagedRun.updated_at,
};

const pages = [page, competitorPage];
const runs = [packagedRun, factoryRun];
const packages = [packageDetail];

export function formatShortId(value: string): string {
  return value.slice(0, 8);
}

export function pagePath(orgId: string, pageId: string): string {
  return `/orgs/${orgId}/pages/${pageId}`;
}

export function reelPath(orgId: string, pageId: string, reelId: string): string {
  return `/orgs/${orgId}/pages/${pageId}/reels/${reelId}`;
}

export function runPath(orgId: string, runId: string): string {
  return `/orgs/${orgId}/runs/${runId}`;
}

export function packagePath(orgId: string, runId: string): string {
  return `/orgs/${orgId}/packages/${runId}`;
}

function matchesOrg(orgId: string): boolean {
  return orgId === demoIds.orgId;
}

function findPage(orgId: string, pageId: string): PageOut | null {
  if (!matchesOrg(orgId)) {
    return null;
  }
  return pages.find((candidate) => candidate.id === pageId) ?? null;
}

function findReel(orgId: string, pageId: string, reelId: string): ReelOut | null {
  if (!matchesOrg(orgId)) {
    return null;
  }
  return reels.find((candidate) => candidate.page_id === pageId && candidate.id === reelId) ?? null;
}

function findRun(orgId: string, runId: string): RunDetailOut | null {
  if (!matchesOrg(orgId)) {
    return null;
  }
  return runs.find((candidate) => candidate.id === runId) ?? null;
}

function findPackage(orgId: string, runId: string): PackageDetailOut | null {
  if (!matchesOrg(orgId)) {
    return null;
  }
  return packages.find((candidate) => candidate.run_id === runId) ?? null;
}

function relatedRunForReel(orgId: string, reelId: string): RunDetailOut | null {
  if (!matchesOrg(orgId)) {
    return null;
  }
  return (
    runs.find((candidate) => {
      const reelIdValue = candidate.input_params.reel_id;
      return typeof reelIdValue === 'string' && reelIdValue === reelId;
    }) ?? null
  );
}

export async function getRelatedRunForReel(
  orgId: string,
  reelId: string,
): Promise<RunDetailOut | null> {
  return relatedRunForReel(orgId, reelId);
}

export async function getWorkspaceSummary(orgId: string): Promise<WorkspaceSummary | null> {
  if (!matchesOrg(orgId)) {
    return null;
  }
  return {
    orgId,
    pages: [...pages],
    runs: [...runs],
    packages: [...packages],
  };
}

export async function getPageDetail(
  orgId: string,
  pageId: string,
): Promise<PageDetailRecord | null> {
  const currentPage = findPage(orgId, pageId);
  if (currentPage === null) {
    return null;
  }

  const recentReels = reels
    .filter((candidate) => candidate.page_id === pageId)
    .sort((left, right) => right.created_at.localeCompare(left.created_at));

  return {
    page: currentPage,
    policy: pageId === page.id ? pagePolicy : null,
    recentReels,
  };
}

export async function getReelDetail(
  orgId: string,
  pageId: string,
  reelId: string,
): Promise<ReelDetailRecord | null> {
  const currentPage = findPage(orgId, pageId);
  const currentReel = findReel(orgId, pageId, reelId);
  if (currentPage === null || currentReel === null) {
    return null;
  }

  const relatedRun = relatedRunForReel(orgId, reelId);
  return {
    page: currentPage,
    reel: currentReel,
    relatedRun,
    packageDetail: relatedRun === null ? null : findPackage(orgId, relatedRun.id),
  };
}

export async function getRunDetail(orgId: string, runId: string): Promise<RunDetailRecord | null> {
  const run = findRun(orgId, runId);
  if (run === null) {
    return null;
  }

  const pageId = run.input_params.page_id;
  const reelId = run.input_params.reel_id;
  const currentPage = typeof pageId === 'string' ? findPage(orgId, pageId) : null;
  const currentReel =
    typeof pageId === 'string' && typeof reelId === 'string'
      ? findReel(orgId, pageId, reelId)
      : null;

  return {
    run,
    page: currentPage,
    reel: currentReel,
    packageDetail: findPackage(orgId, runId),
  };
}

export async function getPackageDetail(
  orgId: string,
  runId: string,
): Promise<PackageRecord | null> {
  const currentPackage = findPackage(orgId, runId);
  const run = findRun(orgId, runId);
  if (currentPackage === null || run === null) {
    return null;
  }

  const pageId = run.input_params.page_id;
  const reelId = run.input_params.reel_id;
  const currentPage = typeof pageId === 'string' ? findPage(orgId, pageId) : null;
  const currentReel =
    typeof pageId === 'string' && typeof reelId === 'string'
      ? findReel(orgId, pageId, reelId)
      : null;

  return {
    packageDetail: currentPackage,
    run,
    page: currentPage,
    reel: currentReel,
  };
}
