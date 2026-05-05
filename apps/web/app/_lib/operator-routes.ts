export function pagePath(orgId: string, pageId: string): string {
  return `/orgs/${orgId}/pages/${pageId}`;
}

export function pageReelsPath(orgId: string, pageId: string): string {
  return `${pagePath(orgId, pageId)}/reels`;
}

export function pageRunsPath(orgId: string, pageId: string): string {
  return `${pagePath(orgId, pageId)}/runs`;
}

export function pagePolicyPath(orgId: string, pageId: string): string {
  return `${pagePath(orgId, pageId)}/policy`;
}

export function reelPath(orgId: string, pageId: string, reelId: string): string {
  return `${pageReelsPath(orgId, pageId)}/${reelId}`;
}

export function runPath(orgId: string, runId: string): string {
  return `/orgs/${orgId}/runs/${runId}`;
}

export function packagePath(orgId: string, runId: string): string {
  return `/orgs/${orgId}/packages/${runId}`;
}
