import React from 'react';
import Link from 'next/link';

import { PolicyEditor } from './policy-editor';
import {
  DetailFrame,
  LinkAction,
  MetaGrid,
  SectionCard,
  StatusBadge,
  formatStatus,
  formatTimestamp,
} from './detail-ui';
import {
  packagePath,
  pagePath,
  pagePolicyPath,
  pageReelsPath,
  pageRunsPath,
  reelPath,
  runPath,
} from '../_lib/content-lab-data';
import type { PolicyEditorRecord } from '../_lib/operator-policy';
import type { PageWorkspaceSnapshot } from '../_lib/operator-page-workspace';

export type PageWorkspaceTab = 'overview' | 'reels' | 'runs' | 'policy';

type TabItem = {
  href: string;
  label: string;
  meta: string;
  active: boolean;
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

function policySummaryLabel(snapshot: PageWorkspaceSnapshot): string {
  if (snapshot.policy === null) {
    return 'Policy unavailable';
  }
  if (snapshot.policy.is_explicit_override) {
    return 'Saved override';
  }
  return snapshot.policy.inherited_from === 'global' ? 'Inherited (org)' : 'Inherited (defaults)';
}

function buildTabItems(snapshot: PageWorkspaceSnapshot, currentTab: PageWorkspaceTab): TabItem[] {
  const { orgId } = snapshot.context;
  const { page } = snapshot;

  return [
    {
      href: pagePath(orgId, page.id),
      label: 'Overview',
      meta: 'Summary',
      active: currentTab === 'overview',
    },
    {
      href: pageReelsPath(orgId, page.id),
      label: 'Reels',
      meta: String(snapshot.reels.length),
      active: currentTab === 'reels',
    },
    {
      href: pageRunsPath(orgId, page.id),
      label: 'Runs',
      meta: String(snapshot.runs.length),
      active: currentTab === 'runs',
    },
    {
      href: pagePolicyPath(orgId, page.id),
      label: 'Policy',
      meta: policySummaryLabel(snapshot),
      active: currentTab === 'policy',
    },
  ];
}

function PageWorkspaceTabs({
  snapshot,
  currentTab,
}: {
  snapshot: PageWorkspaceSnapshot;
  currentTab: PageWorkspaceTab;
}) {
  return (
    <nav className="cl-page-tabs" aria-label="Page workspace sections">
      {buildTabItems(snapshot, currentTab).map((tab) => (
        <Link
          key={tab.href}
          href={tab.href}
          className="cl-page-tab"
          aria-current={tab.active ? 'page' : undefined}
        >
          <span className="cl-page-tab-label">{tab.label}</span>
          <span className="cl-page-tab-meta">{tab.meta}</span>
        </Link>
      ))}
    </nav>
  );
}

function WorkspaceIntro({
  snapshot,
  currentTab,
}: {
  snapshot: PageWorkspaceSnapshot;
  currentTab: PageWorkspaceTab;
}) {
  const currentLabel =
    currentTab === 'overview'
      ? 'Overview'
      : currentTab === 'reels'
        ? 'Reels'
        : currentTab === 'runs'
          ? 'Runs'
          : 'Policy';

  return (
    <MetaGrid
      items={[
        { label: 'Current section', value: currentLabel },
        { label: 'Reels on this page', value: snapshot.reels.length },
        { label: 'Runs on this page', value: snapshot.runs.length },
        { label: 'Policy state', value: policySummaryLabel(snapshot) },
      ]}
    />
  );
}

function PageWorkspaceFrame({
  snapshot,
  currentTab,
  title,
  subtitle,
  children,
}: {
  snapshot: PageWorkspaceSnapshot;
  currentTab: PageWorkspaceTab;
  title: string;
  subtitle: string;
  children: React.ReactNode;
}) {
  const { page, context } = snapshot;

  return (
    <DetailFrame
      breadcrumbs={[
        { label: 'Home', href: '/' },
        { label: 'Pages', href: '/pages' },
        { label: page.display_name },
      ]}
      eyebrow={`${page.platform} page workspace`}
      title={title}
      subtitle={subtitle}
      actions={
        <>
          <StatusBadge status={page.ownership} />
          <LinkAction href="/pages" label="Back to Pages" />
          <LinkAction
            href={buildActionPath({ orgId: context.orgId, pageId: page.id })}
            label="Open in Actions"
            tone="primary"
          />
          <LinkAction href="/queue" label="Open Queue" tone="secondary" />
        </>
      }
      cues={[
        {
          label: 'Workflow pattern',
          value: 'Start with the page, then move into its reels, runs, and policy without leaving context.',
        },
        {
          label: 'What stays global',
          value: 'Queue stays global for human review worklists, and Actions stays global for audited operator tasks.',
        },
        {
          label: 'What comes next',
          value: 'Use the tabs below to move across this page workspace without losing account context.',
        },
      ]}
    >
      <SectionCard
        title="Page workspace"
        description="Everything below stays scoped to this page so operators do not have to mentally reassemble context."
      >
        <PageWorkspaceTabs snapshot={snapshot} currentTab={currentTab} />
        <WorkspaceIntro snapshot={snapshot} currentTab={currentTab} />
      </SectionCard>
      {children}
    </DetailFrame>
  );
}

function PageOverviewPanel({ snapshot }: { snapshot: PageWorkspaceSnapshot }) {
  const { page, policy } = snapshot;
  const disclosureCount = page.metadata.constraints.required_disclosures.length;

  return (
    <SectionCard
      title="Page summary"
      description="Start here when you need to reorient on the account before touching content or workflows."
    >
      <MetaGrid
        items={[
          { label: 'Handle', value: page.handle ?? 'Not recorded' },
          { label: 'External page id', value: page.external_page_id ?? 'Not recorded' },
          { label: 'Persona label', value: page.metadata.persona?.label ?? 'Not configured' },
          { label: 'Audience', value: page.metadata.persona?.audience ?? 'Not configured' },
          {
            label: 'Content pillars',
            value: page.metadata.persona?.content_pillars.join(', ') ?? 'None',
          },
          { label: 'Required disclosures', value: disclosureCount === 0 ? 'None' : disclosureCount },
          {
            label: 'Primary policy mode',
            value: policy
              ? Object.entries(policy.state.mode_ratios)
                  .sort((left, right) => right[1] - left[1])[0]?.[0] ?? 'Balanced'
              : 'Default guardrails',
          },
          { label: 'Updated', value: formatTimestamp(page.updated_at) },
        ]}
      />
    </SectionCard>
  );
}

function PageReelsTable({ snapshot }: { snapshot: PageWorkspaceSnapshot }) {
  if (snapshot.reels.length === 0) {
    return (
      <div className="cl-empty">
        <strong>No reels on this page yet</strong>
        <p className="cl-panel-description">
          Start from Actions when you are ready to trigger or process work for this page.
        </p>
      </div>
    );
  }

  return (
    <div className="cl-table-wrap">
      <table className="cl-table">
        <thead>
          <tr>
            <th>Reel</th>
            <th>Status</th>
            <th>Related run</th>
            <th>Updated</th>
            <th>Next actions</th>
          </tr>
        </thead>
        <tbody>
          {snapshot.reels.map((entry) => (
            <tr key={entry.reel.id}>
              <td>
                <div className="cl-resource-title">
                  <strong>{entry.reel.variant_label ?? `Reel ${entry.reel.id.slice(0, 8)}`}</strong>
                  <span className="cl-resource-meta">{formatStatus(entry.reel.origin)}</span>
                </div>
              </td>
              <td>
                <div className="cl-inline-list">
                  <StatusBadge status={entry.reel.status} />
                  {entry.hasPackage ? <StatusBadge status="package ready" /> : null}
                </div>
              </td>
              <td>
                <div className="cl-resource-title">
                  <strong>{entry.relatedRunId ?? 'No linked run yet'}</strong>
                  <span className="cl-resource-meta">
                    {entry.relatedRunStatus ? formatStatus(entry.relatedRunStatus) : 'No run status yet'}
                  </span>
                </div>
              </td>
              <td>{formatTimestamp(entry.reel.updated_at)}</td>
              <td>
                <div className="cl-button-row">
                  <LinkAction
                    href={reelPath(snapshot.context.orgId, snapshot.page.id, entry.reel.id)}
                    label="Open reel detail"
                  />
                  {entry.relatedRunId ? (
                    <LinkAction
                      href={runPath(snapshot.context.orgId, entry.relatedRunId)}
                      label="Open run"
                    />
                  ) : null}
                  {entry.relatedRunId && entry.hasPackage ? (
                    <LinkAction
                      href={packagePath(snapshot.context.orgId, entry.relatedRunId)}
                      label="Open package"
                    />
                  ) : null}
                  <LinkAction
                    href={buildActionPath({
                      orgId: snapshot.context.orgId,
                      pageId: snapshot.page.id,
                      reelId: entry.reel.id,
                    })}
                    label="Open in Actions"
                    tone="secondary"
                  />
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PageRunsTable({ snapshot }: { snapshot: PageWorkspaceSnapshot }) {
  if (snapshot.runs.length === 0) {
    return (
      <div className="cl-empty">
        <strong>No runs on this page yet</strong>
        <p className="cl-panel-description">
          Runs will appear here after someone triggers work against this page.
        </p>
      </div>
    );
  }

  return (
    <div className="cl-table-wrap">
      <table className="cl-table">
        <thead>
          <tr>
            <th>Run</th>
            <th>Status</th>
            <th>Linked reel</th>
            <th>Updated</th>
            <th>Next actions</th>
          </tr>
        </thead>
        <tbody>
          {snapshot.runs.map((entry) => (
            <tr key={entry.run.id}>
              <td>
                <div className="cl-resource-title">
                  <strong>{entry.run.workflow_key}</strong>
                  <span className="cl-resource-meta">{entry.run.external_ref ?? entry.run.id}</span>
                </div>
              </td>
              <td>
                <div className="cl-inline-list">
                  <StatusBadge status={entry.run.status} />
                  <span className="cl-resource-meta">{formatStatus(entry.run.flow_trigger)}</span>
                </div>
              </td>
              <td>
                <div className="cl-resource-title">
                  <strong>{entry.reelId ?? 'No linked reel'}</strong>
                  <span className="cl-resource-meta">
                    {entry.hasPackage ? 'Package available' : 'Package not ready'}
                  </span>
                </div>
              </td>
              <td>{formatTimestamp(entry.run.updated_at)}</td>
              <td>
                <div className="cl-button-row">
                  <LinkAction
                    href={runPath(snapshot.context.orgId, entry.run.id)}
                    label="Open run detail"
                  />
                  {entry.reelId ? (
                    <LinkAction
                      href={reelPath(snapshot.context.orgId, snapshot.page.id, entry.reelId)}
                      label="Open reel"
                    />
                  ) : null}
                  {entry.hasPackage ? (
                    <LinkAction
                      href={packagePath(snapshot.context.orgId, entry.run.id)}
                      label="Open package"
                    />
                  ) : null}
                  <LinkAction
                    href={buildActionPath({
                      orgId: snapshot.context.orgId,
                      pageId: snapshot.page.id,
                      reelId: entry.reelId,
                    })}
                    label="Open in Actions"
                    tone="secondary"
                  />
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function buildPolicyRecord(snapshot: PageWorkspaceSnapshot): PolicyEditorRecord {
  const fallbackState = {
    mode_ratios: {
      exploit: 0.3,
      explore: 0.4,
      mutation: 0.2,
      chaos: 0.1,
    },
    budget: {
      per_run_usd_limit: 10,
      daily_usd_limit: 40,
      monthly_usd_limit: 800,
    },
    thresholds: {
      similarity: {
        warn_at: 0.72,
        block_at: 0.88,
      },
      min_quality_score: 0.55,
    },
  };

  const policy =
    snapshot.policy ??
    ({
      id: null,
      org_id: snapshot.context.orgId,
      scope_type: 'page' as const,
      scope_id: snapshot.page.id,
      state: fallbackState,
      updated_at: null,
      is_explicit_override: false,
      inherited_from: 'default' as const,
    });

  const baseline = policy.state;

  return {
    page: {
      id: snapshot.page.id,
      displayName: snapshot.page.display_name,
      platform: snapshot.page.platform,
      handle: snapshot.page.handle,
      ownership: snapshot.page.ownership,
      updatedAt: snapshot.page.updated_at,
    },
    policy,
    baseline,
    draft: {
      mode_ratios: { ...baseline.mode_ratios },
      budget: { ...baseline.budget },
      thresholds: {
        similarity: { ...baseline.thresholds.similarity },
        min_quality_score: baseline.thresholds.min_quality_score,
      },
    },
    source: policy.is_explicit_override ? 'saved' : 'inherited',
  };
}

export function PageOverviewRouteView({ snapshot }: { snapshot: PageWorkspaceSnapshot }) {
  return (
    <PageWorkspaceFrame
      snapshot={snapshot}
      currentTab="overview"
      title={snapshot.page.display_name}
      subtitle="This page is now the primary workspace for this account: overview, reels, runs, and policy all stay together."
    >
      <PageOverviewPanel snapshot={snapshot} />
    </PageWorkspaceFrame>
  );
}

export function PageReelsRouteView({ snapshot }: { snapshot: PageWorkspaceSnapshot }) {
  return (
    <PageWorkspaceFrame
      snapshot={snapshot}
      currentTab="reels"
      title={`${snapshot.page.display_name} reels`}
      subtitle="Review every reel tied to this page without bouncing through a global content index first."
    >
      <SectionCard
        title="Page reels"
        description="Each reel row stays scoped to this page and links directly into its run, package, or action flow."
      >
        <PageReelsTable snapshot={snapshot} />
      </SectionCard>
    </PageWorkspaceFrame>
  );
}

export function PageRunsRouteView({ snapshot }: { snapshot: PageWorkspaceSnapshot }) {
  return (
    <PageWorkspaceFrame
      snapshot={snapshot}
      currentTab="runs"
      title={`${snapshot.page.display_name} runs`}
      subtitle="Track only the runs that belong to this page so operators can see progress without cross-page noise."
    >
      <SectionCard
        title="Page runs"
        description="These runs resolve to this page through their page target and keep links back to the linked reel and package."
      >
        <PageRunsTable snapshot={snapshot} />
      </SectionCard>
    </PageWorkspaceFrame>
  );
}

export function PagePolicyRouteView({ snapshot }: { snapshot: PageWorkspaceSnapshot }) {
  const record = buildPolicyRecord(snapshot);

  return (
    <PageWorkspaceFrame
      snapshot={snapshot}
      currentTab="policy"
      title={`${snapshot.page.display_name} policy`}
      subtitle="Edit the page-level guardrails for this account directly inside the page workspace."
    >
      <SectionCard
        title="Policy context"
        description="Policy now lives with the page it affects, so the operator can inspect the account and adjust guardrails in one place."
      >
        <MetaGrid
          items={[
            { label: 'Policy state', value: policySummaryLabel(snapshot) },
            {
              label: 'Per-run budget',
              value: record.draft.budget.per_run_usd_limit.toFixed(2),
            },
            {
              label: 'Daily budget',
              value: record.draft.budget.daily_usd_limit.toFixed(2),
            },
            {
              label: 'Min QA score',
              value: record.draft.thresholds.min_quality_score.toFixed(2),
            },
          ]}
        />
      </SectionCard>

      <SectionCard
        title="Page policy editor"
        description="These controls patch the page policy route directly, without forcing you into a separate policy workspace."
      >
        <PolicyEditor
          apiBaseUrl={snapshot.context.apiBaseUrl}
          orgId={snapshot.context.orgId}
          records={[record]}
          showPagePicker={false}
        />
      </SectionCard>
    </PageWorkspaceFrame>
  );
}
