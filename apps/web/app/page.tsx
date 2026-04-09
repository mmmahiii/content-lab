import React from 'react';

import {
  DetailFrame,
  LinkAction,
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
          <LinkAction href={pagePath(demoIds.orgId, demoIds.pageId)} label="Open page detail" />
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
                <div>
                  <LinkAction
                    href={pagePath(page.org_id, page.id)}
                    label={`Inspect page ${formatShortId(page.id)}`}
                  />
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
                <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                  <LinkAction
                    href={runPath(run.org_id, run.id)}
                    label={`Open run ${formatShortId(run.id)}`}
                  />
                  {workspace.packages.some((currentPackage) => currentPackage.run_id === run.id) ? (
                    <LinkAction
                      href={packagePath(run.org_id, run.id)}
                      label="Open package detail"
                    />
                  ) : null}
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
