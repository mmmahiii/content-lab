export const OPERATOR_ORG_COOKIE = 'content_lab_operator_org_id';

export type OperatorContextSource = 'cookie' | 'env' | 'unconfigured';

type ResolveOperatorOrgInput = {
  cookieOrgId?: string | null;
  envOrgId?: string | null;
};

export function normalizeOrgId(value: string | null | undefined): string | null {
  if (typeof value !== 'string') {
    return null;
  }

  const trimmed = value.trim();
  if (trimmed.length === 0) {
    return null;
  }

  const uuidPattern =
    /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

  return uuidPattern.test(trimmed) ? trimmed : null;
}

export function resolveOperatorOrgId({
  cookieOrgId,
  envOrgId,
}: ResolveOperatorOrgInput): { orgId: string | null; source: OperatorContextSource } {
  const normalizedCookie = normalizeOrgId(cookieOrgId);
  if (normalizedCookie) {
    return { orgId: normalizedCookie, source: 'cookie' };
  }

  const normalizedEnv = normalizeOrgId(envOrgId);
  if (normalizedEnv) {
    return { orgId: normalizedEnv, source: 'env' };
  }

  return { orgId: null, source: 'unconfigured' };
}

export function describeOperatorContextSource(source: OperatorContextSource): string {
  if (source === 'cookie') {
    return 'Saved from the console';
  }

  if (source === 'env') {
    return 'Loaded from environment';
  }

  return 'Not selected yet';
}
