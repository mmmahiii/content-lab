import Link from 'next/link';
import React, { type ReactNode } from 'react';

import { PolicyEditor } from './policy-editor';
import { packagePath, pagePath, reelPath, runPath } from '../_lib/content-lab-data';
import type { PolicyEditorSnapshot } from '../_lib/operator-policy';
import type {
  CurrentRun,
  OperatorDashboardSnapshot,
  OwnedPage,
  RecentReel,
  ReviewQueueItem,
} from '../_lib/operator-dashboard';
import { buildPackageReviewQueue } from '../_lib/operator-dashboard';

type StatusTone = 'neutral' | 'success' | 'warning' | 'danger';

const pageStyle = {
  display: 'grid',
  gap: '20px',
} as const;

const heroStyle = {
  backgroundColor: '#ffffff',
  border: '1px solid #d9ddd4',
  borderRadius: '16px',
  padding: '20px',
} as const;

const heroMetaStyle = {
  color: '#4f5b65',
  display: 'flex',
  flexWrap: 'wrap',
  gap: '12px',
  marginTop: '14px',
} as const;

const metricGridStyle = {
  display: 'grid',
  gap: '12px',
  gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
} as const;

const metricCardStyle = {
  backgroundColor: '#ffffff',
  border: '1px solid #d9ddd4',
  borderRadius: '16px',
  padding: '16px',
} as const;

const panelStyle = {
  backgroundColor: '#ffffff',
  border: '1px solid #d9ddd4',
  borderRadius: '16px',
  padding: '18px',
} as const;

const sectionHeaderStyle = {
  alignItems: 'baseline',
  display: 'flex',
  flexWrap: 'wrap',
  gap: '10px',
  justifyContent: 'space-between',
  marginBottom: '14px',
} as const;

const tableStyle = {
  borderCollapse: 'collapse',
  width: '100%',
} as const;

const cellStyle = {
  borderTop: '1px solid #e7e9e2',
  fontSize: '0.95rem',
  padding: '12px 10px',
  textAlign: 'left',
  verticalAlign: 'top',
} as const;

const noteStyle = {
  color: '#4f5b65',
  fontSize: '0.92rem',
  margin: '12px 0 0',
} as const;

const emptyStateStyle = {
  backgroundColor: '#fbfbf9',
  border: '1px dashed #c4cbc0',
  borderRadius: '12px',
  color: '#3c4750',
  padding: '16px',
} as const;

function formatTimestamp(value: string): string {
  return new Intl.DateTimeFormat('en-GB', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value));
}

function toneForStatus(status: string): StatusTone {
  const normalized = status.toLowerCase();

  if (['ready', 'posted', 'succeeded', 'success', 'owned'].includes(normalized)) {
    return 'success';
  }

  if (['failed', 'archived', 'error'].includes(normalized)) {
    return 'danger';
  }

  if (['running', 'queued', 'pending', 'draft'].includes(normalized)) {
    return 'warning';
  }

  return 'neutral';
}

function toneForPackage(
  status: CurrentRun['packageStatus'] | RecentReel['packageStatus'],
): StatusTone {
  if (status === 'ready') {
    return 'success';
  }

  if (status === 'failed') {
    return 'danger';
  }

  if (status === 'pending') {
    return 'warning';
  }

  return 'neutral';
}

function formatStatusLabel(value: string): string {
  return value.replaceAll('_', ' ');
}

function formatQueueLabel(value: ReviewQueueItem['queueState']): string {
  return value === 'ready_for_review' ? 'ready for review' : formatStatusLabel(value);
}

function toneForQueueState(value: ReviewQueueItem['queueState']): StatusTone {
  if (value === 'ready_for_review') {
    return 'success';
  }

  if (value === 'qa_failed') {
    return 'danger';
  }

  return 'neutral';
}

function StatusBadge({ label, tone }: { label: string; tone: StatusTone }) {
  const colors: Record<StatusTone, { background: string; border: string; color: string }> = {
    neutral: { background: '#eef1ec', border: '#d5dbd1', color: '#34404a' },
    success: { background: '#e7f4e3', border: '#bbd9b7', color: '#204c25' },
    warning: { background: '#fff0d6', border: '#ebca8f', color: '#6d4a06' },
    danger: { background: '#fde4e1', border: '#edb7b0', color: '#7d2d23' },
  };

  return (
    <span
      style={{
        backgroundColor: colors[tone].background,
        border: `1px solid ${colors[tone].border}`,
        borderRadius: '999px',
        color: colors[tone].color,
        display: 'inline-flex',
        fontSize: '0.85rem',
        gap: '6px',
        padding: '4px 10px',
        textTransform: 'capitalize',
      }}
    >
      {label}
    </span>
  );
}

function ResourceMessage({ message, tone }: { message: string; tone: StatusTone }) {
  const borderColor =
    tone === 'danger'
      ? '#edb7b0'
      : tone === 'warning'
        ? '#ebca8f'
        : tone === 'success'
          ? '#bbd9b7'
          : '#c4cbc0';

  return (
    <div style={{ ...emptyStateStyle, borderColor }}>
      <p style={{ margin: 0 }}>{message}</p>
    </div>
  );
}

function SectionPanel({
  title,
  description,
  href,
  children,
  note,
}: {
  title: string;
  description: string;
  href: string;
  children: ReactNode;
  note?: string;
}) {
  return (
    <section style={panelStyle}>
      <div style={sectionHeaderStyle}>
        <div>
          <h2 style={{ margin: 0 }}>{title}</h2>
          <p style={{ color: '#4f5b65', margin: '6px 0 0' }}>{description}</p>
        </div>

        <div className="cl-section-actions">
          <details className="cl-dropdown">
            <summary>
              View <span className="cl-chevron" aria-hidden />
            </summary>
            <div className="cl-dropdown-menu">
              <div className="cl-dropdown-hint">This section</div>
              <Link href={href} className="cl-dropdown-item">
                Open focused route
                <div className="cl-dropdown-item-muted">Dedicated page for this dataset</div>
              </Link>
              <Link href="/ui-demo" className="cl-dropdown-item">
                UI demo
                <div className="cl-dropdown-item-muted">Layout reference for review</div>
              </Link>
            </div>
          </details>
        </div>
      </div>

      {children}
      {note ? <p style={noteStyle}>{note}</p> : null}
    </section>
  );
}

function RowActionsMenu({
  orgId,
  items,
}: {
  orgId: string | null;
  items: { href: string; label: string; hint?: string }[];
}) {
  if (!orgId) {
    return (
      <span
        style={{ color: '#9ca3af', fontSize: 13 }}
        title="Set CONTENT_LAB_OPERATOR_ORG_ID (or NEXT_PUBLIC_) to enable deep links"
      >
        —
      </span>
    );
  }

  if (items.length === 0) {
    return <span style={{ color: '#9ca3af', fontSize: 13 }}>—</span>;
  }

  return (
    <details className="cl-row-dropdown">
      <summary className="cl-actions-trigger" aria-label="Row actions">
        ⋯
      </summary>
      <div className="cl-dropdown-menu">
        <div className="cl-dropdown-hint">Open in console</div>
        {items.map((item) => (
          <Link key={item.href} href={item.href} className="cl-dropdown-item">
            {item.label}
            {item.hint ? <div className="cl-dropdown-item-muted">{item.hint}</div> : null}
          </Link>
        ))}
      </div>
    </details>
  );
}

function OverviewMetrics({ dashboard }: { dashboard: OperatorDashboardSnapshot }) {
  const metrics = [
    { label: 'Owned pages', value: dashboard.pages.data.length, state: dashboard.pages.state },
    { label: 'Current runs', value: dashboard.runs.data.length, state: dashboard.runs.state },
    { label: 'Recent reels', value: dashboard.reels.data.length, state: dashboard.reels.state },
  ];

  return (
    <section style={metricGridStyle}>
      {metrics.map((metric) => (
        <article key={metric.label} style={metricCardStyle}>
          <p style={{ color: '#4f5b65', margin: 0 }}>{metric.label}</p>
          <p style={{ fontSize: '1.8rem', margin: '8px 0 0' }}>{metric.value}</p>
          <p style={{ color: '#4f5b65', margin: '6px 0 0', textTransform: 'capitalize' }}>
            {metric.state.replace('_', ' ')}
          </p>
        </article>
      ))}
    </section>
  );
}

function PagesTable({ pages, orgId }: { pages: OwnedPage[]; orgId: string | null }) {
  return (
    <table style={tableStyle}>
      <thead>
        <tr>
          <th style={cellStyle}>Page</th>
          <th style={cellStyle}>Platform</th>
          <th style={cellStyle}>Ownership</th>
          <th style={cellStyle}>Updated</th>
          <th style={{ ...cellStyle, textAlign: 'right' }}>Actions</th>
        </tr>
      </thead>
      <tbody>
        {pages.map((page) => (
          <tr key={page.id}>
            <td style={cellStyle}>
              <strong>{page.displayName}</strong>
              <div style={{ color: '#4f5b65', marginTop: '4px' }}>
                {page.handle ?? 'Handle not set'}
              </div>
            </td>
            <td style={cellStyle}>{page.platform}</td>
            <td style={cellStyle}>
              <StatusBadge label={page.ownership} tone={toneForStatus(page.ownership)} />
            </td>
            <td style={cellStyle}>{formatTimestamp(page.updatedAt)}</td>
            <td style={{ ...cellStyle, textAlign: 'right' }}>
              <RowActionsMenu
                orgId={orgId}
                items={[
                  {
                    href: pagePath(orgId ?? '', page.id),
                    label: 'Page detail',
                    hint: 'Policy, reels, metadata',
                  },
                ]}
              />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function RunsTable({ runs, orgId }: { runs: CurrentRun[]; orgId: string | null }) {
  return (
    <table style={tableStyle}>
      <thead>
        <tr>
          <th style={cellStyle}>Run</th>
          <th style={cellStyle}>Status</th>
          <th style={cellStyle}>Package</th>
          <th style={cellStyle}>Activity</th>
          <th style={cellStyle}>Updated</th>
          <th style={{ ...cellStyle, textAlign: 'right' }}>Actions</th>
        </tr>
      </thead>
      <tbody>
        {runs.map((run) => (
          <tr key={run.id}>
            <td style={cellStyle}>
              <strong>{run.workflowKey}</strong>
              <div style={{ color: '#4f5b65', marginTop: '4px' }}>
                {run.pageName ?? 'Unknown page'} - {formatStatusLabel(run.flowTrigger)}
              </div>
              <div style={{ color: '#4f5b65', marginTop: '4px' }}>{run.externalRef ?? run.id}</div>
            </td>
            <td style={cellStyle}>
              <StatusBadge label={run.status} tone={toneForStatus(run.status)} />
            </td>
            <td style={cellStyle}>
              <StatusBadge
                label={`package ${formatStatusLabel(run.packageStatus)}`}
                tone={toneForPackage(run.packageStatus)}
              />
            </td>
            <td style={cellStyle}>
              <div>{run.taskSummary}</div>
              <div style={{ color: '#4f5b65', marginTop: '4px' }}>
                {run.currentStep ?? 'No active step'}
              </div>
            </td>
            <td style={cellStyle}>{formatTimestamp(run.updatedAt)}</td>
            <td style={{ ...cellStyle, textAlign: 'right' }}>
              <RowActionsMenu
                orgId={orgId}
                items={[
                  {
                    href: runPath(orgId ?? '', run.id),
                    label: 'Run detail',
                    hint: 'Tasks, payloads, lineage',
                  },
                  {
                    href: packagePath(orgId ?? '', run.id),
                    label: 'Package detail',
                    hint: 'Artifacts tied to this run',
                  },
                ]}
              />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function ReelsTable({ reels, orgId }: { reels: RecentReel[]; orgId: string | null }) {
  return (
    <table style={tableStyle}>
      <thead>
        <tr>
          <th style={cellStyle}>Reel</th>
          <th style={cellStyle}>Lifecycle</th>
          <th style={cellStyle}>Package</th>
          <th style={cellStyle}>Run</th>
          <th style={cellStyle}>Updated</th>
          <th style={{ ...cellStyle, textAlign: 'right' }}>Actions</th>
        </tr>
      </thead>
      <tbody>
        {reels.map((reel) => {
          const items: { href: string; label: string; hint?: string }[] = [
            {
              href: reelPath(orgId ?? '', reel.pageId, reel.id),
              label: 'Reel detail',
              hint: 'Lifecycle, assets, posting',
            },
          ];
          if (reel.lastRunId) {
            items.push({
              href: runPath(orgId ?? '', reel.lastRunId),
              label: 'Linked run',
              hint: 'Orchestration context',
            });
            items.push({
              href: packagePath(orgId ?? '', reel.lastRunId),
              label: 'Linked package',
              hint: 'Downloadable bundle',
            });
          }
          return (
            <tr key={reel.id}>
              <td style={cellStyle}>
                <strong>{reel.variantLabel}</strong>
                <div style={{ color: '#4f5b65', marginTop: '4px' }}>{reel.pageName}</div>
              </td>
              <td style={cellStyle}>
                <StatusBadge label={reel.status} tone={toneForStatus(reel.status)} />
                <div style={{ color: '#4f5b65', marginTop: '6px' }}>
                  {formatStatusLabel(reel.origin)}
                </div>
              </td>
              <td style={cellStyle}>
                <StatusBadge
                  label={`package ${formatStatusLabel(reel.packageStatus)}`}
                  tone={toneForPackage(reel.packageStatus)}
                />
                <div style={{ color: '#4f5b65', marginTop: '6px' }}>
                  {reel.packageMessage ?? 'No package message'}
                </div>
              </td>
              <td style={cellStyle}>
                <div>{reel.lastRunId ?? 'No run linked yet'}</div>
                <div style={{ color: '#4f5b65', marginTop: '6px' }}>
                  {reel.currentStep ?? 'No step reported'}
                </div>
              </td>
              <td style={cellStyle}>{formatTimestamp(reel.updatedAt)}</td>
              <td style={{ ...cellStyle, textAlign: 'right' }}>
                <RowActionsMenu orgId={orgId} items={items} />
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function QueueTable({ queue, orgId }: { queue: ReviewQueueItem[]; orgId: string | null }) {
  return (
    <table style={tableStyle}>
      <thead>
        <tr>
          <th style={cellStyle}>Reel</th>
          <th style={cellStyle}>Queue state</th>
          <th style={cellStyle}>Package</th>
          <th style={cellStyle}>Flow</th>
          <th style={cellStyle}>Updated</th>
          <th style={{ ...cellStyle, textAlign: 'right' }}>Actions</th>
        </tr>
      </thead>
      <tbody>
        {queue.map((item) => {
          const items: { href: string; label: string; hint?: string }[] = [
            {
              href: reelPath(orgId ?? '', item.pageId, item.id),
              label: 'Reel detail',
              hint: 'Review or posting context',
            },
          ];
          if (item.lastRunId) {
            items.push({
              href: runPath(orgId ?? '', item.lastRunId),
              label: 'Run detail',
              hint: 'Tasks and orchestration',
            });
            items.push({
              href: packagePath(orgId ?? '', item.lastRunId),
              label: 'Package detail',
              hint: 'Artifacts for this run',
            });
          }
          return (
            <tr key={item.id}>
              <td style={cellStyle}>
                <strong>{item.variantLabel}</strong>
                <div style={{ color: '#4f5b65', marginTop: '4px' }}>{item.pageName}</div>
              </td>
              <td style={cellStyle}>
                <StatusBadge
                  label={formatQueueLabel(item.queueState)}
                  tone={toneForQueueState(item.queueState)}
                />
                <div style={{ color: '#4f5b65', marginTop: '6px' }}>
                  Lifecycle: {formatStatusLabel(item.status)}
                </div>
              </td>
              <td style={cellStyle}>
                <StatusBadge
                  label={`package ${formatStatusLabel(item.packageStatus)}`}
                  tone={toneForPackage(item.packageStatus)}
                />
                <div style={{ color: '#4f5b65', marginTop: '6px' }}>
                  {item.packageMessage ?? 'No package message'}
                </div>
              </td>
              <td style={cellStyle}>
                <div>{item.currentStep ?? 'No step reported'}</div>
                <div style={{ color: '#4f5b65', marginTop: '6px' }}>
                  {item.lastRunId ?? 'No run linked yet'}
                </div>
              </td>
              <td style={cellStyle}>{formatTimestamp(item.updatedAt)}</td>
              <td style={{ ...cellStyle, textAlign: 'right' }}>
                <RowActionsMenu orgId={orgId} items={items} />
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function renderSectionState(
  state: OperatorDashboardSnapshot['pages']['state'],
  message: string | undefined,
) {
  if (!message) {
    return null;
  }

  if (state === 'error') {
    return <ResourceMessage message={message} tone="danger" />;
  }

  if (state === 'unconfigured') {
    return <ResourceMessage message={message} tone="warning" />;
  }

  return <ResourceMessage message={message} tone="neutral" />;
}

export function DashboardHomeView({ dashboard }: { dashboard: OperatorDashboardSnapshot }) {
  return (
    <main style={pageStyle}>
      <section style={heroStyle}>
        <p style={{ color: '#4f5b65', margin: 0 }}>
          Thin operator surface backed directly by the API.
        </p>
        <h2 style={{ fontSize: '2rem', margin: '10px 0 0' }}>
          Production visibility for pages, runs, reels, and packages
        </h2>
        <div style={heroMetaStyle}>
          <span>API: {dashboard.context.apiBaseUrl}</span>
          <span>Org: {dashboard.context.orgId ?? 'Not configured'}</span>
        </div>
        {dashboard.context.configurationMessage ? (
          <p style={{ ...noteStyle, marginTop: '12px' }}>
            {dashboard.context.configurationMessage}
          </p>
        ) : null}
      </section>

      <OverviewMetrics dashboard={dashboard} />

      <SectionPanel
        title="Owned pages"
        description="Registered production accounts the operator team is responsible for."
        href="/pages"
        note={dashboard.pages.state === 'ready' ? dashboard.pages.message : undefined}
      >
        {dashboard.pages.state === 'ready' ? (
          <PagesTable pages={dashboard.pages.data.slice(0, 5)} orgId={dashboard.context.orgId} />
        ) : (
          renderSectionState(dashboard.pages.state, dashboard.pages.message)
        )}
      </SectionPanel>

      <SectionPanel
        title="Current runs"
        description="Recent reel-linked workflow activity pulled from existing run detail endpoints."
        href="/runs"
        note={dashboard.runs.state === 'ready' ? dashboard.runs.message : undefined}
      >
        {dashboard.runs.state === 'ready' ? (
          <RunsTable runs={dashboard.runs.data} orgId={dashboard.context.orgId} />
        ) : (
          renderSectionState(dashboard.runs.state, dashboard.runs.message)
        )}
      </SectionPanel>

      <SectionPanel
        title="Recent reels"
        description="Latest reel lifecycle changes, including package-readiness signals."
        href="/reels"
        note={dashboard.reels.state === 'ready' ? dashboard.reels.message : undefined}
      >
        {dashboard.reels.state === 'ready' ? (
          <ReelsTable reels={dashboard.reels.data} orgId={dashboard.context.orgId} />
        ) : (
          renderSectionState(dashboard.reels.state, dashboard.reels.message)
        )}
      </SectionPanel>
    </main>
  );
}

export function PagesRouteView({ dashboard }: { dashboard: OperatorDashboardSnapshot }) {
  return (
    <main style={pageStyle}>
      <section style={heroStyle}>
        <p style={{ color: '#4f5b65', margin: 0 }}>Pages</p>
        <h2 style={{ margin: '10px 0 0' }}>Owned portfolio</h2>
        <p style={{ color: '#4f5b65', margin: '10px 0 0' }}>
          Operators use this view to confirm which production accounts are in scope.
        </p>
      </section>

      <SectionPanel
        title="Owned pages"
        description="Direct API view of the org page registry."
        href="/"
      >
        {dashboard.pages.state === 'ready' ? (
          <PagesTable pages={dashboard.pages.data} orgId={dashboard.context.orgId} />
        ) : (
          renderSectionState(dashboard.pages.state, dashboard.pages.message)
        )}
      </SectionPanel>
    </main>
  );
}

export function RunsRouteView({ dashboard }: { dashboard: OperatorDashboardSnapshot }) {
  return (
    <main style={pageStyle}>
      <section style={heroStyle}>
        <p style={{ color: '#4f5b65', margin: 0 }}>Runs</p>
        <h2 style={{ margin: '10px 0 0' }}>Workflow activity</h2>
        <p style={{ color: '#4f5b65', margin: '10px 0 0' }}>
          This route follows recent reel-linked runs and surfaces workflow and package state in one
          place.
        </p>
      </section>

      <SectionPanel
        title="Current runs"
        description="Run detail compiled from reel metadata and run endpoints."
        href="/"
      >
        {dashboard.runs.state === 'ready' ? (
          <RunsTable runs={dashboard.runs.data} orgId={dashboard.context.orgId} />
        ) : (
          renderSectionState(dashboard.runs.state, dashboard.runs.message)
        )}
      </SectionPanel>
    </main>
  );
}

export function ReelsRouteView({ dashboard }: { dashboard: OperatorDashboardSnapshot }) {
  return (
    <main style={pageStyle}>
      <section style={heroStyle}>
        <p style={{ color: '#4f5b65', margin: 0 }}>Reels</p>
        <h2 style={{ margin: '10px 0 0' }}>Recent content state</h2>
        <p style={{ color: '#4f5b65', margin: '10px 0 0' }}>
          Recent reel updates with operator-facing lifecycle and package readiness badges.
        </p>
      </section>

      <SectionPanel
        title="Recent reels"
        description="Latest reel activity across owned pages."
        href="/"
      >
        {dashboard.reels.state === 'ready' ? (
          <ReelsTable reels={dashboard.reels.data} orgId={dashboard.context.orgId} />
        ) : (
          renderSectionState(dashboard.reels.state, dashboard.reels.message)
        )}
      </SectionPanel>
    </main>
  );
}

export function PolicyRouteView({ snapshot }: { snapshot: PolicyEditorSnapshot }) {
  return (
    <main style={pageStyle}>
      <section style={heroStyle}>
        <p style={{ color: '#4f5b65', margin: 0 }}>Policy</p>
        <h2 style={{ margin: '10px 0 0' }}>Phase-1 guardrails editor</h2>
        <p style={{ color: '#4f5b65', margin: '10px 0 0' }}>
          Operators can inspect and patch only the allowed policy schema: mode ratios, budget
          guardrails, and QA or similarity thresholds.
        </p>
      </section>

      <SectionPanel
        title="Page policy editor"
        description="This editor stays inside the real page-policy PATCH contract and avoids adding speculative controls."
        href="/"
        note={snapshot.policies.state === 'ready' ? snapshot.policies.message : undefined}
      >
        {snapshot.policies.state === 'ready' && snapshot.context.orgId ? (
          <PolicyEditor
            apiBaseUrl={snapshot.context.apiBaseUrl}
            orgId={snapshot.context.orgId}
            records={snapshot.policies.data}
          />
        ) : (
          renderSectionState(snapshot.policies.state, snapshot.policies.message)
        )}
      </SectionPanel>
    </main>
  );
}

export function QueueRouteView({ dashboard }: { dashboard: OperatorDashboardSnapshot }) {
  const queue = buildPackageReviewQueue(dashboard);
  const readyCount =
    queue.state === 'ready'
      ? queue.data.filter((item) => item.queueState === 'ready_for_review').length
      : 0;
  const qaFailedCount =
    queue.state === 'ready'
      ? queue.data.filter((item) => item.queueState === 'qa_failed').length
      : 0;
  const postedCount =
    queue.state === 'ready' ? queue.data.filter((item) => item.queueState === 'posted').length : 0;

  return (
    <main style={pageStyle}>
      <section style={heroStyle}>
        <p style={{ color: '#4f5b65', margin: 0 }}>Queue</p>
        <h2 style={{ margin: '10px 0 0' }}>Package-ready working queue</h2>
        <p style={{ color: '#4f5b65', margin: '10px 0 0' }}>
          Generated reels stay visible in one operator queue as soon as they are ready for human
          review, blocked by QA, or already marked posted.
        </p>
        {queue.state === 'ready' ? (
          <div style={heroMetaStyle}>
            <span>Ready for review: {readyCount}</span>
            <span>QA failed: {qaFailedCount}</span>
            <span>Posted: {postedCount}</span>
          </div>
        ) : null}
      </section>

      <SectionPanel
        title="Review and posting queue"
        description="This view keeps phase-1 operator work centered on package readiness and explicit human outcomes."
        href="/"
        note={queue.state === 'ready' ? queue.message : undefined}
      >
        {queue.state === 'ready' ? (
          <QueueTable queue={queue.data} orgId={dashboard.context.orgId} />
        ) : (
          renderSectionState(queue.state, queue.message)
        )}
      </SectionPanel>
    </main>
  );
}
