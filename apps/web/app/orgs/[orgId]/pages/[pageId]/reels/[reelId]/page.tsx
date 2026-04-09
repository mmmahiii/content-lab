import React from 'react';
import { notFound } from 'next/navigation';

import {
  DetailFrame,
  ExternalAction,
  JsonPanel,
  LinkAction,
  MetaGrid,
  SectionCard,
  StatusBadge,
  formatStatus,
  formatTimestamp,
} from '../../../../../../_components/detail-ui';
import {
  getReelDetail,
  packagePath,
  pagePath,
  runPath,
} from '../../../../../../_lib/content-lab-data';

const generatedTimeline = [
  'draft',
  'planning',
  'generating',
  'editing',
  'qa',
  'qa_failed',
  'ready',
  'posted',
  'archived',
];
const observedTimeline = ['active', 'removed', 'unavailable'];

function timelineForStatus(origin: string, currentStatus: string) {
  const timeline = origin === 'generated' ? generatedTimeline : observedTimeline;
  const currentIndex = timeline.indexOf(currentStatus);

  return timeline.map((status, index) => {
    const state =
      status === currentStatus
        ? 'current'
        : currentIndex >= 0 && index < currentIndex
          ? 'complete'
          : 'upcoming';

    return {
      status,
      state,
    };
  });
}

function timelineTone(state: string): string {
  if (state === 'current') {
    return '#a04a2d';
  }
  if (state === 'complete') {
    return '#1f6a4d';
  }
  return '#6d7483';
}

export default async function ReelDetailPage({
  params,
}: {
  params: { orgId: string; pageId: string; reelId: string };
}) {
  const detail = await getReelDetail(params.orgId, params.pageId, params.reelId);

  if (detail === null) {
    notFound();
  }

  const { page, reel, relatedRun, packageDetail } = detail;
  const timeline = timelineForStatus(reel.origin, reel.status);

  return (
    <DetailFrame
      eyebrow={`${reel.origin} reel`}
      title={reel.variant_label ?? `Reel ${reel.id.slice(0, 8)}`}
      subtitle="Reel detail combines lifecycle status, operator review history, and package visibility before any autopost ambitions."
      actions={
        <>
          <LinkAction href={pagePath(page.org_id, page.id)} label="Back to page" />
          <StatusBadge status={reel.status} />
        </>
      }
    >
      <SectionCard
        title="Lifecycle timeline"
        description="Generated reels follow the factory pipeline while observed reels stay on their external visibility states."
      >
        <div style={{ display: 'grid', gap: 12 }}>
          {timeline.map((item) => (
            <div
              key={item.status}
              style={{
                display: 'grid',
                gap: 6,
                padding: 16,
                borderRadius: 18,
                border: '1px solid rgba(23, 32, 51, 0.12)',
                background:
                  item.state === 'current'
                    ? 'rgba(160, 74, 45, 0.08)'
                    : 'rgba(255, 255, 255, 0.75)',
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
                <div style={{ fontWeight: 700, color: timelineTone(item.state) }}>
                  {formatStatus(item.status)}
                </div>
                <div
                  style={{
                    fontSize: 13,
                    color: '#55627a',
                    textTransform: 'uppercase',
                    letterSpacing: '0.08em',
                  }}
                >
                  {item.state}
                </div>
              </div>
            </div>
          ))}
        </div>
      </SectionCard>

      <SectionCard
        title="Operator detail"
        description="Review timestamps, posting timestamps, and the raw reel metadata stay close to the headline status."
      >
        <MetaGrid
          items={[
            { label: 'Page', value: page.display_name },
            { label: 'Family id', value: reel.reel_family_id.slice(0, 8) },
            { label: 'Approved at', value: formatTimestamp(reel.approved_at) },
            { label: 'Approved by', value: reel.approved_by ?? 'Not recorded' },
            { label: 'Posted at', value: formatTimestamp(reel.posted_at) },
            { label: 'Posted by', value: reel.posted_by ?? 'Not recorded' },
            { label: 'External reel id', value: reel.external_reel_id ?? 'Generated only' },
            { label: 'Updated', value: formatTimestamp(reel.updated_at) },
          ]}
        />
        <JsonPanel title="Reel metadata" value={reel.metadata} />
      </SectionCard>

      <SectionCard
        title="Package artifacts"
        description="Package visibility is surfaced directly on the reel so operators can confirm the output set before any publishing workflow."
      >
        {packageDetail ? (
          <div style={{ display: 'grid', gap: 14 }}>
            <MetaGrid
              items={[
                { label: 'Package run', value: relatedRun?.id.slice(0, 8) ?? 'Not linked' },
                { label: 'Package status', value: packageDetail.status },
                {
                  label: 'Manifest artifacts',
                  value: String(packageDetail.manifest_metadata.artifact_count ?? 'Unknown'),
                },
                { label: 'Root uri', value: packageDetail.package_root_uri ?? 'Not recorded' },
              ]}
            />
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
              {relatedRun ? (
                <LinkAction href={runPath(page.org_id, relatedRun.id)} label="Open related run" />
              ) : null}
              <LinkAction
                href={packagePath(page.org_id, packageDetail.run_id)}
                label="Open package detail"
              />
              {packageDetail.manifest_download ? (
                <ExternalAction
                  href={packageDetail.manifest_download.url}
                  label="Download manifest"
                />
              ) : null}
              {packageDetail.provenance_download ? (
                <ExternalAction
                  href={packageDetail.provenance_download.url}
                  label="Download provenance"
                />
              ) : null}
            </div>
            <div style={{ display: 'grid', gap: 12 }}>
              {packageDetail.artifacts.map((artifact) => (
                <article
                  key={artifact.name}
                  style={{
                    display: 'grid',
                    gap: 10,
                    padding: 16,
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
                    <div style={{ fontWeight: 700, color: '#172033' }}>{artifact.name}</div>
                    <StatusBadge status={artifact.kind ?? 'artifact'} />
                  </div>
                  <MetaGrid
                    items={[
                      { label: 'Content type', value: artifact.content_type ?? 'Unknown' },
                      { label: 'Storage uri', value: artifact.storage_uri },
                    ]}
                  />
                  <ExternalAction
                    href={artifact.download.url}
                    label={`Download ${artifact.name}`}
                  />
                </article>
              ))}
            </div>
          </div>
        ) : (
          <p style={{ margin: 0, color: '#55627a' }}>
            No package output is linked to this reel yet. The detail view stays ready for package
            visibility as soon as a process run completes.
          </p>
        )}
      </SectionCard>
    </DetailFrame>
  );
}
