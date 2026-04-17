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

function FeatureDirectory() {
  const features = [
    {
      title: 'Pages',
      description: 'Use Pages as the main hub, then move through each page workspace without losing context.',
      href: '/pages',
    },
    {
      title: 'Queue',
      description: 'Handle the human review and posting workflow without missing items that need attention.',
      href: '/queue',
    },
    {
      title: 'Actions',
      description: 'Start workflows, process a reel, approve or archive, and record manual posting.',
      href: '/actions',
    },
  ];

  return (
    <div className="cl-card-grid">
      {features.map((feature) => (
        <article key={feature.title} className="cl-card cl-card-compact">
          <div className="cl-kicker">Feature</div>
          <h3 className="cl-card-title">{feature.title}</h3>
          <p className="cl-card-description">{feature.description}</p>
          <LinkAction href={feature.href} label={`Open ${feature.title}`} />
        </article>
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

function NewHerePanel() {
  return (
    <div className="cl-card-grid">
      <article className="cl-card cl-card-compact">
        <div className="cl-kicker">If you are new</div>
        <h3 className="cl-card-title">Start with Pages</h3>
        <p className="cl-card-description">
          Choose the account you are working on first. That page now carries its own overview,
          reels, runs, and policy tabs before you take action.
        </p>
        <LinkAction href="/pages" label="Open Pages" />
      </article>
      <article className="cl-card cl-card-compact">
        <div className="cl-kicker">Then move to</div>
        <h3 className="cl-card-title">Queue or Actions</h3>
        <p className="cl-card-description">
          Go to Queue if you are reviewing existing work. Go to Actions if you are starting
          something new or recording a human step.
        </p>
        <div className="cl-button-row">
          <LinkAction href="/queue" label="Open Queue" />
          <LinkAction href="/actions" label="Open Actions" tone="secondary" />
        </div>
      </article>
    </div>
  );
}

function WorkflowSteps() {
  const steps = [
    {
      label: '1. Choose a page',
      copy: 'Open Pages to confirm which account you are working on and inspect its context.',
      href: '/pages',
    },
    {
      label: '2. Open the page workspace',
      copy: 'Use the page overview, reels, runs, and policy tabs to stay inside one account context.',
      href: pagePath(demoIds.orgId, demoIds.pageId),
    },
    {
      label: '3. Start work',
      copy: 'Open Actions to launch a workflow or process a specific reel with explicit audited inputs.',
      href: '/actions',
    },
    {
      label: '4. Review output',
      copy: 'Use Queue to approve, archive, or investigate items that need human attention.',
      href: '/queue',
    },
    {
      label: '5. Inspect the package',
      copy: 'Open reel or package detail to confirm downloads, provenance, and publishable files.',
      href: packagePath(demoIds.orgId, demoIds.runId),
    },
    {
      label: '6. Record posting',
      copy: 'After a human posts externally, record the outcome in Actions without autoposting.',
      href: buildActionPath({ orgId: demoIds.orgId, pageId: demoIds.pageId, reelId: demoIds.reelId }),
    },
  ];

  return (
    <div className="cl-card-grid">
      {steps.map((step) => (
        <article key={step.label} className="cl-card cl-card-compact">
          <div className="cl-kicker">Daily workflow</div>
          <h3 className="cl-card-title">{step.label}</h3>
          <p className="cl-card-description">{step.copy}</p>
          <LinkAction href={step.href} label="Open step" />
        </article>
      ))}
    </div>
  );
}

function DashboardMetrics({ dashboard }: { dashboard: OperatorDashboardSnapshot }) {
  const queue = buildPackageReviewQueue(dashboard);

  const items = [
    { label: 'Pages in scope', value: dashboard.pages.state === 'ready' ? dashboard.pages.data.length : 'Not connected' },
    { label: 'Current runs', value: dashboard.runs.state === 'ready' ? dashboard.runs.data.length : 'Not available' },
    { label: 'Recent reels', value: dashboard.reels.state === 'ready' ? dashboard.reels.data.length : 'Not available' },
    { label: 'Queue items', value: queue.state === 'ready' ? queue.data.length : 'Not available' },
  ];

  return (
    <div className="cl-stat-grid">
      {items.map((item) => (
        <article key={item.label} className="cl-stat-card">
          <div className="cl-meta-label">{item.label}</div>
          <div className="cl-stat-value">{item.value}</div>
        </article>
      ))}
    </div>
  );
}

function QueueSummaryCards({ dashboard }: { dashboard: OperatorDashboardSnapshot }) {
  const queue = buildPackageReviewQueue(dashboard);
  const items =
    queue.state === 'ready'
      ? [
          {
            label: 'Ready for review',
            value: queue.data.filter((item) => item.queueState === 'ready_for_review').length,
          },
          {
            label: 'QA failed',
            value: queue.data.filter((item) => item.queueState === 'qa_failed').length,
          },
          {
            label: 'Posted',
            value: queue.data.filter((item) => item.queueState === 'posted').length,
          },
        ]
      : [
          { label: 'Ready for review', value: 'Not loaded' },
          { label: 'QA failed', value: 'Not loaded' },
          { label: 'Posted', value: 'Not loaded' },
        ];

  return <MetaGrid items={items} />;
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

function RecentActivity({ dashboard }: { dashboard: OperatorDashboardSnapshot }) {
  const queue = buildPackageReviewQueue(dashboard);

  return (
    <div className="cl-card-grid">
      <article className="cl-card">
        <div className="cl-kicker">Pages</div>
        <h3 className="cl-card-title">
          {dashboard.pages.state === 'ready' ? dashboard.pages.data[0]?.displayName ?? 'No pages yet' : 'Pages unavailable'}
        </h3>
        <p className="cl-card-description">
          {dashboard.pages.state === 'ready'
            ? 'Start from the page you manage, then stay inside that page workspace for reels, runs, and policy.'
            : dashboard.pages.message ?? 'Connect an org to begin loading pages.'}
        </p>
        <LinkAction href="/pages" label="Open Pages" />
      </article>
      <article className="cl-card">
        <div className="cl-kicker">Page workspace</div>
        <h3 className="cl-card-title">
          {dashboard.pages.state === 'ready' ? 'Overview, reels, runs, policy' : 'Workspace unavailable'}
        </h3>
        <p className="cl-card-description">
          {dashboard.pages.state === 'ready'
            ? 'Every page now groups its own content, automation, and guardrails in one place.'
            : dashboard.pages.message ?? 'Choose an org to load page workspaces.'}
        </p>
        <LinkAction
          href={
            dashboard.pages.state === 'ready' && dashboard.pages.data[0]
              ? pagePath(dashboard.context.orgId ?? demoIds.orgId, dashboard.pages.data[0].id)
              : pagePath(demoIds.orgId, demoIds.pageId)
          }
          label="Open a page workspace"
        />
      </article>
      <article className="cl-card">
        <div className="cl-kicker">Queue</div>
        <h3 className="cl-card-title">
          {queue.state === 'ready' ? `${queue.data.length} items need attention` : 'Queue unavailable'}
        </h3>
        <p className="cl-card-description">
          {queue.state === 'ready'
            ? 'Queue brings review-ready, QA-failed, and posted reels into one operator workflow.'
            : queue.message ?? 'Queue items appear when generated reels reach a human step.'}
        </p>
        <LinkAction href="/queue" label="Open Queue" />
      </article>
    </div>
  );
}

export function HomeRouteView({ dashboard }: { dashboard: OperatorDashboardSnapshot }) {
  const configured = dashboard.context.orgId !== null;

  return (
    <DetailFrame
      breadcrumbs={[{ label: 'Home' }]}
      eyebrow="Start here"
      title="A guided operator workspace for Content Lab"
      subtitle="This UI is now page-first: operators choose a page, stay inside that page workspace for reels, runs, and policy, then use Queue or Actions only when the workflow crosses page boundaries."
      cuesSummary="Open this quick guide if you want the short version of what this workspace does and where to go next."
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
      cues={[
        {
          label: 'What this workspace is for',
          value: 'Operate the reel workflow from page selection through human review and manual posting records.',
        },
        {
          label: 'What you can do here',
          value: 'Navigate every feature, understand the language of the system, and jump into the next recommended action.',
        },
        {
          label: 'What comes next',
          value: configured
            ? 'Choose a page, then use its tabs to move through reels, runs, and policy.'
            : 'Choose a workspace org in the sidebar to load live data, or use the sample detail links while onboarding.',
        },
      ]}
    >
      {!configured ? (
        <SectionCard
          title="Connect your workspace"
          description="The shell is ready, but live org-scoped data needs a workspace org before it can load pages, runs, reels, queue items, and policy."
          actions={<LinkAction href="/actions" label="Open Actions anyway" />}
        >
          <EmptyState
            title="Live data is not connected yet"
            message={
              dashboard.context.configurationMessage ??
              'Use the workspace org control in the sidebar so the primary routes can load live API data.'
            }
            tone="warning"
            actions={
              <>
                <LinkAction href={pagePath(demoIds.orgId, demoIds.pageId)} label="Open sample page" />
                <LinkAction href={reelPath(demoIds.orgId, demoIds.pageId, demoIds.reelId)} label="Open sample reel" />
              </>
            }
          />
        </SectionCard>
      ) : null}

      <SectionCard
        title="Start here today"
        description="This is the shortest path to understanding the workspace and acting on current work."
      >
        <DashboardMetrics dashboard={dashboard} />
        <QueueSummaryCards dashboard={dashboard} />
        <NewHerePanel />
        <RecentActivity dashboard={dashboard} />
      </SectionCard>

      <SectionCard
        title="Workspace map"
        description="Keep every feature visible, but grouped into the two questions operators usually have: where do I go, and in what order?"
      >
        <div className="cl-form-columns">
          <div className="cl-stack-md">
            <WorkflowSteps />
          </div>
          <div className="cl-stack-md">
            <FeatureDirectory />
          </div>
        </div>
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

export function ReelsRouteView({ dashboard }: { dashboard: OperatorDashboardSnapshot }) {
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
      <SectionCard
        title="Recent reels"
        description="Every reel row explains state in plain language and links to the next relevant workspace."
        note={dashboard.reels.state === 'ready' ? dashboard.reels.message : undefined}
      >
        {dashboard.reels.state === 'ready' ? (
          <ReelsTable reels={dashboard.reels.data} orgId={dashboard.context.orgId} />
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

export function QueueRouteView({ dashboard }: { dashboard: OperatorDashboardSnapshot }) {
  const queue = buildPackageReviewQueue(dashboard);
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

      <SectionCard
        title="Review and posting queue"
        description="Each item explains why it is here and offers direct links to the next safe action."
        note={queue.state === 'ready' ? queue.message : undefined}
      >
        {queue.state === 'ready' ? (
          <QueueTable queue={queue.data} orgId={dashboard.context.orgId} />
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
  const defaultsCount = records.filter((record) => record.source === 'default').length;

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
          value: 'Understand current policy source, compare default versus saved values, and patch safe ranges through the audited route.',
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
            { label: 'Pages on defaults', value: snapshot.policies.state === 'ready' ? defaultsCount : 'Unknown' },
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
