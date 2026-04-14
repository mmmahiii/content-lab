import { cookies } from 'next/headers';

import type { ReviewQueueState } from '@shared/types';

import {
  OPERATOR_ORG_COOKIE,
  resolveOperatorOrgId,
  type OperatorContextSource,
} from './operator-context';

export type ResourceState = 'ready' | 'empty' | 'error' | 'unconfigured';
export type PackageStatus = 'ready' | 'failed' | 'pending' | 'not_started';
type JsonRecord = Record<string, unknown>;

export type Resource<T> = {
  state: ResourceState;
  data: T;
  message?: string;
};

export type OperatorContext = {
  apiBaseUrl: string;
  orgId: string | null;
  source: OperatorContextSource;
  configurationMessage?: string;
};

export type OwnedPage = {
  id: string;
  displayName: string;
  platform: string;
  handle: string | null;
  ownership: string;
  updatedAt: string;
};

export type RecentReel = {
  id: string;
  pageId: string;
  pageName: string;
  variantLabel: string;
  origin: string;
  status: string;
  createdAt: string;
  updatedAt: string;
  currentStep: string | null;
  lastRunId: string | null;
  packageStatus: PackageStatus;
  packageMessage: string | null;
};

export type CurrentRun = {
  id: string;
  workflowKey: string;
  flowTrigger: string;
  status: string;
  updatedAt: string;
  externalRef: string | null;
  taskSummary: string;
  currentStep: string | null;
  pageName: string | null;
  reelId: string | null;
  packageStatus: PackageStatus;
};

export type ReviewQueueItem = {
  id: string;
  pageId: string;
  pageName: string;
  variantLabel: string;
  status: string;
  queueState: ReviewQueueState;
  updatedAt: string;
  currentStep: string | null;
  lastRunId: string | null;
  packageStatus: PackageStatus;
  packageMessage: string | null;
};

export type OperatorDashboardSnapshot = {
  context: OperatorContext;
  pages: Resource<OwnedPage[]>;
  reels: Resource<RecentReel[]>;
  runs: Resource<CurrentRun[]>;
};

type ApiPage = {
  id: string;
  display_name: string;
  platform: string;
  handle: string | null;
  ownership: string;
  updated_at: string;
};

type ApiReel = {
  id: string;
  page_id: string;
  origin: string;
  status: string;
  variant_label: string | null;
  metadata: JsonRecord;
  created_at: string;
  updated_at: string;
};

type ApiRunTask = {
  task_type: string;
  status: string;
};

type ApiRunDetail = {
  id: string;
  workflow_key: string;
  flow_trigger: string;
  status: string;
  external_ref: string | null;
  updated_at: string;
  output_payload: JsonRecord | null;
  run_metadata: JsonRecord;
  task_status_counts: Record<string, number>;
  tasks: ApiRunTask[];
};

export const DEFAULT_API_BASE_URL = 'http://127.0.0.1:8000';
const MAX_RECENT_REELS = 8;
const MAX_CURRENT_RUNS = 6;

function readyResource<T>(data: T, message?: string): Resource<T> {
  return { state: 'ready', data, message };
}

function emptyResource<T>(data: T, message: string): Resource<T> {
  return { state: 'empty', data, message };
}

function errorResource<T>(data: T, message: string): Resource<T> {
  return { state: 'error', data, message };
}

function unconfiguredResource<T>(data: T, message: string): Resource<T> {
  return { state: 'unconfigured', data, message };
}

function asRecord(value: unknown): JsonRecord | null {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    return null;
  }

  return value as JsonRecord;
}

function readString(record: JsonRecord | null, key: string): string | null {
  if (record === null) {
    return null;
  }

  const value = record[key];
  return typeof value === 'string' && value.length > 0 ? value : null;
}

function readBoolean(record: JsonRecord | null, key: string): boolean | null {
  if (record === null) {
    return null;
  }

  const value = record[key];
  return typeof value === 'boolean' ? value : null;
}

export async function resolveOperatorContext(): Promise<OperatorContext> {
  const apiBaseUrl = (
    process.env.CONTENT_LAB_API_BASE_URL ??
    process.env.NEXT_PUBLIC_CONTENT_LAB_API_BASE_URL ??
    DEFAULT_API_BASE_URL
  ).replace(/\/$/, '');
  let cookieOrgId: string | undefined;

  try {
    const cookieStore = await cookies();
    cookieOrgId = cookieStore.get(OPERATOR_ORG_COOKIE)?.value;
  } catch {
    cookieOrgId = undefined;
  }

  const selection = resolveOperatorOrgId({
    cookieOrgId,
    envOrgId:
      process.env.CONTENT_LAB_OPERATOR_ORG_ID ??
      process.env.NEXT_PUBLIC_CONTENT_LAB_OPERATOR_ORG_ID,
  });

  if (!selection.orgId) {
    return {
      apiBaseUrl,
      source: 'unconfigured',
      orgId: null,
      configurationMessage:
        'Choose a workspace org in the console sidebar, or set CONTENT_LAB_OPERATOR_ORG_ID, so the operator dashboard can load live API data.',
    };
  }

  return { apiBaseUrl, orgId: selection.orgId, source: selection.source };
}

function buildUrl(context: OperatorContext, path: string): string {
  return `${context.apiBaseUrl}${path}`;
}

async function fetchJson<T>(context: OperatorContext, path: string): Promise<T> {
  const response = await fetch(buildUrl(context, path), {
    cache: 'no-store',
    headers: {
      Accept: 'application/json',
    },
  });

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;

    try {
      const payload = (await response.json()) as JsonRecord;
      const responseDetail = readString(payload, 'detail');
      if (responseDetail) {
        detail = responseDetail;
      }
    } catch {
      // Ignore parse failures and fall back to the HTTP status.
    }

    throw new Error(detail);
  }

  return (await response.json()) as T;
}

function derivePackageStatus(metadata: JsonRecord): {
  status: PackageStatus;
  message: string | null;
} {
  const packageRecord = asRecord(metadata.package);
  const packageQa = asRecord(packageRecord?.package_qa);
  const manifest = asRecord(packageRecord?.manifest);
  const qaPassed = readBoolean(packageQa, 'passed');
  const qaMessage = readString(packageQa, 'message');
  const manifestComplete = readBoolean(manifest, 'complete');

  if (qaPassed === true || manifestComplete === true) {
    return { status: 'ready', message: qaMessage ?? 'Package is ready for operator review.' };
  }

  if (qaPassed === false) {
    return { status: 'failed', message: qaMessage ?? 'Package QA failed.' };
  }

  if (packageRecord !== null) {
    return {
      status: 'pending',
      message: 'Packaging metadata exists, but the package is not ready yet.',
    };
  }

  return { status: 'not_started', message: 'Packaging has not started yet.' };
}

function getProcessReelMetadata(metadata: JsonRecord): JsonRecord | null {
  return asRecord(metadata.process_reel);
}

export async function loadOwnedPages(context: OperatorContext): Promise<Resource<OwnedPage[]>> {
  try {
    const pages = await fetchJson<ApiPage[]>(
      context,
      `/orgs/${context.orgId}/pages?ownership=owned`,
    );

    if (pages.length === 0) {
      return emptyResource([], 'No owned pages are registered for this org yet.');
    }

    return readyResource(
      pages.map((page) => ({
        id: page.id,
        displayName: page.display_name,
        platform: page.platform,
        handle: page.handle,
        ownership: page.ownership,
        updatedAt: page.updated_at,
      })),
    );
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Owned pages could not be loaded.';
    return errorResource([], message);
  }
}

async function loadRecentReels(
  context: OperatorContext,
  pages: OwnedPage[],
): Promise<Resource<RecentReel[]>> {
  const reelResponses = await Promise.allSettled(
    pages.map(async (page) => ({
      page,
      reels: await fetchJson<ApiReel[]>(context, `/orgs/${context.orgId}/pages/${page.id}/reels`),
    })),
  );

  const loadedReels: RecentReel[] = [];
  let failedPages = 0;

  for (const result of reelResponses) {
    if (result.status !== 'fulfilled') {
      failedPages += 1;
      continue;
    }

    for (const reel of result.value.reels) {
      const metadata = asRecord(reel.metadata) ?? {};
      const processReel = getProcessReelMetadata(metadata);
      const packageState = derivePackageStatus(metadata);

      loadedReels.push({
        id: reel.id,
        pageId: reel.page_id,
        pageName: result.value.page.displayName,
        variantLabel: reel.variant_label ?? 'Untitled variant',
        origin: reel.origin,
        status: reel.status,
        createdAt: reel.created_at,
        updatedAt: reel.updated_at,
        currentStep: readString(processReel, 'current_step'),
        lastRunId: readString(processReel, 'last_run_id'),
        packageStatus: packageState.status,
        packageMessage: packageState.message,
      });
    }
  }

  loadedReels.sort((left, right) => right.createdAt.localeCompare(left.createdAt));

  if (loadedReels.length === 0 && failedPages > 0) {
    return errorResource([], 'Recent reels could not be loaded from the API.');
  }

  if (loadedReels.length === 0) {
    return emptyResource([], 'No reels have been created for the owned pages yet.');
  }

  const message =
    failedPages > 0
      ? `Skipped ${failedPages} page feed${failedPages === 1 ? '' : 's'} due to API errors.`
      : undefined;

  return readyResource(loadedReels.slice(0, MAX_RECENT_REELS), message);
}

function buildTaskSummary(taskCounts: Record<string, number>): string {
  const parts = Object.entries(taskCounts)
    .filter(([, count]) => count > 0)
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([status, count]) => `${count} ${status}`);

  return parts.length > 0 ? parts.join(', ') : 'No task activity yet';
}

function deriveRunPackageStatus(run: ApiRunDetail, matchedReel: RecentReel | null): PackageStatus {
  const outputPayload = asRecord(run.output_payload);
  const summaryPackage = asRecord(outputPayload?.package);

  if (summaryPackage !== null) {
    return derivePackageStatus({ package: summaryPackage }).status;
  }

  return matchedReel?.packageStatus ?? 'not_started';
}

function deriveCurrentStep(run: ApiRunDetail, matchedReel: RecentReel | null): string | null {
  const runningTask = run.tasks.find((task) => task.status === 'running');
  if (runningTask) {
    return runningTask.task_type;
  }

  return matchedReel?.currentStep ?? null;
}

async function loadCurrentRuns(
  context: OperatorContext,
  reels: RecentReel[],
): Promise<Resource<CurrentRun[]>> {
  const reelByRunId = new Map<string, RecentReel>();

  for (const reel of reels) {
    if (reel.lastRunId && !reelByRunId.has(reel.lastRunId)) {
      reelByRunId.set(reel.lastRunId, reel);
    }
  }

  const runIds = Array.from(reelByRunId.keys());
  if (runIds.length === 0) {
    return emptyResource([], 'No reel-triggered runs are visible yet.');
  }

  const runResponses = await Promise.allSettled(
    runIds.map(
      async (runId) =>
        await fetchJson<ApiRunDetail>(context, `/orgs/${context.orgId}/runs/${runId}`),
    ),
  );

  const loadedRuns: CurrentRun[] = [];
  let failedRuns = 0;

  for (const result of runResponses) {
    if (result.status !== 'fulfilled') {
      failedRuns += 1;
      continue;
    }

    const run = result.value;
    const target = asRecord(run.run_metadata.target);
    const matchedReel = reelByRunId.get(run.id) ?? null;

    loadedRuns.push({
      id: run.id,
      workflowKey: run.workflow_key,
      flowTrigger: run.flow_trigger,
      status: run.status,
      updatedAt: run.updated_at,
      externalRef: run.external_ref,
      taskSummary: buildTaskSummary(run.task_status_counts),
      currentStep: deriveCurrentStep(run, matchedReel),
      pageName: matchedReel?.pageName ?? null,
      reelId: readString(target, 'reel_id'),
      packageStatus: deriveRunPackageStatus(run, matchedReel),
    });
  }

  loadedRuns.sort((left, right) => right.updatedAt.localeCompare(left.updatedAt));

  if (loadedRuns.length === 0 && failedRuns > 0) {
    return errorResource([], 'Current run detail could not be loaded from the API.');
  }

  if (loadedRuns.length === 0) {
    return emptyResource([], 'No current runs are available yet.');
  }

  const message =
    failedRuns > 0
      ? `Skipped ${failedRuns} run detail${failedRuns === 1 ? '' : 's'} due to API errors.`
      : undefined;

  return readyResource(loadedRuns.slice(0, MAX_CURRENT_RUNS), message);
}

export async function loadOperatorDashboard(): Promise<OperatorDashboardSnapshot> {
  const context = await resolveOperatorContext();

  if (!context.orgId) {
    const message =
      context.configurationMessage ??
      'Choose a workspace org in the console sidebar so the operator dashboard can load live API data.';

    return {
      context,
      pages: unconfiguredResource([], message),
      reels: unconfiguredResource([], message),
      runs: unconfiguredResource([], message),
    };
  }

  const pages = await loadOwnedPages(context);
  if (pages.state !== 'ready') {
    return {
      context,
      pages,
      reels:
        pages.state === 'empty'
          ? emptyResource([], 'Reels will appear after owned pages start generating content.')
          : errorResource(
              [],
              'Recent reels depend on the owned page feed and are currently unavailable.',
            ),
      runs:
        pages.state === 'empty'
          ? emptyResource([], 'Runs will appear once reels have been triggered for owned pages.')
          : errorResource(
              [],
              'Current runs depend on recent reel context and are currently unavailable.',
            ),
    };
  }

  const reels = await loadRecentReels(context, pages.data);
  const runs =
    reels.state === 'ready'
      ? await loadCurrentRuns(context, reels.data)
      : reels.state === 'empty'
        ? emptyResource([], 'Runs will appear after the first reel workflow starts.')
        : errorResource(
            [],
            'Current runs could not be assembled because reel activity is unavailable.',
          );

  return {
    context,
    pages,
    reels,
    runs,
  };
}

function deriveReviewQueueState(reel: RecentReel): ReviewQueueState | null {
  if (reel.status === 'posted') {
    return 'posted';
  }

  if (reel.status === 'qa_failed' || reel.packageStatus === 'failed') {
    return 'qa_failed';
  }

  if (reel.status === 'ready' || reel.packageStatus === 'ready') {
    return 'ready_for_review';
  }

  return null;
}

export function buildPackageReviewQueue(
  dashboard: OperatorDashboardSnapshot,
): Resource<ReviewQueueItem[]> {
  if (dashboard.reels.state !== 'ready') {
    if (dashboard.reels.state === 'empty') {
      return emptyResource(
        [],
        'Queue items appear after generated reels either pass QA, fail QA, or are marked posted.',
      );
    }

    return {
      state: dashboard.reels.state,
      data: [],
      message:
        dashboard.reels.message ??
        'Review queue depends on the recent reel feed and is currently unavailable.',
    };
  }

  const priority: Record<ReviewQueueState, number> = {
    ready_for_review: 0,
    qa_failed: 1,
    posted: 2,
  };

  const items = dashboard.reels.data
    .filter((reel) => reel.origin === 'generated')
    .map((reel) => {
      const queueState = deriveReviewQueueState(reel);
      if (queueState === null) {
        return null;
      }

      return {
        id: reel.id,
        pageId: reel.pageId,
        pageName: reel.pageName,
        variantLabel: reel.variantLabel,
        status: reel.status,
        queueState,
        updatedAt: reel.updatedAt,
        currentStep: reel.currentStep,
        lastRunId: reel.lastRunId,
        packageStatus: reel.packageStatus,
        packageMessage: reel.packageMessage,
      } satisfies ReviewQueueItem;
    })
    .filter((item): item is ReviewQueueItem => item !== null)
    .sort((left, right) => {
      const byState = priority[left.queueState] - priority[right.queueState];
      if (byState !== 0) {
        return byState;
      }

      return right.updatedAt.localeCompare(left.updatedAt);
    });

  if (items.length === 0) {
    return emptyResource(
      [],
      'No generated reels are currently ready for review, blocked by QA, or already posted.',
    );
  }

  const readyCount = items.filter((item) => item.queueState === 'ready_for_review').length;
  const qaFailedCount = items.filter((item) => item.queueState === 'qa_failed').length;
  const postedCount = items.filter((item) => item.queueState === 'posted').length;

  return readyResource(
    items,
    `${readyCount} ready for review, ${qaFailedCount} QA-failed, ${postedCount} posted.`,
  );
}
