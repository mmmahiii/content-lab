import type { PolicyStateDocument, PolicyStateOut } from '@shared/types';

import {
  type OperatorContext,
  type OwnedPage,
  type Resource,
  loadOwnedPages,
  resolveOperatorContext,
} from './operator-dashboard';

type PolicyEditorSource = 'saved' | 'default';

export type PolicyEditorRecord = {
  page: OwnedPage;
  policy: PolicyStateOut | null;
  baseline: PolicyStateDocument;
  draft: PolicyStateDocument;
  source: PolicyEditorSource;
};

export type PolicyEditorSnapshot = {
  context: OperatorContext;
  policies: Resource<PolicyEditorRecord[]>;
};

function createDefaultPolicyState(): PolicyStateDocument {
  return {
    mode_ratios: {
      exploit: 0.3,
      explore: 0.4,
      mutation: 0.2,
      chaos: 0.1,
    },
    budget: {
      per_run_usd_limit: 10,
      daily_usd_limit: 40,
      monthly_usd_limit: 800,
    },
    thresholds: {
      similarity: {
        warn_at: 0.72,
        block_at: 0.88,
      },
      min_quality_score: 0.55,
    },
  };
}

function clonePolicyState(policy: PolicyStateDocument): PolicyStateDocument {
  return {
    mode_ratios: { ...policy.mode_ratios },
    budget: { ...policy.budget },
    thresholds: {
      similarity: { ...policy.thresholds.similarity },
      min_quality_score: policy.thresholds.min_quality_score,
    },
  };
}

async function fetchPagePolicy(
  context: OperatorContext,
  pageId: string,
): Promise<PolicyStateOut | null> {
  const response = await fetch(
    `${context.apiBaseUrl}/orgs/${context.orgId}/policy/page/${pageId}`,
    {
      cache: 'no-store',
      headers: {
        Accept: 'application/json',
      },
    },
  );

  if (response.status === 404) {
    return null;
  }

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`.trim();

    try {
      const payload = (await response.json()) as { detail?: unknown };
      if (typeof payload.detail === 'string' && payload.detail.trim().length > 0) {
        detail = payload.detail.trim();
      }
    } catch {
      // Ignore parse failures and fall back to the status text.
    }

    throw new Error(detail);
  }

  return (await response.json()) as PolicyStateOut;
}

export async function loadPolicyEditorSnapshot(): Promise<PolicyEditorSnapshot> {
  const context = resolveOperatorContext();

  if (!context.orgId) {
    const message =
      context.configurationMessage ??
      'Set CONTENT_LAB_OPERATOR_ORG_ID to an org UUID so page policy can be loaded.';

    return {
      context,
      policies: {
        state: 'unconfigured',
        data: [],
        message,
      },
    };
  }

  const pages = await loadOwnedPages(context);
  if (pages.state !== 'ready') {
    const message =
      pages.message ??
      (pages.state === 'empty'
        ? 'Page policy appears after owned pages are registered.'
        : 'Page policy could not be loaded because the owned page feed is unavailable.');

    return {
      context,
      policies: {
        state: pages.state,
        data: [],
        message,
      },
    };
  }

  const policyResponses = await Promise.allSettled(
    pages.data.map(async (page) => ({
      page,
      policy: await fetchPagePolicy(context, page.id),
    })),
  );

  const policies: PolicyEditorRecord[] = [];
  let failedPages = 0;
  let defaultCount = 0;

  for (const response of policyResponses) {
    if (response.status !== 'fulfilled') {
      failedPages += 1;
      continue;
    }

    const policy = response.value.policy;
    if (policy === null) {
      defaultCount += 1;
    }

    policies.push({
      page: response.value.page,
      policy,
      baseline: clonePolicyState(policy?.state ?? createDefaultPolicyState()),
      draft: clonePolicyState(policy?.state ?? createDefaultPolicyState()),
      source: policy === null ? 'default' : 'saved',
    });
  }

  if (policies.length === 0 && failedPages > 0) {
    return {
      context,
      policies: {
        state: 'error',
        data: [],
        message: 'Page policy could not be loaded from the API.',
      },
    };
  }

  if (policies.length === 0) {
    return {
      context,
      policies: {
        state: 'empty',
        data: [],
        message: 'No owned pages are available for policy editing yet.',
      },
    };
  }

  const notes: string[] = [];
  if (defaultCount > 0) {
    notes.push(
      `${defaultCount} page ${defaultCount === 1 ? 'is' : 'are'} using default phase-1 guardrails until a saved page policy exists.`,
    );
  }
  if (failedPages > 0) {
    notes.push(
      `Skipped ${failedPages} page policy request${failedPages === 1 ? '' : 's'} due to API errors.`,
    );
  }

  return {
    context,
    policies: {
      state: 'ready',
      data: policies,
      message: notes.join(' '),
    },
  };
}
