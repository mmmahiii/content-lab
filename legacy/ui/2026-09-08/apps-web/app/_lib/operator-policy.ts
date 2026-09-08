import type { PagePolicyStateOut, PolicyStateDocument } from '@shared/types';

import {
  type OperatorContext,
  type OwnedPage,
  type Resource,
  loadOwnedPages,
  resolveOperatorContext,
} from './operator-dashboard';

export type PolicyEditorSource = 'saved' | 'inherited';

/** Maps API page-policy view to editor source; explicit overrides are auditable saves, else inherited effective state. */
export function policyEditorSourceFromApi(policy: PagePolicyStateOut): PolicyEditorSource {
  return policy.is_explicit_override ? 'saved' : 'inherited';
}

export type PolicyEditorRecord = {
  page: OwnedPage;
  policy: PagePolicyStateOut;
  baseline: PolicyStateDocument;
  draft: PolicyStateDocument;
  source: PolicyEditorSource;
};

export type PolicyEditorSnapshot = {
  context: OperatorContext;
  policies: Resource<PolicyEditorRecord[]>;
};

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

async function fetchPagePolicy(context: OperatorContext, pageId: string): Promise<PagePolicyStateOut> {
  const response = await fetch(
    `${context.apiBaseUrl}/orgs/${context.orgId}/policy/page/${pageId}`,
    {
      cache: 'no-store',
      headers: {
        Accept: 'application/json',
      },
    },
  );

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

  return (await response.json()) as PagePolicyStateOut;
}

export async function loadPolicyEditorSnapshot(): Promise<PolicyEditorSnapshot> {
  const context = await resolveOperatorContext();

  if (!context.orgId) {
    const message =
      context.configurationMessage ??
      'Choose a workspace org in the console sidebar so page policy can be loaded.';

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
  let inheritedCount = 0;

  for (const response of policyResponses) {
    if (response.status !== 'fulfilled') {
      failedPages += 1;
      continue;
    }

    const policy = response.value.policy;
    if (!policy.is_explicit_override) {
      inheritedCount += 1;
    }

    policies.push({
      page: response.value.page,
      policy,
      baseline: clonePolicyState(policy.state),
      draft: clonePolicyState(policy.state),
      source: policyEditorSourceFromApi(policy),
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
  if (inheritedCount > 0) {
    notes.push(
      `${inheritedCount} page ${inheritedCount === 1 ? 'is' : 'are'} inheriting org-wide or built-in guardrails until a saved page override exists.`,
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
