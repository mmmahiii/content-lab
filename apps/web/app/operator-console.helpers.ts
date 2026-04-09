import type {
  ApiErrorResponse,
  ApiValidationIssue,
  JsonObject,
  ReelResponse,
  ReelTriggerRequest,
  RunCreateRequest,
  RunResponse,
  WorkflowKey,
} from '@shared/types';

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

const RESERVED_REEL_TRIGGER_KEYS = new Set(['org_id', 'page_id', 'reel_id', 'reel_family_id']);

export const DEFAULT_API_BASE_URL = 'http://127.0.0.1:8000';

export const HUMAN_BOUNDARY_COPY =
  'This console never posts to a social platform. Operators trigger workflows, review generated reels, and record manual posting only after a person has posted externally.';

export type FieldErrors<TField extends string> = Partial<Record<TField, string>>;

export type ValidationResult<TValue, TField extends string> =
  | {
      ok: true;
      value: TValue;
    }
  | {
      ok: false;
      fieldErrors: FieldErrors<TField>;
      summary: string[];
    };

export type SubmissionDefinition = {
  actionLabel: string;
  actionPath: string;
  successTitle: string;
  body?: string;
  headers: Record<string, string>;
};

export type SubmissionFeedback<TPayload> = {
  kind: 'idle' | 'pending' | 'success' | 'error';
  title?: string;
  message?: string;
  details?: string[];
  payload?: TPayload;
  route?: string;
  statusCode?: number;
};

export type RunTriggerField =
  | 'orgId'
  | 'actorId'
  | 'workflowKey'
  | 'inputParamsText'
  | 'metadataText'
  | 'idempotencyKey';

export type ReelTriggerField =
  | 'orgId'
  | 'pageId'
  | 'reelId'
  | 'actorId'
  | 'inputParamsText'
  | 'metadataText'
  | 'idempotencyKey';

export type ReelReviewField = 'orgId' | 'pageId' | 'reelId' | 'actorId';

export type MarkPostedField = 'orgId' | 'pageId' | 'reelId' | 'actorId' | 'manualConfirmation';

export type RunTriggerFormValues = {
  orgId: string;
  actorId: string;
  workflowKey: WorkflowKey;
  inputParamsText: string;
  metadataText: string;
  idempotencyKey: string;
};

export type ReelTriggerFormValues = {
  orgId: string;
  pageId: string;
  reelId: string;
  actorId: string;
  inputParamsText: string;
  metadataText: string;
  idempotencyKey: string;
};

export type ReelReviewFormValues = {
  orgId: string;
  pageId: string;
  reelId: string;
  actorId: string;
};

export type MarkPostedFormValues = ReelReviewFormValues & {
  manualConfirmation: boolean;
};

export type ReviewActionName = 'approve' | 'archive';

type FetchLike = typeof fetch;

const WORKFLOW_KEYS: WorkflowKey[] = ['daily_reel_factory', 'process_reel'];

function normalizeRequiredText(value: string, label: string): string | null {
  const normalized = value.trim();
  if (!normalized) {
    return `${label} is required.`;
  }
  return normalized;
}

function normalizeOptionalText(value: string): string | undefined {
  const normalized = value.trim();
  return normalized ? normalized : undefined;
}

function readUuidField<TField extends string>(
  value: string,
  label: string,
  field: TField,
  fieldErrors: FieldErrors<TField>,
): string | null {
  const normalized = normalizeRequiredText(value, label);
  if (!normalized) {
    fieldErrors[field] = `${label} is required.`;
    return null;
  }
  if (!UUID_PATTERN.test(normalized)) {
    fieldErrors[field] = `${label} must be a valid UUID.`;
    return null;
  }
  return normalized;
}

function readActorField<TField extends string>(
  value: string,
  field: TField,
  fieldErrors: FieldErrors<TField>,
): string | null {
  const normalized = normalizeRequiredText(value, 'Operator actor ID');
  if (!normalized) {
    fieldErrors[field] = 'Operator actor ID is required for audited actions.';
    return null;
  }
  return normalized;
}

function parseJsonObject<TField extends string>(
  value: string,
  label: string,
  field: TField,
  fieldErrors: FieldErrors<TField>,
): JsonObject | null {
  const normalized = value.trim();
  if (!normalized) {
    return {};
  }
  try {
    const parsed: unknown = JSON.parse(normalized);
    if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') {
      fieldErrors[field] = `${label} must be a JSON object.`;
      return null;
    }
    return parsed as JsonObject;
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Invalid JSON';
    fieldErrors[field] = `${label} must be valid JSON. ${message}`;
    return null;
  }
}

function workflowKeyIsValid(value: string): value is WorkflowKey {
  return WORKFLOW_KEYS.includes(value as WorkflowKey);
}

function withValidationSummary<TField extends string>(fieldErrors: FieldErrors<TField>): string[] {
  return Object.values(fieldErrors).filter((value): value is string => Boolean(value));
}

export function createRunTriggerSubmission(
  form: RunTriggerFormValues,
): ValidationResult<SubmissionDefinition, RunTriggerField> {
  const fieldErrors: FieldErrors<RunTriggerField> = {};
  const orgId = readUuidField(form.orgId, 'Org ID', 'orgId', fieldErrors);
  const actorId = readActorField(form.actorId, 'actorId', fieldErrors);
  const inputParams = parseJsonObject(
    form.inputParamsText,
    'Run input params',
    'inputParamsText',
    fieldErrors,
  );
  const metadata = parseJsonObject(form.metadataText, 'Run metadata', 'metadataText', fieldErrors);
  const idempotencyKey = normalizeOptionalText(form.idempotencyKey);

  if (!workflowKeyIsValid(form.workflowKey)) {
    fieldErrors.workflowKey = 'Workflow key must be one of the supported operator workflows.';
  }

  if (Object.keys(fieldErrors).length > 0 || !orgId || !actorId || !inputParams || !metadata) {
    return {
      ok: false,
      fieldErrors,
      summary: withValidationSummary(fieldErrors),
    };
  }

  const body: RunCreateRequest = {
    workflow_key: form.workflowKey,
    input_params: inputParams,
    metadata,
  };

  if (idempotencyKey) {
    body.idempotency_key = idempotencyKey;
  }

  return {
    ok: true,
    value: {
      actionLabel: 'Trigger Run',
      actionPath: `/orgs/${orgId}/runs`,
      successTitle: 'Run trigger accepted',
      body: JSON.stringify(body),
      headers: {
        'Content-Type': 'application/json',
        'X-Actor-Id': actorId,
      },
    },
  };
}

export function createReelTriggerSubmission(
  form: ReelTriggerFormValues,
): ValidationResult<SubmissionDefinition, ReelTriggerField> {
  const fieldErrors: FieldErrors<ReelTriggerField> = {};
  const orgId = readUuidField(form.orgId, 'Org ID', 'orgId', fieldErrors);
  const pageId = readUuidField(form.pageId, 'Page ID', 'pageId', fieldErrors);
  const reelId = readUuidField(form.reelId, 'Reel ID', 'reelId', fieldErrors);
  const actorId = readActorField(form.actorId, 'actorId', fieldErrors);
  const inputParams = parseJsonObject(
    form.inputParamsText,
    'Reel trigger input params',
    'inputParamsText',
    fieldErrors,
  );
  const metadata = parseJsonObject(
    form.metadataText,
    'Reel trigger metadata',
    'metadataText',
    fieldErrors,
  );
  const idempotencyKey = normalizeOptionalText(form.idempotencyKey);

  if (inputParams) {
    const reservedKeys = Object.keys(inputParams).filter((key) =>
      RESERVED_REEL_TRIGGER_KEYS.has(key),
    );
    if (reservedKeys.length > 0) {
      fieldErrors.inputParamsText = `Reel trigger input params cannot include reserved keys: ${reservedKeys.join(', ')}.`;
    }
  }

  if (
    Object.keys(fieldErrors).length > 0 ||
    !orgId ||
    !pageId ||
    !reelId ||
    !actorId ||
    !inputParams ||
    !metadata
  ) {
    return {
      ok: false,
      fieldErrors,
      summary: withValidationSummary(fieldErrors),
    };
  }

  const body: ReelTriggerRequest = {
    input_params: inputParams,
    metadata,
  };

  if (idempotencyKey) {
    body.idempotency_key = idempotencyKey;
  }

  return {
    ok: true,
    value: {
      actionLabel: 'Trigger Reel',
      actionPath: `/orgs/${orgId}/pages/${pageId}/reels/${reelId}/trigger`,
      successTitle: 'Reel trigger accepted',
      body: JSON.stringify(body),
      headers: {
        'Content-Type': 'application/json',
        'X-Actor-Id': actorId,
      },
    },
  };
}

export function createReelReviewSubmission(
  form: ReelReviewFormValues,
  action: ReviewActionName,
): ValidationResult<SubmissionDefinition, ReelReviewField> {
  const fieldErrors: FieldErrors<ReelReviewField> = {};
  const orgId = readUuidField(form.orgId, 'Org ID', 'orgId', fieldErrors);
  const pageId = readUuidField(form.pageId, 'Page ID', 'pageId', fieldErrors);
  const reelId = readUuidField(form.reelId, 'Reel ID', 'reelId', fieldErrors);
  const actorId = readActorField(form.actorId, 'actorId', fieldErrors);

  if (Object.keys(fieldErrors).length > 0 || !orgId || !pageId || !reelId || !actorId) {
    return {
      ok: false,
      fieldErrors,
      summary: withValidationSummary(fieldErrors),
    };
  }

  const actionPath = `/orgs/${orgId}/pages/${pageId}/reels/${reelId}/${action}`;
  const actionLabel = action === 'approve' ? 'Approve Reel' : 'Archive Reel';
  const successTitle = action === 'approve' ? 'Reel approved' : 'Reel archived';

  return {
    ok: true,
    value: {
      actionLabel,
      actionPath,
      successTitle,
      headers: {
        'X-Actor-Id': actorId,
      },
    },
  };
}

export function createMarkPostedSubmission(
  form: MarkPostedFormValues,
): ValidationResult<SubmissionDefinition, MarkPostedField> {
  const fieldErrors: FieldErrors<MarkPostedField> = {};
  const orgId = readUuidField(form.orgId, 'Org ID', 'orgId', fieldErrors);
  const pageId = readUuidField(form.pageId, 'Page ID', 'pageId', fieldErrors);
  const reelId = readUuidField(form.reelId, 'Reel ID', 'reelId', fieldErrors);
  const actorId = readActorField(form.actorId, 'actorId', fieldErrors);

  if (!form.manualConfirmation) {
    fieldErrors.manualConfirmation =
      'Confirm that a human has already posted this reel before marking it posted.';
  }

  if (Object.keys(fieldErrors).length > 0 || !orgId || !pageId || !reelId || !actorId) {
    return {
      ok: false,
      fieldErrors,
      summary: withValidationSummary(fieldErrors),
    };
  }

  return {
    ok: true,
    value: {
      actionLabel: 'Mark Posted',
      actionPath: `/orgs/${orgId}/pages/${pageId}/reels/${reelId}/mark-posted`,
      successTitle: 'Human posting recorded',
      headers: {
        'X-Actor-Id': actorId,
      },
    },
  };
}

function isApiValidationIssue(value: unknown): value is ApiValidationIssue {
  return Boolean(value) && typeof value === 'object';
}

export function formatApiError(status: number, payload: unknown): string[] {
  const errorPayload = payload as ApiErrorResponse | string | null | undefined;
  const detail =
    errorPayload && typeof errorPayload === 'object' && 'detail' in errorPayload
      ? errorPayload.detail
      : errorPayload;

  if (typeof detail === 'string' && detail.trim()) {
    return [detail.trim()];
  }

  if (Array.isArray(detail) && detail.length > 0) {
    return detail.map((issue) => {
      if (!isApiValidationIssue(issue)) {
        return 'Request validation failed.';
      }
      const location = Array.isArray(issue.loc) ? issue.loc.join('.') : 'request';
      const message = issue.msg?.trim() || 'Validation failed.';
      return `${location}: ${message}`;
    });
  }

  if (detail && typeof detail === 'object') {
    return Object.entries(detail).map(([key, value]) => `${key}: ${String(value)}`);
  }

  if (typeof payload === 'string' && payload.trim()) {
    return [payload.trim()];
  }

  return [`Request failed with status ${status}.`];
}

async function readJsonResponse(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text.trim()) {
    return null;
  }
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return text;
  }
}

function normalizeApiBaseUrl(apiBaseUrl: string): string {
  return apiBaseUrl.trim().replace(/\/+$/, '') || DEFAULT_API_BASE_URL;
}

function buildSuccessMessage(payload: unknown): string | undefined {
  if (!payload || typeof payload !== 'object') {
    return undefined;
  }

  if ('status' in payload && typeof payload.status === 'string') {
    return `API status: ${payload.status}`;
  }

  if ('workflow_key' in payload && typeof payload.workflow_key === 'string') {
    return `Workflow: ${payload.workflow_key}`;
  }

  return undefined;
}

export async function submitOperatorRequest<TPayload extends ReelResponse | RunResponse>(
  apiBaseUrl: string,
  submission: SubmissionDefinition,
  fetchImpl: FetchLike = fetch,
): Promise<SubmissionFeedback<TPayload>> {
  const route = submission.actionPath;
  const url = `${normalizeApiBaseUrl(apiBaseUrl)}${route}`;

  try {
    const response = await fetchImpl(url, {
      method: 'POST',
      headers: submission.headers,
      body: submission.body,
    });
    const payload = await readJsonResponse(response);

    if (!response.ok) {
      return {
        kind: 'error',
        title: `${submission.actionLabel} failed`,
        message: `${response.status} ${response.statusText}`.trim(),
        details: formatApiError(response.status, payload),
        payload: payload as TPayload,
        route,
        statusCode: response.status,
      };
    }

    return {
      kind: 'success',
      title: submission.successTitle,
      message: buildSuccessMessage(payload),
      payload: payload as TPayload,
      route,
      statusCode: response.status,
    };
  } catch (error) {
    return {
      kind: 'error',
      title: `${submission.actionLabel} failed`,
      message: 'Network request failed before the API responded.',
      details: [error instanceof Error ? error.message : 'Unknown network error.'],
      route,
    };
  }
}
