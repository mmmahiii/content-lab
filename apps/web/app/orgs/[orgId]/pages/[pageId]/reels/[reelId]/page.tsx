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
  packagePath,
  pagePath,
  pageReelsPath,
  runPath,
} from '../../../../../../_lib/content-lab-data';
import { loadOperatorReelDetail } from '../../../../../../_lib/operator-page-workspace';

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
    return 'current';
  }
  if (state === 'complete') {
    return 'complete';
  }
  return 'upcoming';
}

function buildActionPath(orgId: string, pageId: string, reelId: string): string {
  const params = new URLSearchParams({
    orgId,
    pageId,
    reelId,
  });

  return `/actions?${params.toString()}`;
}

export default async function ReelDetailPage({
  params,
}: {
  params: Promise<{ orgId: string; pageId: string; reelId: string }>;
}) {
  const { orgId, pageId, reelId } = await params;
  const detail = await loadOperatorReelDetail(orgId, pageId, reelId);

  if (detail === null) {
    notFound();
  }

  const { page, reel, relatedRun, packageDetail } = detail;
  const timeline = timelineForStatus(reel.origin, reel.status);

  return (
    <DetailFrame
      breadcrumbs={[
        { label: 'Home', href: '/' },
        { label: 'Pages', href: '/pages' },
        { label: page.display_name, href: pagePath(page.org_id, page.id) },
        { label: 'Reels', href: pageReelsPath(page.org_id, page.id) },
        { label: reel.variant_label ?? `Reel ${reel.id.slice(0, 8)}` },
      ]}
      eyebrow={`${reel.origin} reel`}
      title={reel.variant_label ?? `Reel ${reel.id.slice(0, 8)}`}
      subtitle="This reel detail stays anchored to its page workspace so operators can inspect lifecycle, package output, and the next action without losing context."
      actions={
        <>
          <LinkAction href={pageReelsPath(page.org_id, page.id)} label="Back to page reels" />
          <LinkAction
            href={buildActionPath(page.org_id, page.id, reel.id)}
            label="Open in Actions"
            tone="primary"
          />
          <StatusBadge status={reel.status} />
        </>
      }
      cues={[
        {
          label: 'What this page is for',
          value: 'Explain one reel end to end while keeping the page workspace one click away.',
        },
        {
          label: 'What you can do here',
          value: 'Review lifecycle state, audit metadata, inspect the linked run, and download package artifacts.',
        },
        {
          label: 'What comes next',
          value: 'Move back to the page reels tab, or continue into Actions when a human decision is needed.',
        },
      ]}
    >
      <SectionCard
        title="Lifecycle timeline"
        description="Read this top to bottom to understand what has already happened and what state the reel is currently in."
      >
        <div className="cl-stack-sm">
          {timeline.map((item) => (
            <div
              key={item.status}
              className={`cl-step-card${item.state === 'current' ? ' is-current' : ''}`}
            >
              <div className="cl-split">
                <div className="cl-entity-title">{formatStatus(item.status)}</div>
                <div className={`cl-step-state is-${timelineTone(item.state)}`}>{item.state}</div>
              </div>
            </div>
          ))}
        </div>
      </SectionCard>

      <SectionCard
        title="Operator detail"
        description="These fields explain who reviewed or posted the reel and when those human steps happened."
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
        description="Use this section to confirm whether the output set is ready and inspect each downloadable artifact."
      >
        {packageDetail ? (
          <div className="cl-stack-md">
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
            <div className="cl-button-row">
              {relatedRun ? (
                <LinkAction href={runPath(page.org_id, relatedRun.id)} label="Open related run" />
              ) : null}
              <LinkAction href={pagePath(page.org_id, page.id)} label="Open page overview" />
              <LinkAction
                href={buildActionPath(page.org_id, page.id, reel.id)}
                label="Open in Actions"
                tone="secondary"
              />
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
            <div className="cl-stack-sm">
              {packageDetail.artifacts.map((artifact) => (
                <article key={artifact.name} className="cl-artifact-card">
                  <div className="cl-split">
                    <div className="cl-entity-title">{artifact.name}</div>
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
          <p className="cl-panel-description">
            No package output is linked to this reel yet. Return to the page reels tab or Actions if you need to keep work moving.
          </p>
        )}
      </SectionCard>
    </DetailFrame>
  );
}
