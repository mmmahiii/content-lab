import type {
  JsonObject,
  PackageDetailOut,
  PageOut,
  PolicyStateOut,
  ReelOut,
  RunDetailOut,
  RunOut,
} from '@shared/types';

import {
  DEFAULT_API_BASE_URL,
  resolveOperatorContext,
} from './operator-dashboard';
import {
  demoIds,
  getPackageDetail,
  getPageDetail,
  getReelDetail,
  getRunDetail,
  getWorkspaceSummary,
} from './content-lab-data';
import type { OperatorContextSource } from './operator-context';

type WorkspaceContext = {
  apiBaseUrl: string;
  orgId: string;
  source: OperatorContextSource;
};

export type PageWorkspaceRun = {
  run: RunOut;
  pageId: string | null;
  reelId: string | null;
  hasPackage: boolean;
};

export type PageWorkspaceReel = {
  reel: ReelOut;
  relatedRunId: string | null;
  relatedRunStatus: string | null;
  hasPackage: boolean;
};

export type PageWorkspaceSnapshot = {
  context: WorkspaceContext;
  page: PageOut;
  reels: PageWorkspaceReel[];
  runs: PageWorkspaceRun[];
  policy: PolicyStateOut | null;
};

export type OperatorReelDetailSnapshot = {
  context: WorkspaceContext;
  page: PageOut;
  reel: ReelOut;
  relatedRun: RunDetailOut | null;
  packageDetail: PackageDetailOut | null;
};

export type OperatorRunDetailSnapshot = {
  context: WorkspaceContext;
  run: RunDetailOut;
  page: PageOut | null;
  reel: ReelOut | null;
  packageDetail: PackageDetailOut | null;
};

export type OperatorPackageDetailSnapshot = {
  context: WorkspaceContext;
  packageDetail: PackageDetailOut;
  run: RunDetailOut;
  page: PageOut | null;
  reel: ReelOut | null;
};

function asRecord(value: unknown): JsonObject | null {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    return null;
  }

  return value as JsonObject;
}

function readString(record: JsonObject | null, key: string): string | null {
  if (record === null) {
    return null;
  }

  const value = record[key];
  return typeof value === 'string' && value.length > 0 ? value : null;
}

function hasPackagePayload(run: Pick<RunOut, 'output_payload'>): boolean {
  const payload = asRecord(run.output_payload);
  const nestedPackage = asRecord(payload?.package);
  const candidate = nestedPackage ?? payload;

  if (candidate === null) {
    return false;
  }

  return ['artifacts', 'manifest', 'manifest_uri', 'package_root_uri', 'provenance'].some(
    (key) => candidate[key] !== undefined,
  );
}

function runPageId(run: Pick<RunOut, 'input_params' | 'run_metadata'>): string | null {
  return (
    readString(asRecord(run.input_params), 'page_id') ??
    readString(asRecord(asRecord(run.run_metadata)?.target), 'page_id')
  );
}

function runReelId(run: Pick<RunOut, 'input_params' | 'run_metadata'>): string | null {
  return (
    readString(asRecord(run.input_params), 'reel_id') ??
    readString(asRecord(asRecord(run.run_metadata)?.target), 'reel_id')
  );
}

function relatedRunIdFromReel(reel: ReelOut): string | null {
  return readString(asRecord(asRecord(reel.metadata)?.process_reel), 'last_run_id');
}

async function loadWorkspaceContext(orgId: string): Promise<WorkspaceContext> {
  try {
    const context = await resolveOperatorContext();
    return {
      apiBaseUrl: context.apiBaseUrl,
      orgId,
      source: context.source,
    };
  } catch {
    return {
      apiBaseUrl: DEFAULT_API_BASE_URL,
      orgId,
      source: 'unconfigured',
    };
  }
}

async function fetchJson<T>(apiBaseUrl: string, path: string): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    cache: 'no-store',
    headers: {
      Accept: 'application/json',
    },
  });

  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`.trim());
  }

  return (await response.json()) as T;
}

async function fetchOptionalJson<T>(apiBaseUrl: string, path: string): Promise<T | null> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    cache: 'no-store',
    headers: {
      Accept: 'application/json',
    },
  });

  if (response.status === 404) {
    return null;
  }

  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`.trim());
  }

  return (await response.json()) as T;
}

function isDemoOrg(orgId: string): boolean {
  return orgId === demoIds.orgId;
}

function buildPageWorkspaceRuns(runs: RunOut[], pageId: string): PageWorkspaceRun[] {
  return runs
    .map((run) => ({
      run,
      pageId: runPageId(run),
      reelId: runReelId(run),
      hasPackage: hasPackagePayload(run),
    }))
    .filter((entry) => entry.pageId === pageId)
    .sort((left, right) => {
      const byUpdated = right.run.updated_at.localeCompare(left.run.updated_at);
      if (byUpdated !== 0) {
        return byUpdated;
      }

      return right.run.id.localeCompare(left.run.id);
    });
}

function buildPageWorkspaceReels(
  reels: ReelOut[],
  runs: PageWorkspaceRun[],
): PageWorkspaceReel[] {
  const newestRunByReelId = new Map<string, PageWorkspaceRun>();

  runs.forEach((entry) => {
    if (entry.reelId && !newestRunByReelId.has(entry.reelId)) {
      newestRunByReelId.set(entry.reelId, entry);
    }
  });

  return reels.map((reel) => {
    const metadataRunId = relatedRunIdFromReel(reel);
    const relatedRun =
      (metadataRunId ? runs.find((entry) => entry.run.id === metadataRunId) : null) ??
      newestRunByReelId.get(reel.id) ??
      null;

    return {
      reel,
      relatedRunId: relatedRun?.run.id ?? metadataRunId,
      relatedRunStatus: relatedRun?.run.status ?? null,
      hasPackage: relatedRun?.hasPackage ?? false,
    };
  });
}

async function loadDemoPageWorkspaceSnapshot(
  orgId: string,
  pageId: string,
): Promise<PageWorkspaceSnapshot | null> {
  const context = await loadWorkspaceContext(orgId);
  const pageDetail = await getPageDetail(orgId, pageId);
  const workspace = await getWorkspaceSummary(orgId);

  if (pageDetail === null || workspace === null) {
    return null;
  }

  const runs = buildPageWorkspaceRuns(workspace.runs, pageId);
  const reels = buildPageWorkspaceReels(pageDetail.recentReels, runs);

  return {
    context,
    page: pageDetail.page,
    reels,
    runs,
    policy: pageDetail.policy,
  };
}

export async function loadPageWorkspaceSnapshot(
  orgId: string,
  pageId: string,
): Promise<PageWorkspaceSnapshot | null> {
  if (isDemoOrg(orgId)) {
    return loadDemoPageWorkspaceSnapshot(orgId, pageId);
  }

  const context = await loadWorkspaceContext(orgId);
  const page = await fetchOptionalJson<PageOut>(context.apiBaseUrl, `/orgs/${orgId}/pages/${pageId}`);
  if (page === null) {
    return null;
  }

  const [reels, runs, policy] = await Promise.all([
    fetchJson<ReelOut[]>(context.apiBaseUrl, `/orgs/${orgId}/pages/${pageId}/reels`),
    fetchJson<RunOut[]>(context.apiBaseUrl, `/orgs/${orgId}/pages/${pageId}/runs`),
    fetchOptionalJson<PolicyStateOut>(context.apiBaseUrl, `/orgs/${orgId}/policy/page/${pageId}`),
  ]);

  const pageRuns = buildPageWorkspaceRuns(runs, pageId);
  return {
    context,
    page,
    reels: buildPageWorkspaceReels(reels, pageRuns),
    runs: pageRuns,
    policy,
  };
}

export async function loadOperatorReelDetail(
  orgId: string,
  pageId: string,
  reelId: string,
): Promise<OperatorReelDetailSnapshot | null> {
  if (isDemoOrg(orgId)) {
    const context = await loadWorkspaceContext(orgId);
    const detail = await getReelDetail(orgId, pageId, reelId);
    if (detail === null) {
      return null;
    }

    return {
      context,
      page: detail.page,
      reel: detail.reel,
      relatedRun: detail.relatedRun,
      packageDetail: detail.packageDetail,
    };
  }

  const context = await loadWorkspaceContext(orgId);
  const [page, reel] = await Promise.all([
    fetchOptionalJson<PageOut>(context.apiBaseUrl, `/orgs/${orgId}/pages/${pageId}`),
    fetchOptionalJson<ReelOut>(context.apiBaseUrl, `/orgs/${orgId}/pages/${pageId}/reels/${reelId}`),
  ]);

  if (page === null || reel === null) {
    return null;
  }

  let relatedRunId = relatedRunIdFromReel(reel);
  if (relatedRunId === null) {
    const pageRuns = await fetchJson<RunOut[]>(
      context.apiBaseUrl,
      `/orgs/${orgId}/pages/${pageId}/runs`,
    );
    relatedRunId =
      buildPageWorkspaceRuns(pageRuns, pageId).find((entry) => entry.reelId === reelId)?.run.id ??
      null;
  }

  const relatedRun =
    relatedRunId === null
      ? null
      : await fetchOptionalJson<RunDetailOut>(context.apiBaseUrl, `/orgs/${orgId}/runs/${relatedRunId}`);
  const packageDetail =
    relatedRunId === null
      ? null
      : await fetchOptionalJson<PackageDetailOut>(
          context.apiBaseUrl,
          `/orgs/${orgId}/packages/${relatedRunId}`,
        );

  return {
    context,
    page,
    reel,
    relatedRun,
    packageDetail,
  };
}

export async function loadOperatorRunDetail(
  orgId: string,
  runId: string,
): Promise<OperatorRunDetailSnapshot | null> {
  if (isDemoOrg(orgId)) {
    const context = await loadWorkspaceContext(orgId);
    const detail = await getRunDetail(orgId, runId);
    if (detail === null) {
      return null;
    }

    return {
      context,
      run: detail.run,
      page: detail.page,
      reel: detail.reel,
      packageDetail: detail.packageDetail,
    };
  }

  const context = await loadWorkspaceContext(orgId);
  const run = await fetchOptionalJson<RunDetailOut>(context.apiBaseUrl, `/orgs/${orgId}/runs/${runId}`);
  if (run === null) {
    return null;
  }

  const pageId = runPageId(run);
  const reelId = runReelId(run);
  const [page, reel, packageDetail] = await Promise.all([
    pageId === null
      ? Promise.resolve(null)
      : fetchOptionalJson<PageOut>(context.apiBaseUrl, `/orgs/${orgId}/pages/${pageId}`),
    pageId === null || reelId === null
      ? Promise.resolve(null)
      : fetchOptionalJson<ReelOut>(
          context.apiBaseUrl,
          `/orgs/${orgId}/pages/${pageId}/reels/${reelId}`,
        ),
    fetchOptionalJson<PackageDetailOut>(context.apiBaseUrl, `/orgs/${orgId}/packages/${runId}`),
  ]);

  return {
    context,
    run,
    page,
    reel,
    packageDetail,
  };
}

export async function loadOperatorPackageDetail(
  orgId: string,
  runId: string,
): Promise<OperatorPackageDetailSnapshot | null> {
  if (isDemoOrg(orgId)) {
    const context = await loadWorkspaceContext(orgId);
    const detail = await getPackageDetail(orgId, runId);
    if (detail === null) {
      return null;
    }

    return {
      context,
      packageDetail: detail.packageDetail,
      run: detail.run,
      page: detail.page,
      reel: detail.reel,
    };
  }

  const context = await loadWorkspaceContext(orgId);
  const [packageDetail, run] = await Promise.all([
    fetchOptionalJson<PackageDetailOut>(context.apiBaseUrl, `/orgs/${orgId}/packages/${runId}`),
    fetchOptionalJson<RunDetailOut>(context.apiBaseUrl, `/orgs/${orgId}/runs/${runId}`),
  ]);

  if (packageDetail === null || run === null) {
    return null;
  }

  const pageId = runPageId(run);
  const reelId = runReelId(run);
  const [page, reel] = await Promise.all([
    pageId === null
      ? Promise.resolve(null)
      : fetchOptionalJson<PageOut>(context.apiBaseUrl, `/orgs/${orgId}/pages/${pageId}`),
    pageId === null || reelId === null
      ? Promise.resolve(null)
      : fetchOptionalJson<ReelOut>(
          context.apiBaseUrl,
          `/orgs/${orgId}/pages/${pageId}/reels/${reelId}`,
        ),
  ]);

  return {
    context,
    packageDetail,
    run,
    page,
    reel,
  };
}
