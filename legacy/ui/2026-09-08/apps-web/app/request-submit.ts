import type { ApiErrorResponse, ApiValidationIssue } from '@shared/types';

export const DEFAULT_API_BASE_URL = 'http://127.0.0.1:8000';

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
  method?: 'POST' | 'PATCH' | 'PUT' | 'DELETE';
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

type FetchLike = typeof fetch;

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

export async function submitApiRequest<TPayload>(
  apiBaseUrl: string,
  submission: SubmissionDefinition,
  fetchImpl: FetchLike = fetch,
): Promise<SubmissionFeedback<TPayload>> {
  const route = submission.actionPath;
  const url = `${normalizeApiBaseUrl(apiBaseUrl)}${route}`;

  try {
    const response = await fetchImpl(url, {
      method: submission.method ?? 'POST',
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
