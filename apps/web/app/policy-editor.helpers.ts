import type { PolicySectionKey, PolicyStateDocument } from '@shared/types';

import type {
  FieldErrors,
  SubmissionDefinition,
  ValidationResult,
} from './operator-console.helpers';

const POLICY_SECTIONS: PolicySectionKey[] = ['mode_ratios', 'budget', 'thresholds'];

export type PolicyEditorField = 'actorId' | PolicySectionKey;

export type PolicyEditorFormValues = {
  actorId: string;
  state: PolicyStateDocument;
};

function isFiniteNumber(value: number): boolean {
  return Number.isFinite(value);
}

function validateUnitInterval(value: number): boolean {
  return isFiniteNumber(value) && value >= 0 && value <= 1;
}

function validateNonNegative(value: number): boolean {
  return isFiniteNumber(value) && value >= 0;
}

function normalizeActorId(value: string): string | null {
  const normalized = value.trim();
  return normalized.length > 0 ? normalized : null;
}

export function clonePolicyDocument(policy: PolicyStateDocument): PolicyStateDocument {
  return {
    mode_ratios: { ...policy.mode_ratios },
    budget: { ...policy.budget },
    thresholds: {
      similarity: { ...policy.thresholds.similarity },
      min_quality_score: policy.thresholds.min_quality_score,
    },
  };
}

export function createPolicyUpdateSubmission({
  orgId,
  pageId,
  form,
}: {
  orgId: string;
  pageId: string;
  form: PolicyEditorFormValues;
}): ValidationResult<SubmissionDefinition, PolicyEditorField> {
  const fieldErrors: FieldErrors<PolicyEditorField> = {};
  const actorId = normalizeActorId(form.actorId);
  const { mode_ratios, budget, thresholds } = form.state;

  if (!actorId) {
    fieldErrors.actorId = 'Operator actor ID is required before saving page policy.';
  }

  const ratioValues = Object.values(mode_ratios);
  if (!ratioValues.every(validateUnitInterval)) {
    fieldErrors.mode_ratios = 'Each mode ratio must stay between 0.00 and 1.00.';
  } else {
    const total = ratioValues.reduce((sum, value) => sum + value, 0);
    if (Math.abs(total - 1) > 1e-6) {
      fieldErrors.mode_ratios = 'Mode ratios must sum to 1.00.';
    }
  }

  const budgetValues = Object.values(budget);
  if (!budgetValues.every(validateNonNegative)) {
    fieldErrors.budget = 'Budget guardrails must be finite non-negative numbers.';
  } else if (budget.per_run_usd_limit > budget.daily_usd_limit) {
    fieldErrors.budget = 'Per-run budget must not exceed the daily budget.';
  } else if (budget.daily_usd_limit > budget.monthly_usd_limit) {
    fieldErrors.budget = 'Daily budget must not exceed the monthly budget.';
  }

  const similarity = thresholds.similarity;
  if (
    !validateUnitInterval(similarity.warn_at) ||
    !validateUnitInterval(similarity.block_at) ||
    !validateUnitInterval(thresholds.min_quality_score)
  ) {
    fieldErrors.thresholds =
      'Similarity guardrails and minimum QA score must stay between 0.00 and 1.00.';
  } else if (similarity.warn_at >= similarity.block_at) {
    fieldErrors.thresholds =
      'Similarity warning threshold must stay lower than the block threshold.';
  }

  if (Object.keys(fieldErrors).length > 0 || actorId === null) {
    return {
      ok: false,
      fieldErrors,
      summary: [
        fieldErrors.actorId,
        ...POLICY_SECTIONS.map((section) => fieldErrors[section]),
      ].filter((value): value is string => Boolean(value)),
    };
  }

  return {
    ok: true,
    value: {
      actionLabel: 'Save Policy',
      actionPath: `/orgs/${orgId}/policy/page/${pageId}`,
      successTitle: 'Page policy saved',
      body: JSON.stringify(form.state),
      headers: {
        'Content-Type': 'application/json',
        'X-Actor-Id': actorId,
      },
    },
  };
}
