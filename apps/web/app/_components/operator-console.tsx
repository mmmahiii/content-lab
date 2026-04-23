import React from 'react';
import type { ReactNode } from 'react';

import {
  DetailFrame,
  LinkAction,
  MetaGrid,
  SectionCard,
  StatusBadge,
  formatStatus,
  formatTimestamp,
} from './detail-ui';
import { PolicyEditor } from './policy-editor';
import {
  demoIds,
  packagePath,
  pagePath,
  pagePolicyPath,
  pageReelsPath,
  pageRunsPath,
  reelPath,
  runPath,
} from '../_lib/content-lab-data';
import { buildPackageReviewQueue } from '../_lib/operator-dashboard';
import type { PolicyEditorSnapshot } from '../_lib/operator-policy';
import type {
  CurrentRun,
  OperatorDashboardSnapshot,
  OwnedPage,
  RecentReel,
  ResourceState,
  ReviewQueueItem,
} from '../_lib/operator-dashboard';
import {
  normalizeQaFailureFilter,
  queueItemMatchesQaFailureFilter,
  reelMatchesQaFailureFilter,
  resolvedQaFailureClass,
} from '../_lib/qa-failure-triage';
import { QaFailedWorkbench, type QaWorkbenchRow } from './qa-failed-workbench';
import { QaFailureClassBadge, QaFailureGatesSummary } from './qa-failure-badge';

type StatusTone = 'neutral' | 'success' | 'warning' | 'danger';

type LinkItem = {
  href: string;
  label: string;
  tone?: 'default' | 'primary' | 'secondary';
};

function buildActionPath(values: Record<string, string | null | undefined>): string {
  const params = new URLSearchParams();

  Object.entries(values).forEach(([key, value]) => {
    if (typeof value === 'string' && value.length > 0) {
      params.set(key, value);
    }
  });

  const query = params.toString();
  return query.length > 0 ? `/actions?${query}` : '/actions';
}

function formatQueueLabel(value: ReviewQueueItem['queueState']): string {
  return value === 'ready_for_review' ? 'ready for review' : formatStatus(value);
}

function reviewQueueToWorkbenchRows(items: ReviewQueueItem[]): QaWorkbenchRow[] {
  return items
    .filter((item) => item.queueState === 'qa_failed')
    .map((item) => ({
      id: item.id,
      pageId: item.pageId,
      pageName: item.pageName,
      variantLabel: item.variantLabel,
      qaFailureClass: resolvedQaFailureClass(item.qaFailureClass),
      qaFailureGates: item.qaFailureGates,
      qaFailureNextAction: item.qaFailureNextAction,
      lastRunId: item.lastRunId,
    }));
}

function recentReelsToWorkbenchRows(reels: RecentReel[]): QaWorkbenchRow[] {
  const blocked = reels
    .filter((reel) => reel.origin === 'generated')
    .filter((reel) => reel.status === 'qa_failed' || reel.packageStatus === 'failed')
    .sort((left, right) => right.updatedAt.localeCompare(left.updatedAt));

  return blocked.map((reel) => ({
    id: reel.id,
    pageId: reel.pageId,
    pageName: reel.pageName,
    variantLabel: reel.variantLabel,
    qaFailureClass: resolvedQaFailureClass(reel.qaFailureClass),
    qaFailureGates: reel.qaFailureGates,
    qaFailureNextAction: reel.qaFailureNextAction,
    lastRunId: reel.lastRunId,
  }));
}

function toneForState(state: ResourceState): StatusTone {
  if (state === 'error') {
    return 'danger';
  }

  if (state === 'unconfigured') {
    return 'warning';
  }

  return 'neutral';
}

function EmptyState({
  title,
  message,
  tone = 'neutral',
  actions,
}: {
  title: string;
  message: string;
  tone?: StatusTone;
  actions?: ReactNode;
}) {
  const className =
    tone === 'danger' ? 'cl-empty is-danger' : tone === 'warning' ? 'cl-empty is-warning' : 'cl-empty';

  return (
    <div className={className}>
      <strong>{title}</strong>
      <p className="cl-panel-description">{message}</p>
      {actions ? <div className="cl-button-row">{actions}</div> : null}
    </div>
  );
}

function ActionCluster({ items }: { items: LinkItem[] }) {
  return (
    <div className="cl-button-row">
      {items.map((item) => (
        <LinkAction key={`${item.href}-${item.label}`} href={item.href} label={item.label} tone={item.tone} />
      ))}
    </div>
  );
}

function GlossaryPanel() {
  return (
    <div className="cl-glossary">
      <dl>
        <div>
          <dt>Page</dt>
          <dd>The social account Content Lab is planning and producing content for.</dd>
        </div>
        <div>
          <dt>Run</dt>
          <dd>A workflow execution that moves content from planning through packaging.</dd>
        </div>
        <div>
          <dt>Reel</dt>
          <dd>A piece of content being generated, reviewed, observed, or marked as posted.</dd>
        </div>
        <div>
          <dt>Package</dt>
          <dd>The ready-to-use output set: video, cover, captions, posting plan, and provenance.</dd>
        </div>
        <div>
          <dt>Queue</dt>
          <dd>The human working list for review-ready, QA-failed, and posted generated reels.</dd>
        </div>
        <div>
          <dt>Policy</dt>
          <dd>The allowed guardrails that shape budget, novelty, and quality thresholds for a page.</dd>
        </div>
      </dl>
    </div>
  );
}

function HomeSignalStrip({ dashboard }: { dashboard: OperatorDashboardSnapshot }) {
  const queue = buildPackageReviewQueue(dashboard);
  const reviewReadyCount =
    queue.state === 'ready'
      ? queue.data.filter((item) => item.queueState === 'ready_for_review').length
      : 'Not available';
  const qaFailedCount =
    queue.state === 'ready'
      ? queue.data.filter((item) => item.queueState === 'qa_failed').length
      : 'Not available';

  const items = [
    { label: 'Pages in scope', value: dashboard.pages.state === 'ready' ? dashboard.pages.data.length : 'Not connected' },
    { label: 'In-flight runs', value: dashboard.runs.state === 'ready' ? dashboard.runs.data.length : 'Not available' },
    { label: 'Needs review', value: reviewReadyCount },
    { label: 'QA failed', value: qaFailedCount },
  ];

  return (
    <div className="cl-stat-grid cl-home-signal-grid">
      {items.map((item) => (
        <article key={item.label} className="cl-stat-card">
          <div className="cl-meta-label">{item.label}</div>
          <div className="cl-stat-value">{item.value}</div>
        </article>
      ))}
    </div>
  );
}

function cueSummaryForRoute(copy: string): string {
  return copy;
}

function ResourceStateBlock({
  title,
  state,
  message,
  action,
}: {
  title: string;
  state: ResourceState;
  message: string | undefined;
  action?: ReactNode;
}) {
  return (
    <EmptyState
      title={title}
      message={message ?? 'This data is not available yet.'}
      tone={toneForState(state)}
      actions={action}
    />
  );
}

function PagesTable({ pages, orgId }: { pages: OwnedPage[]; orgId: string | null }) {
  return (
    <div className="cl-table-wrap">
      <table className="cl-table">
        <thead>
          <tr>
            <th>Page</th>
            <th>What it means</th>
            <th>Updated</th>
            <th>Next actions</th>
          </tr>
        </thead>
        <tbody>
          {pages.map((page) => (
            <tr key={page.id}>
              <td>
                <div className="cl-resource-title">
                  <strong>{page.displayName}</strong>
                  <span className="cl-resource-meta">{page.handle ?? 'Handle not set'}</span>
                </div>
              </td>
              <td>
                <div className="cl-inline-list">
                  <StatusBadge status={page.ownership} />
                  <span className="cl-resource-meta">
                    {page.ownership === 'owned'
                      ? 'This page is in your production scope.'
                      : 'This page is visible for competitor context.'}
                  </span>
                </div>
              </td>
              <td>{formatTimestamp(page.updatedAt)}</td>
              <td>
                <ActionCluster
                  items={[
                    { href: pagePath(orgId ?? demoIds.orgId, page.id), label: 'Overview' },
                    { href: pageReelsPath(orgId ?? demoIds.orgId, page.id), label: 'Reels' },
                    { href: pageRunsPath(orgId ?? demoIds.orgId, page.id), label: 'Runs' },
                    { href: pagePolicyPath(orgId ?? demoIds.orgId, page.id), label: 'Policy' },
                    {
                      href: buildActionPath({ orgId: orgId ?? demoIds.orgId, pageId: page.id }),
                      label: 'Actions',
                      tone: 'secondary',
                    },
                  ]}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RunsTable({ runs, orgId }: { runs: CurrentRun[]; orgId: string | null }) {
  return (
    <div className="cl-table-wrap">
      <table className="cl-table">
        <thead>
          <tr>
            <th>Run</th>
            <th>Status</th>
            <th>What is happening</th>
            <th>Updated</th>
            <th>Next actions</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => (
            <tr key={run.id}>
              <td>
                <div className="cl-resource-title">
                  <strong>{run.workflowKey}</strong>
                  <span className="cl-resource-meta">{run.externalRef ?? run.id}</span>
                </div>
              </td>
              <td>
                <div className="cl-inline-list">
                  <StatusBadge status={run.status} />
                  <StatusBadge status={`package ${run.packageStatus}`} />
                </div>
              </td>
              <td>
                <div className="cl-resource-title">
                  <strong>{run.currentStep ?? 'Waiting for the next reported step'}</strong>
                  <span className="cl-resource-meta">
                    {run.pageName ?? 'Unknown page'} - {formatStatus(run.flowTrigger)} -{' '}
                    {run.taskSummary}
                  </span>
                  {run.outboxSummary ? (
                    <span className="cl-resource-meta">
                      {run.outboxBacklog ? 'Outbox backlog: ' : 'Outbox: '}
                      {run.outboxSummary}
                    </span>
                  ) : null}
                </div>
              </td>
              <td>{formatTimestamp(run.updatedAt)}</td>
              <td>
                <ActionCluster
                  items={[
                    { href: runPath(orgId ?? demoIds.orgId, run.id), label: 'Open run detail' },
                    { href: packagePath(orgId ?? demoIds.orgId, run.id), label: 'Open package' },
                    run.reelId
                      ? {
                          href: buildActionPath({ orgId: orgId ?? demoIds.orgId, reelId: run.reelId }),
                          label: 'Open in Actions',
                          tone: 'secondary',
                        }
                      : { href: '/actions', label: 'Open in Actions', tone: 'secondary' },
                  ]}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ReelsTable({ reels, orgId }: { reels: RecentReel[]; orgId: string | null }) {
  return (
    <div className="cl-table-wrap">
      <table className="cl-table">
        <thead>
          <tr>
            <th>Reel</th>
            <th>Lifecycle</th>
            <th>Package readiness</th>
            <th>Linked run</th>
            <th>Next actions</th>
          </tr>
        </thead>
        <tbody>
          {reels.map((reel) => (
            <tr key={reel.id}>
              <td>
                <div className="cl-resource-title">
                  <strong>{reel.variantLabel}</strong>
                  <span className="cl-resource-meta">{reel.pageName}</span>
                </div>
              </td>
              <td>
                <div className="cl-inline-list">
                  <StatusBadge status={reel.status} />
                  <span className="cl-resource-meta">{formatStatus(reel.origin)}</span>
                </div>
                {reel.status === 'qa_failed' || reel.packageStatus === 'failed' ? (
                  <div className="cl-resource-title">
                    {reel.qaFailureClass ? (
                      <div className="cl-inline-list">
                        <QaFailureClassBadge failureClass={reel.qaFailureClass} />
                      </div>
                    ) : null}
                    <QaFailureGatesSummary gates={reel.qaFailureGates} />
                    {reel.qaFailureNextAction ? (
                      <span className="cl-resource-meta">{reel.qaFailureNextAction}</span>
                    ) : null}
                  </div>
                ) : null}
              </td>
              <td>
                <div className="cl-resource-title">
                  <strong>{formatStatus(reel.packageStatus)}</strong>
                  <span className="cl-resource-meta">{reel.packageMessage ?? 'No package message yet.'}</span>
                </div>
              </td>
              <td>
                <div className="cl-resource-title">
                  <strong>{reel.lastRunId ?? 'No linked run yet'}</strong>
                  <span className="cl-resource-meta">{reel.currentStep ?? 'No current step reported'}</span>
                </div>
              </td>
              <td>
                <ActionCluster
                  items={[
                    { href: reelPath(orgId ?? demoIds.orgId, reel.pageId, reel.id), label: 'Open reel detail' },
                    reel.lastRunId
                      ? { href: packagePath(orgId ?? demoIds.orgId, reel.lastRunId), label: 'Open package' }
                      : { href: '/queue', label: 'Open queue' },
                    {
                      href: buildActionPath({
                        orgId: orgId ?? demoIds.orgId,
                        pageId: reel.pageId,
                        reelId: reel.id,
                      }),
                      label: 'Open in Actions',
                      tone: 'secondary',
                    },
                  ]}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function QueueTable({ queue, orgId }: { queue: ReviewQueueItem[]; orgId: string | null }) {
  return (
    <div className="cl-table-wrap">
      <table className="cl-table">
        <thead>
          <tr>
            <th>Queue item</th>
            <th>Why it is here</th>
            <th>Package state</th>
            <th>Linked workflow</th>
            <th>Next actions</th>
          </tr>
        </thead>
        <tbody>
          {queue.map((item) => (
            <tr key={item.id}>
              <td>
                <div className="cl-resource-title">
                  <strong>{item.variantLabel}</strong>
                  <span className="cl-resource-meta">{item.pageName}</span>
                </div>
              </td>
              <td>
                <div className="cl-resource-title">
                  <strong>{formatQueueLabel(item.queueState)}</strong>
                  <span className="cl-resource-meta">Lifecycle state: {formatStatus(item.status)}</span>
                </div>
                {item.queueState === 'qa_failed' ? (
                  <div className="cl-resource-title">
                    {item.qaFailureClass ? (
                      <div className="cl-inline-list">
                        <QaFailureClassBadge failureClass={item.qaFailureClass} />
                      </div>
                    ) : null}
                    <QaFailureGatesSummary gates={item.qaFailureGates} />
                    {item.qaFailureNextAction ? (
                      <span className="cl-resource-meta">{item.qaFailureNextAction}</span>
                    ) : null}
                  </div>
                ) : null}
              </td>
              <td>
                <div className="cl-resource-title">
                  <strong>{formatStatus(item.packageStatus)}</strong>
                  <span className="cl-resource-meta">{item.packageMessage ?? 'No package message yet.'}</span>
                </div>
              </td>
              <td>
                <div className="cl-resource-title">
                  <strong>{item.lastRunId ?? 'No linked run yet'}</strong>
                  <span className="cl-resource-meta">{item.currentStep ?? 'No current step reported'}</span>
                </div>
              </td>
              <td>
                <ActionCluster
                  items={[
                    { href: reelPath(orgId ?? demoIds.orgId, item.pageId, item.id), label: 'Open reel detail' },
                    {
                      href: buildActionPath({
                        orgId: orgId ?? demoIds.orgId,
                        pageId: item.pageId,
                        reelId: item.id,
                      }),
                      label: 'Review in Actions',
                      tone: 'primary',
                    },
                    item.lastRunId
                      ? { href: packagePath(orgId ?? demoIds.orgId, item.lastRunId), label: 'Open package' }
                      : { href: '/actions', label: 'Open actions' },
                  ]}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function HomeWorkflowPanel({ dashboard }: { dashboard: OperatorDashboardSnapshot }) {
  const configured = dashboard.context.orgId !== null;
  const firstPageId =
    dashboard.pages.state === 'ready' && dashboard.pages.data[0] ? dashboard.pages.data[0].id : demoIds.pageId;
  const pageWorkspaceHref = pagePath(dashboard.context.orgId ?? demoIds.orgId, firstPageId);
  const steps = [
    {
      title: 'Choose a page',
      description: 'Start in Pages, confirm the account in scope, and keep the rest of the work tied to that page.',
      actions: <LinkAction href="/pages" label="Open Pages" />,
    },
    {
      title: 'Stay in the page workspace',
      description: 'Use the overview, reels, runs, and policy tabs so context stays inside one account.',
      actions: <LinkAction href={pageWorkspaceHref} label="Open page workspace" tone="secondary" />,
    },
    {
      title: 'Start or review work',
      description: 'Use Actions to trigger or record a human step, and Queue when review work spans multiple pages.',
      actions: (
        <ActionCluster
          items={[
            { href: '/actions', label: 'Open Actions' },
            { href: '/queue', label: 'Open Queue', tone: 'secondary' },
          ]}
        />
      ),
    },
    {
      title: 'Inspect the package and finish',
      description: 'Check the package output, then record manual posting after the human publish step is complete.',
      actions: (
        <ActionCluster
          items={[
            { href: packagePath(demoIds.orgId, demoIds.runId), label: 'Open sample package' },
            {
              href: buildActionPath({ orgId: demoIds.orgId, pageId: demoIds.pageId, reelId: demoIds.reelId }),
              label: 'Record posting',
              tone: 'secondary',
            },
          ]}
        />
      ),
    },
  ];

  return (
    <div className="cl-home-layout">
      {!configured ? (
        <EmptyState
          title="Connect your workspace"
          message={
            dashboard.context.configurationMessage ??
            'Choose a workspace org in the sidebar to load live pages, runs, reels, and queue counts.'
          }
          tone="warning"
          actions={
            <>
              <LinkAction href={pageWorkspaceHref} label="Open sample page" />
              <LinkAction href="/actions" label="Open Actions anyway" tone="secondary" />
            </>
          }
        />
      ) : null}
      <div className="cl-home-flow">
        <div className="cl-home-flow-head">
          <div>
            <div className="cl-kicker">Workflow map</div>
            <h2 className="cl-panel-title">One clear path through the operator workspace</h2>
            <p className="cl-panel-description">
              Pages is the main entry point. Stay page-scoped until the work crosses into shared review or audited manual actions.
            </p>
          </div>
          <p className="cl-home-flow-note">
            Use the reference panel below when you need glossary help. The homepage keeps only the workflow path and live signal.
          </p>
        </div>
        <HomeSignalStrip dashboard={dashboard} />
        <ol className="cl-flow-list cl-home-flow-list">
          {steps.map((step, index) => (
            <li key={step.title} className="cl-flow-item cl-home-flow-item">
              <span className="cl-flow-step">{index + 1}</span>
              <div className="cl-flow-copy">
                <strong>{step.title}</strong>
                <span>{step.description}</span>
                <div className="cl-button-row cl-home-step-actions">{step.actions}</div>
              </div>
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}

export function HomeRouteView({ dashboard }: { dashboard: OperatorDashboardSnapshot }) {
  return (
    <DetailFrame
      className="cl-page-home"
      breadcrumbs={[{ label: 'Home' }]}
      eyebrow="Home"
      title="Content Lab operator home"
      subtitle="A compact landing page for daily operations: one workflow map, live queue signal, and direct entry points into Pages, Queue, Actions, and a sample page."
      actions={
        <ActionCluster
          items={[
            { href: '/pages', label: 'Open Pages', tone: 'primary' },
            { href: '/actions', label: 'Open Actions' },
            { href: '/queue', label: 'Go to Queue' },
            { href: pagePath(demoIds.orgId, demoIds.pageId), label: 'Open sample page', tone: 'secondary' },
          ]}
        />
      }
    >
      <SectionCard
        title="Workflow map"
        description="One concise path for daily work, with live signal kept in the same panel so the homepage stays useful without repeating itself."
      >
        <HomeWorkflowPanel dashboard={dashboard} />
      </SectionCard>

      <details className="cl-panel cl-disclosure-panel">
        <summary className="cl-disclosure-summary">
          <span>
            <span className="cl-kicker">Reference</span>
            <strong className="cl-disclosure-title">Glossary and orientation</strong>
          </span>
          <span className="cl-disclosure-hint">Show</span>
        </summary>
        <GlossaryPanel />
      </details>
    </DetailFrame>
  );
}

export function DashboardHomeView({ dashboard }: { dashboard: OperatorDashboardSnapshot }) {
  return <HomeRouteView dashboard={dashboard} />;
}

export function PagesRouteView({ dashboard }: { dashboard: OperatorDashboardSnapshot }) {
  return (
    <DetailFrame
      breadcrumbs={[{ label: 'Home', href: '/' }, { label: 'Pages' }]}
      eyebrow="Pages"
      title="Your production page directory"
      subtitle="Start here whenever you need to choose the right account, then move into that page’s overview, reels, runs, policy, or actions."
      cuesSummary={cueSummaryForRoute('Every row now opens a page-first workspace, so the next step is always scoped to the account you selected.')}
      actions={<ActionCluster items={[{ href: '/actions', label: 'Open Actions', tone: 'primary' }]} />}
      cues={[
        {
          label: 'What this page is for',
          value: 'See which social accounts you are responsible for and which ones are just reference accounts.',
        },
        {
          label: 'What you can do here',
          value: 'Open the page workspace tabs directly, or jump into Actions with the right page context already filled in.',
        },
        {
          label: 'What comes next',
          value: 'After choosing a page, stay inside that page workspace for reels, runs, and policy before leaving to Queue or Actions.',
        },
      ]}
    >
      <SectionCard
        title="Pages in scope"
        description="Each row tells you what the page is, why it matters, and where to go next."
        note={dashboard.pages.state === 'ready' ? dashboard.pages.message : undefined}
      >
        {dashboard.pages.state === 'ready' ? (
          <PagesTable pages={dashboard.pages.data} orgId={dashboard.context.orgId} />
        ) : (
          <ResourceStateBlock
            title="Pages are not available yet"
            state={dashboard.pages.state}
            message={dashboard.pages.message}
            action={<LinkAction href="/" label="Back to Home" />}
          />
        )}
      </SectionCard>
    </DetailFrame>
  );
}

export function RunsRouteView({ dashboard }: { dashboard: OperatorDashboardSnapshot }) {
  return (
    <DetailFrame
      breadcrumbs={[{ label: 'Home', href: '/' }, { label: 'Runs' }]}
      eyebrow="Runs"
      title="Track workflow progress and blockers"
      subtitle="Use this route to check work that is already in motion: what started, what step it is on, and whether it is blocked or ready."
      cuesSummary={cueSummaryForRoute('Track in-flight work, open the linked package, and spot blockers without reading raw payloads first.')}
      actions={<ActionCluster items={[{ href: '/actions', label: 'Start a workflow', tone: 'primary' }]} />}
      cues={[
        {
          label: 'What this page is for',
          value: 'See workflow activity at a glance instead of reading raw task payloads first.',
        },
        {
          label: 'What you can do here',
          value: 'Spot blockers, open detailed run payloads, or jump into the linked package and actions workspace.',
        },
        {
          label: 'What comes next',
          value: 'If a run finishes, open the linked package or queue item to continue human review.',
        },
      ]}
    >
      <SectionCard
        title="Current run tracker"
        description="Each run summarizes progress, package state, and what the operator should inspect next."
        note={dashboard.runs.state === 'ready' ? dashboard.runs.message : undefined}
      >
        {dashboard.runs.state === 'ready' ? (
          <RunsTable runs={dashboard.runs.data} orgId={dashboard.context.orgId} />
        ) : (
          <ResourceStateBlock
            title="Runs are not available yet"
            state={dashboard.runs.state}
            message={dashboard.runs.message}
            action={<LinkAction href="/actions" label="Open Actions" />}
          />
        )}
      </SectionCard>
    </DetailFrame>
  );
}

export function ReelsRouteView({
  dashboard,
  qaFailureFilter,
}: {
  dashboard: OperatorDashboardSnapshot;
  qaFailureFilter?: string;
}) {
  const triageFilter = normalizeQaFailureFilter(qaFailureFilter);
  const reels =
    dashboard.reels.state === 'ready'
      ? dashboard.reels.data.filter((reel) => reelMatchesQaFailureFilter(reel, triageFilter))
      : [];

  const workbenchRows =
    dashboard.reels.state === 'ready' ? recentReelsToWorkbenchRows(dashboard.reels.data) : [];

  return (
    <DetailFrame
      breadcrumbs={[{ label: 'Home', href: '/' }, { label: 'Reels' }]}
      eyebrow="Reels"
      title="See content readiness without guessing"
      subtitle="Use this route when you want a simple answer to what happened to a piece of content and whether it is ready for the next step."
      cuesSummary={cueSummaryForRoute('Check lifecycle, package readiness, and jump straight into review or detail from the same table.')}
      actions={<ActionCluster items={[{ href: '/queue', label: 'Open Queue', tone: 'primary' }]} />}
      cues={[
        {
          label: 'What this page is for',
          value: 'Understand whether a reel is observed, generated, ready for review, blocked, or already posted.',
        },
        {
          label: 'What you can do here',
          value: 'Open reel detail, inspect packages, or jump straight into the action workspace with reel IDs filled in.',
        },
        {
          label: 'What comes next',
          value: 'If a reel is ready, move to Queue or Actions for the human review step.',
        },
      ]}
    >
      {dashboard.reels.state === 'ready' && workbenchRows.length > 0 ? (
        <SectionCard
          title="QA failure triage"
          description="Separate semantic or compliance issues from packaging and integrity problems. Filters narrow the recent reel list; the triage table always lists every blocked reel."
        >
          <QaFailedWorkbench
            orgId={dashboard.context.orgId}
            basePath="/reels"
            activeFilter={triageFilter}
            rows={workbenchRows}
          />
        </SectionCard>
      ) : null}

      <SectionCard
        title="Recent reels"
        description="Every reel row explains state in plain language and links to the next relevant workspace."
        note={dashboard.reels.state === 'ready' ? dashboard.reels.message : undefined}
      >
        {dashboard.reels.state === 'ready' ? (
          reels.length > 0 ? (
            <ReelsTable reels={reels} orgId={dashboard.context.orgId} />
          ) : (
            <EmptyState
              title="No reels match this QA filter"
              message="Clear the failure-class filter to see the full recent reel feed again."
              tone="neutral"
              actions={<LinkAction href="/reels" label="Show all reels" tone="primary" />}
            />
          )
        ) : (
          <ResourceStateBlock
            title="Reels are not available yet"
            state={dashboard.reels.state}
            message={dashboard.reels.message}
            action={<LinkAction href="/pages" label="Open Pages" />}
          />
        )}
      </SectionCard>
    </DetailFrame>
  );
}

export function QueueRouteView({
  dashboard,
  qaFailureFilter,
}: {
  dashboard: OperatorDashboardSnapshot;
  qaFailureFilter?: string;
}) {
  const queue = buildPackageReviewQueue(dashboard);
  const triageFilter = normalizeQaFailureFilter(qaFailureFilter);
  const workbenchRows = queue.state === 'ready' ? reviewQueueToWorkbenchRows(queue.data) : [];
  const filteredQueue =
    queue.state === 'ready' ? queue.data.filter((item) => queueItemMatchesQaFailureFilter(item, triageFilter)) : [];
  const readyCount = queue.state === 'ready' ? queue.data.filter((item) => item.queueState === 'ready_for_review').length : 0;
  const qaFailedCount = queue.state === 'ready' ? queue.data.filter((item) => item.queueState === 'qa_failed').length : 0;
  const postedCount = queue.state === 'ready' ? queue.data.filter((item) => item.queueState === 'posted').length : 0;

  return (
    <DetailFrame
      breadcrumbs={[{ label: 'Home', href: '/' }, { label: 'Queue' }]}
      eyebrow="Queue"
      title="The human review workspace"
      subtitle="Use Queue when a person needs to make a decision: review content, investigate a failure, or record that something was already posted."
      cuesSummary={cueSummaryForRoute('Keep review-ready, QA-failed, and posted reels in one working list, then jump into the next safe action.')}
      actions={<ActionCluster items={[{ href: '/actions', label: 'Review in Actions', tone: 'primary' }, { href: '/pages', label: 'Open Pages' }]} />}
      cues={[
        {
          label: 'What this page is for',
          value: 'Collect every generated reel that needs human attention into one working list.',
        },
        {
          label: 'What you can do here',
          value: 'Open a reel, inspect its package, approve or archive it, or record manual posting with the right IDs in place.',
        },
        {
          label: 'What comes next',
          value: 'Move from Queue into Actions or reel detail depending on whether you are reviewing or investigating.',
        },
      ]}
    >
      <SectionCard title="Queue summary" description="These counts show how much human work is waiting right now.">
        <MetaGrid
          items={[
            { label: 'Ready for review', value: readyCount },
            { label: 'QA failed', value: qaFailedCount },
            { label: 'Posted', value: postedCount },
            { label: 'Source', value: 'Generated reels only' },
          ]}
        />
      </SectionCard>

      {queue.state === 'ready' && workbenchRows.length > 0 ? (
        <SectionCard
          title="QA failure triage"
          description="QA-failed queue items are grouped by whether the problem is mostly creative or mostly packaging. Filters apply to the working list below while this table keeps the full blocked set visible."
        >
          <QaFailedWorkbench
            orgId={dashboard.context.orgId}
            basePath="/queue"
            activeFilter={triageFilter}
            rows={workbenchRows}
          />
        </SectionCard>
      ) : null}

      <SectionCard
        title="Review and posting queue"
        description="Each item explains why it is here and offers direct links to the next safe action."
        note={queue.state === 'ready' ? queue.message : undefined}
      >
        {queue.state === 'ready' ? (
          filteredQueue.length > 0 ? (
            <QueueTable queue={filteredQueue} orgId={dashboard.context.orgId} />
          ) : (
            <EmptyState
              title="No queue items match this QA filter"
              message="Clear the failure-class filter to see ready, QA-failed, and posted items together again."
              tone="neutral"
              actions={<LinkAction href="/queue" label="Show full queue" tone="primary" />}
            />
          )
        ) : (
          <ResourceStateBlock
            title="Queue items are not available yet"
            state={queue.state}
            message={queue.message}
            action={<LinkAction href="/actions" label="Open Actions" />}
          />
        )}
      </SectionCard>
    </DetailFrame>
  );
}

export function PolicyRouteView({ snapshot }: { snapshot: PolicyEditorSnapshot }) {
  const records = snapshot.policies.state === 'ready' ? snapshot.policies.data : [];
  const inheritedCount = records.filter((record) => record.source === 'inherited').length;

  return (
    <DetailFrame
      breadcrumbs={[{ label: 'Home', href: '/' }, { label: 'Policy' }]}
      eyebrow="Policy"
      title="Guardrails that shape what the system is allowed to do"
      subtitle="Use Policy when you need to change how adventurous, expensive, or strict the system is allowed to be for a page."
      cuesSummary={cueSummaryForRoute('Adjust safe ranges for each page without leaving the allowed phase-1 schema.')}
      actions={<ActionCluster items={[{ href: '/pages', label: 'Open Pages' }, { href: '/actions', label: 'Open Actions', tone: 'secondary' }]} />}
      cues={[
        {
          label: 'What this page is for',
          value: 'Adjust page-level budgets, mode ratios, and thresholds without leaving the allowed schema.',
        },
        {
          label: 'What you can do here',
          value: 'Understand explicit overrides versus inherited guardrails, and patch safe ranges through the audited route.',
        },
        {
          label: 'What comes next',
          value: 'After updating policy, return to Pages or Actions to start new work under the new guardrails.',
        },
      ]}
    >
      <SectionCard
        title="What these controls affect"
        description="Policy does not create content by itself. It shapes how the system budgets work, how exploratory it is, and when similarity or quality thresholds should stop a reel."
      >
        <MetaGrid
          items={[
            { label: 'Mode ratios', value: 'Control the balance between safer exploitation and more exploratory generation.' },
            { label: 'Budget guardrails', value: 'Set upper bounds on spend per run, per day, and per month.' },
            { label: 'Thresholds', value: 'Define when similarity warns or blocks and the minimum QA score that work should meet.' },
            {
              label: 'Pages inheriting',
              value: snapshot.policies.state === 'ready' ? inheritedCount : 'Unknown',
            },
          ]}
        />
      </SectionCard>

      <SectionCard
        title="Page policy editor"
        description="Edit one page at a time with inline guidance about safe ranges and the effect of each section."
        note={snapshot.policies.state === 'ready' ? snapshot.policies.message : undefined}
      >
        {snapshot.policies.state === 'ready' && snapshot.context.orgId ? (
          <PolicyEditor apiBaseUrl={snapshot.context.apiBaseUrl} orgId={snapshot.context.orgId} records={snapshot.policies.data} />
        ) : (
          <ResourceStateBlock
            title="Policy is not available yet"
            state={snapshot.policies.state}
            message={snapshot.policies.message}
            action={<LinkAction href="/pages" label="Open Pages" />}
          />
        )}
      </SectionCard>
    </DetailFrame>
  );
}
