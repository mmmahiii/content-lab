import Link from 'next/link';
import React from 'react';

import { LinkAction } from './detail-ui';
import { packagePath, reelPath } from '../_lib/operator-routes';
import type { QaFailureClass, QaFailureFilter } from '../_lib/qa-failure-triage';
import { QaFailureClassBadge, QaFailureGatesSummary } from './qa-failure-badge';

export type QaWorkbenchRow = {
  id: string;
  pageId: string;
  pageName: string;
  variantLabel: string;
  qaFailureClass: QaFailureClass;
  qaFailureGates: string[];
  qaFailureNextAction: string | null;
  lastRunId: string | null;
};

function filterHref(basePath: string, filter: QaFailureFilter): string {
  if (filter === 'all') {
    return basePath;
  }

  return `${basePath}?qaFailure=${filter}`;
}

function FilterChip({
  basePath,
  filter,
  label,
  active,
}: {
  basePath: string;
  filter: QaFailureFilter;
  label: string;
  active: boolean;
}): React.ReactElement {
  const href = filterHref(basePath, filter);
  const className = active ? 'cl-link-button is-primary' : 'cl-link-button is-secondary';

  return (
    <Link href={href} className={className}>
      {label}
    </Link>
  );
}

export function QaFailedWorkbench({
  orgId,
  basePath,
  activeFilter,
  rows,
}: {
  orgId: string | null;
  basePath: string;
  activeFilter: QaFailureFilter;
  rows: QaWorkbenchRow[];
}): React.ReactElement {
  const summaryCounts = rows.reduce(
    (acc, row) => {
      acc[row.qaFailureClass] += 1;
      acc.all += 1;
      return acc;
    },
    { all: 0, semantic: 0, technical: 0, unknown: 0 },
  );

  return (
    <div className="cl-workbench">
      <div className="cl-panel-description">
        <strong>Failure class</strong> separates copy and brief issues from packaging, manifest, and media problems.
        Use the filters to focus one backlog at a time ({summaryCounts.semantic} semantic, {summaryCounts.technical}{' '}
        technical, {summaryCounts.unknown} needs classification).
      </div>

      <div className="cl-button-row">
        <FilterChip basePath={basePath} filter="all" label="All blocked reels" active={activeFilter === 'all'} />
        <FilterChip basePath={basePath} filter="semantic" label="Semantic / content" active={activeFilter === 'semantic'} />
        <FilterChip
          basePath={basePath}
          filter="technical"
          label="Packaging / format"
          active={activeFilter === 'technical'}
        />
        <FilterChip
          basePath={basePath}
          filter="unknown"
          label="Needs classification"
          active={activeFilter === 'unknown'}
        />
      </div>

      <div className="cl-table-wrap">
        <table className="cl-table">
          <thead>
            <tr>
              <th>Reel</th>
              <th>Failure class</th>
              <th>Gates</th>
              <th>Operator next step</th>
              <th>Open</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const gates = row.qaFailureGates ?? [];

              return (
              <tr key={row.id}>
                <td>
                  <div className="cl-resource-title">
                    <strong>{row.variantLabel}</strong>
                    <span className="cl-resource-meta">{row.pageName}</span>
                  </div>
                </td>
                <td>
                  <div className="cl-inline-list">
                    <QaFailureClassBadge failureClass={row.qaFailureClass} />
                  </div>
                </td>
                <td>
                  {gates.length > 0 ? (
                    <QaFailureGatesSummary gates={gates} />
                  ) : (
                    <span className="cl-resource-meta">No gate labels recorded on this reel yet.</span>
                  )}
                </td>
                <td>
                  <span className="cl-resource-meta">{row.qaFailureNextAction ?? 'Inspect reel detail for the latest QA rollup.'}</span>
                </td>
                <td>
                  <div className="cl-button-row">
                    {orgId ? (
                      <LinkAction href={reelPath(orgId, row.pageId, row.id)} label="Reel detail" />
                    ) : null}
                    {orgId && row.lastRunId ? (
                      <LinkAction href={packagePath(orgId, row.lastRunId)} label="Package" tone="secondary" />
                    ) : null}
                  </div>
                </td>
              </tr>
            );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
