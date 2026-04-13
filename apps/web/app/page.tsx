import Link from 'next/link';
import React from 'react';

import {
  DetailFrame,
  MetaGrid,
  SectionCard,
  StatusBadge,
} from './_components/detail-ui';
import {
  demoIds,
  formatShortId,
  getWorkspaceSummary,
  packagePath,
  pagePath,
  reelPath,
  runPath,
} from './_lib/content-lab-data';
import { OperatorConsole } from './operator-console';

export default async function HomePage() {
  const workspace = await getWorkspaceSummary(demoIds.orgId);

  if (workspace === null) {
    return <OperatorConsole />;
  }

  return (
    <>
      <DetailFrame
        eyebrow="Operator Workspace"
        title="Content Lab"
        subtitle="Demo org detail routes wired to the real page, reel, run, policy, and package contracts."
        actions={
          <div className="cl-hero-actions">
            <details className="cl-dropdown">
              <summary>
                Workspace links <span className="cl-chevron" aria-hidden />
              </summary>
              <div className="cl-dropdown-menu">
                <div className="cl-dropdown-hint">Demo org</div>
                <Link href={pagePath(demoIds.orgId, demoIds.pageId)} className="cl-dropdown-item">
                  Page detail
                  <div className="cl-dropdown-item-muted">Policy + recent reels</div>
                </Link>
                <Link
                  href={reelPath(demoIds.orgId, demoIds.pageId, demoIds.reelId)}
                  className="cl-dropdown-item"
                >
                  Reel detail
                  <div className="cl-dropdown-item-muted">Lifecycle + package</div>
                </Link>
                <Link href={runPath(demoIds.orgId, demoIds.runId)} className="cl-dropdown-item">
                  Run detail
                  <div className="cl-dropdown-item-muted">Tasks + payloads</div>
                </Link>
                <Link
                  href={packagePath(demoIds.orgId, demoIds.runId)}
                  className="cl-dropdown-item"
                >
                  Package detail
                  <div className="cl-dropdown-item-muted">Artifacts + downloads</div>
                </Link>
                <div className="cl-dropdown-divider" />
                <Link href="/ui-demo" className="cl-dropdown-item">
                  UI demo
                  <div className="cl-dropdown-item-muted">Review shell and table menus</div>
                </Link>
                <Link href="/#operator-actions" className="cl-dropdown-item">
                  Operator API actions
                </Link>
              </div>
            </details>
          </div>
        }
      >
        <SectionCard
          title="Workspace summary"
          description="The entry point stays org-scoped and only links into nested resources for the same organization."
        >
          <MetaGrid
            items={[
              { label: 'Org id', value: demoIds.orgId },
              { label: 'Pages', value: workspace.pages.length },
              { label: 'Runs', value: workspace.runs.length },
              { label: 'Packages', value: workspace.packages.length },
            ]}
          />
        </SectionCard>

        <SectionCard
          title="Pages"
          description="Owned and competitor pages remain visible through the same operator shell."
        >
          <div style={{ display: 'grid', gap: 14 }}>
            {workspace.pages.map((page) => (
              <article
                key={page.id}
                style={{
                  display: 'grid',
                  gap: 12,
                  padding: 18,
                  borderRadius: 18,
                  border: '1px solid rgba(23, 32, 51, 0.12)',
                  background: 'rgba(255, 255, 255, 0.75)',
                }}
              >
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    gap: 12,
                    flexWrap: 'wrap',
                  }}
                >
                  <div>
                    <div
                      style={{
                        fontSize: 12,
                        textTransform: 'uppercase',
                        letterSpacing: '0.12em',
                        color: '#6d7483',
                      }}
                    >
                      {page.platform}
                    </div>
                    <div
                      style={{
                        fontSize: 22,
                        fontFamily: 'Georgia, Cambria, "Times New Roman", Times, serif',
                      }}
                    >
                      {page.display_name}
                    </div>
                  </div>
                  <StatusBadge status={page.ownership} />
                </div>
                <div style={{ color: '#55627a' }}>{page.handle ?? 'No handle recorded'}</div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'center' }}>
                  <details className="cl-dropdown">
                    <summary>
                      Page menu <span className="cl-chevron" aria-hidden />
                    </summary>
                    <div className="cl-dropdown-menu">
                      <Link href={pagePath(page.org_id, page.id)} className="cl-dropdown-item">
                        Inspect page
                        <div className="cl-dropdown-item-muted">{formatShortId(page.id)}</div>
                      </Link>
                      <Link href="/pages" className="cl-dropdown-item">
                        All pages route
                      </Link>
                    </div>
                  </details>
                </div>
              </article>
            ))}
          </div>
        </SectionCard>

        <SectionCard
          title="Operational runs"
          description="Run detail pages expose task status counts, orchestration metadata, and package links."
        >
          <div style={{ display: 'grid', gap: 14 }}>
            {workspace.runs.map((run) => (
              <article
                key={run.id}
                style={{
                  display: 'grid',
                  gap: 12,
                  padding: 18,
                  borderRadius: 18,
                  border: '1px solid rgba(23, 32, 51, 0.12)',
                  background: 'rgba(255, 255, 255, 0.75)',
                }}
              >
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    gap: 12,
                    flexWrap: 'wrap',
                  }}
                >
                  <div>
                    <div
                      style={{
                        fontSize: 12,
                        textTransform: 'uppercase',
                        letterSpacing: '0.12em',
                        color: '#6d7483',
                      }}
                    >
                      {run.flow_trigger}
                    </div>
                    <div
                      style={{
                        fontSize: 20,
                        fontFamily: 'Georgia, Cambria, "Times New Roman", Times, serif',
                      }}
                    >
                      {run.workflow_key}
                    </div>
                  </div>
                  <StatusBadge status={run.status} />
                </div>
                <div style={{ color: '#55627a' }}>
                  {Object.entries(run.task_status_counts)
                    .map(([status, count]) => `${status}: ${count}`)
                    .join(', ')}
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'center' }}>
                  <details className="cl-dropdown">
                    <summary>
                      Run menu <span className="cl-chevron" aria-hidden />
                    </summary>
                    <div className="cl-dropdown-menu">
                      <Link href={runPath(run.org_id, run.id)} className="cl-dropdown-item">
                        Open run detail
                        <div className="cl-dropdown-item-muted">{formatShortId(run.id)}</div>
                      </Link>
                      {workspace.packages.some((currentPackage) => currentPackage.run_id === run.id) ? (
                        <Link
                          href={packagePath(run.org_id, run.id)}
                          className="cl-dropdown-item"
                        >
                          Open package detail
                          <div className="cl-dropdown-item-muted">Same run id</div>
                        </Link>
                      ) : (
                        <span className="cl-dropdown-item" style={{ cursor: 'default' }}>
                          No package for this run
                          <div className="cl-dropdown-item-muted">Link appears when present</div>
                        </span>
                      )}
                      <Link href="/runs" className="cl-dropdown-item">
                        Runs list route
                      </Link>
                    </div>
                  </details>
                </div>
              </article>
            ))}
          </div>
        </SectionCard>
      </DetailFrame>

      <OperatorConsole />
    </>
  );
}
