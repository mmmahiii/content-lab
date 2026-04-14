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
import { getRunDetail, packagePath, pagePath, reelPath } from '../../../../_lib/content-lab-data';

export default async function RunDetailPage({
  params,
}: {
  params: Promise<{ orgId: string; runId: string }>;
}) {
  const { orgId, runId } = await params;
  const detail = await getRunDetail(orgId, runId);

  if (detail === null) {
    notFound();
  }

  const { run, page, reel, packageDetail } = detail;

  return (
    <DetailFrame
      breadcrumbs={[
        { label: 'Home', href: '/' },
        { label: 'Runs', href: '/runs' },
        { label: `Run ${run.id.slice(0, 8)}` },
      ]}
      eyebrow={run.workflow_key}
      title={`Run ${run.id.slice(0, 8)}`}
      subtitle="This run detail explains what started the workflow, where it is now, and how the tasks and payloads fit together."
      actions={
        <>
          <StatusBadge status={run.status} />
          <LinkAction
            href={`/actions?orgId=${run.org_id}${reel ? `&pageId=${page?.id ?? ''}&reelId=${reel.id}` : ''}`}
            label="Open in Actions"
            tone="primary"
          />
          {page ? <LinkAction href={pagePath(run.org_id, page.id)} label="Open page" /> : null}
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
          value: 'Explain a single workflow run without making you read raw payloads first.',
        },
        {
          label: 'What you can do here',
          value: 'See timing, task-level progress, linked content, and the output package in one place.',
        },
        {
          label: 'What comes next',
          value: 'If the run is still moving, return to Runs later. If it finished, inspect the reel or package.',
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
