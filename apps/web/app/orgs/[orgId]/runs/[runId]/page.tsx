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
  params: { orgId: string; runId: string };
}) {
  const detail = await getRunDetail(params.orgId, params.runId);

  if (detail === null) {
    notFound();
  }

  const { run, page, reel, packageDetail } = detail;

  return (
    <DetailFrame
      eyebrow={run.workflow_key}
      title={`Run ${run.id.slice(0, 8)}`}
      subtitle="Run detail exposes trigger context, orchestration metadata, and task-level progress in one operator view."
      actions={
        <>
          <StatusBadge status={run.status} />
          {page ? <LinkAction href={pagePath(run.org_id, page.id)} label="Open page" /> : null}
          {page && reel ? (
            <LinkAction href={reelPath(run.org_id, page.id, reel.id)} label="Open reel" />
          ) : null}
          {packageDetail ? (
            <LinkAction href={packagePath(run.org_id, run.id)} label="Open package" />
          ) : null}
        </>
      }
    >
      <SectionCard
        title="Run summary"
        description="Workflow key, trigger source, idempotency, and timing remain visible without digging through raw payloads."
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
        description="Task-level payloads and results help operators understand which part of a workflow is blocked or complete."
      >
        <div style={{ display: 'grid', gap: 14 }}>
          {run.tasks.map((task) => (
            <article
              key={task.id}
              style={{
                display: 'grid',
                gap: 14,
                padding: 18,
                borderRadius: 18,
                border: '1px solid rgba(23, 32, 51, 0.12)',
                background: 'rgba(255, 255, 255, 0.78)',
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
                    {task.idempotency_key}
                  </div>
                  <div
                    style={{
                      fontSize: 20,
                      fontFamily: 'Georgia, Cambria, "Times New Roman", Times, serif',
                    }}
                  >
                    {task.task_type}
                  </div>
                </div>
                <StatusBadge status={task.status} />
              </div>
              <MetaGrid
                items={[
                  { label: 'Created', value: formatTimestamp(task.created_at) },
                  { label: 'Updated', value: formatTimestamp(task.updated_at) },
                ]}
              />
              <div style={{ display: 'grid', gap: 14 }}>
                <JsonPanel title="Task payload" value={task.payload} />
                <JsonPanel title="Task result" value={task.result} />
              </div>
            </article>
          ))}
        </div>
      </SectionCard>

      <SectionCard
        title="Run payloads"
        description="The raw input, output, and metadata match the API contracts so operators can correlate UI state with backend behavior."
      >
        <div style={{ display: 'grid', gap: 14 }}>
          <JsonPanel title="Input params" value={run.input_params} />
          <JsonPanel title="Run metadata" value={run.run_metadata} />
          <JsonPanel title="Output payload" value={run.output_payload} />
        </div>
      </SectionCard>
    </DetailFrame>
  );
}
