import React from 'react';
import { notFound } from 'next/navigation';

import {
  DetailFrame,
  JsonPanel,
  LinkAction,
  MetaGrid,
  SectionCard,
  StatusBadge,
  formatTimestamp,
} from '../../../../_components/detail-ui';
import {
  packagePath,
  pagePath,
  pageRunsPath,
  reelPath,
} from '../../../../_lib/content-lab-data';
import { loadOperatorRunDetail } from '../../../../_lib/operator-page-workspace';

function buildActionPath(orgId: string, pageId: string | null, reelId: string | null): string {
  const params = new URLSearchParams({
    orgId,
  });

  if (pageId) {
    params.set('pageId', pageId);
  }
  if (reelId) {
    params.set('reelId', reelId);
  }

  return `/actions?${params.toString()}`;
}

export default async function RunDetailPage({
  params,
}: {
  params: Promise<{ orgId: string; runId: string }>;
}) {
  const { orgId, runId } = await params;
  const detail = await loadOperatorRunDetail(orgId, runId);

  if (detail === null) {
    notFound();
  }

  const { run, page, reel, packageDetail } = detail;

  return (
    <DetailFrame
      breadcrumbs={
        page
          ? [
              { label: 'Home', href: '/' },
              { label: 'Pages', href: '/pages' },
              { label: page.display_name, href: pagePath(run.org_id, page.id) },
              { label: 'Runs', href: pageRunsPath(run.org_id, page.id) },
              { label: `Run ${run.id.slice(0, 8)}` },
            ]
          : [
              { label: 'Home', href: '/' },
              { label: 'Pages', href: '/pages' },
              { label: `Run ${run.id.slice(0, 8)}` },
            ]
      }
      eyebrow={run.workflow_key}
      title={`Run ${run.id.slice(0, 8)}`}
      subtitle="This run detail keeps its page context when available, so operators can move back to the owning page workspace instead of a global runs index."
      actions={
        <>
          <StatusBadge status={run.status} />
          <LinkAction
            href={buildActionPath(run.org_id, page?.id ?? null, reel?.id ?? null)}
            label="Open in Actions"
            tone="primary"
          />
          {page ? <LinkAction href={pagePath(run.org_id, page.id)} label="Open page" /> : null}
          {page ? (
            <LinkAction href={pageRunsPath(run.org_id, page.id)} label="Back to page runs" />
          ) : null}
          {page && reel ? (
            <LinkAction href={reelPath(run.org_id, page.id, reel.id)} label="Open reel" />
          ) : null}
          {packageDetail ? (
            <LinkAction href={packagePath(run.org_id, run.id)} label="Open package" />
          ) : null}
        </>
      }
      cues={[
        {
          label: 'What this page is for',
          value: 'Explain a single workflow run without losing the page and reel it belongs to.',
        },
        {
          label: 'What you can do here',
          value: 'See timing, task-level progress, linked content, and the output package in one place.',
        },
        {
          label: 'What comes next',
          value: 'Return to the page runs tab when monitoring multiple runs, or open the linked reel/package for deeper review.',
        },
      ]}
    >
      <SectionCard
        title="Run summary"
        description="Start with this summary to understand the run before looking at individual tasks or raw metadata."
      >
        <MetaGrid
          items={[
            { label: 'Workflow key', value: run.workflow_key },
            { label: 'Flow trigger', value: run.flow_trigger },
            { label: 'External ref', value: run.external_ref ?? 'Not recorded' },
            { label: 'Idempotency key', value: run.idempotency_key ?? 'Not recorded' },
            { label: 'Started at', value: formatTimestamp(run.started_at) },
            { label: 'Finished at', value: formatTimestamp(run.finished_at) },
            {
              label: 'Task counts',
              value: Object.entries(run.task_status_counts)
                .map(([status, count]) => `${status}: ${count}`)
                .join(', '),
            },
            { label: 'Package linked', value: packageDetail ? 'Yes' : 'No' },
          ]}
        />
      </SectionCard>

      <SectionCard
        title="Task summaries"
        description="Use these task summaries to understand what part of the workflow finished, failed, or is still running."
      >
        <div className="cl-stack-md">
          {run.tasks.map((task) => (
            <article key={task.id} className="cl-entity-card">
              <div className="cl-split">
                <div>
                  <div className="cl-step-label">{task.idempotency_key}</div>
                  <div className="cl-entity-title">{task.task_type}</div>
                </div>
                <StatusBadge status={task.status} />
              </div>
              <MetaGrid
                items={[
                  { label: 'Created', value: formatTimestamp(task.created_at) },
                  { label: 'Updated', value: formatTimestamp(task.updated_at) },
                ]}
              />
              <div className="cl-stack-md">
                <JsonPanel title="Task payload" value={task.payload} />
                <JsonPanel title="Task result" value={task.result} />
              </div>
            </article>
          ))}
        </div>
      </SectionCard>

      <SectionCard
        title="Run payloads"
        description="These raw payloads are secondary diagnostics when you need to correlate the UI with backend behavior."
      >
        <div className="cl-stack-md">
          <JsonPanel title="Input params" value={run.input_params} />
          <JsonPanel title="Run metadata" value={run.run_metadata} />
          <JsonPanel title="Output payload" value={run.output_payload} />
        </div>
      </SectionCard>
    </DetailFrame>
  );
}
