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
  formatTimestamp,
} from '../../../../_components/detail-ui';
import {
  pagePath,
  pageRunsPath,
  reelPath,
  runPath,
} from '../../../../_lib/content-lab-data';
import { loadOperatorPackageDetail } from '../../../../_lib/operator-page-workspace';

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

export default async function PackageDetailPage({
  params,
}: {
  params: Promise<{ orgId: string; runId: string }>;
}) {
  const { orgId, runId } = await params;
  const detail = await loadOperatorPackageDetail(orgId, runId);

  if (detail === null) {
    notFound();
  }

  const { packageDetail, run, page, reel } = detail;

  return (
    <DetailFrame
      breadcrumbs={
        page
          ? [
              { label: 'Home', href: '/' },
              { label: 'Pages', href: '/pages' },
              { label: page.display_name, href: pagePath(packageDetail.org_id, page.id) },
              { label: 'Runs', href: pageRunsPath(packageDetail.org_id, page.id) },
              { label: `Package ${packageDetail.run_id.slice(0, 8)}` },
            ]
          : [
              { label: 'Home', href: '/' },
              { label: 'Pages', href: '/pages' },
              { label: `Package ${packageDetail.run_id.slice(0, 8)}` },
            ]
      }
      eyebrow="Package output"
      title={`Package ${packageDetail.run_id.slice(0, 8)}`}
      subtitle="This package detail stays tied to the owning page and run so handoff checks do not force the operator out into a separate global workflow."
      actions={
        <>
          <StatusBadge status={packageDetail.status} />
          <LinkAction
            href={buildActionPath(packageDetail.org_id, page?.id ?? null, reel?.id ?? null)}
            label="Open in Actions"
            tone="primary"
          />
          <LinkAction href={runPath(packageDetail.org_id, run.id)} label="Open run" />
          {page ? <LinkAction href={pagePath(packageDetail.org_id, page.id)} label="Open page" /> : null}
          {page ? (
            <LinkAction
              href={pageRunsPath(packageDetail.org_id, page.id)}
              label="Back to page runs"
            />
          ) : null}
          {page && reel ? (
            <LinkAction
              href={reelPath(packageDetail.org_id, page.id, reel.id)}
              label="Open reel"
            />
          ) : null}
        </>
      }
      cues={[
        {
          label: 'What this page is for',
          value: 'Confirm what was packaged, where it came from, and what is ready to hand off.',
        },
        {
          label: 'What you can do here',
          value: 'Download artifacts, inspect provenance, and move back to the linked page, run, or reel.',
        },
        {
          label: 'What comes next',
          value: 'After verifying the package, continue review in Queue or record manual posting in Actions.',
        },
      ]}
    >
      <SectionCard
        title="Package summary"
        description="Start here to see which run and reel produced the package and where it lives."
      >
        <MetaGrid
          items={[
            { label: 'Workflow key', value: packageDetail.workflow_key },
            { label: 'Reel id', value: packageDetail.reel_id ?? 'Not recorded' },
            { label: 'Package root', value: packageDetail.package_root_uri ?? 'Not recorded' },
            { label: 'Manifest uri', value: packageDetail.manifest_uri ?? 'Not recorded' },
            { label: 'Created', value: formatTimestamp(packageDetail.created_at) },
            { label: 'Updated', value: formatTimestamp(packageDetail.updated_at) },
          ]}
        />
      </SectionCard>

      <SectionCard
        title="Provenance"
        description="Use provenance and manifest files to confirm audit context before this package is handed off."
      >
        <div className="cl-button-row">
          {packageDetail.manifest_download ? (
            <ExternalAction href={packageDetail.manifest_download.url} label="Download manifest" />
          ) : null}
          {packageDetail.provenance_download ? (
            <ExternalAction
              href={packageDetail.provenance_download.url}
              label="Download provenance"
            />
          ) : null}
        </div>
        <MetaGrid
          items={[
            {
              label: 'Manifest artifacts',
              value: String(packageDetail.manifest_metadata.artifact_count ?? 'Unknown'),
            },
            {
              label: 'Manifest expires',
              value: packageDetail.manifest_download
                ? formatTimestamp(packageDetail.manifest_download.expires_at)
                : 'Unavailable',
            },
            {
              label: 'Provenance expires',
              value: packageDetail.provenance_download
                ? formatTimestamp(packageDetail.provenance_download.expires_at)
                : 'Unavailable',
            },
          ]}
        />
        <JsonPanel title="Manifest metadata" value={packageDetail.manifest_metadata} />
        <JsonPanel title="Provenance payload" value={packageDetail.provenance} />
      </SectionCard>

      <SectionCard
        title="Downloadable artifacts"
        description="These are the publishable or handoff-ready files the operator usually cares about first."
      >
        <div className="cl-stack-md">
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
                  {
                    label: 'Download expires',
                    value: formatTimestamp(artifact.download.expires_at),
                  },
                ]}
              />
              <JsonPanel title="Artifact metadata" value={artifact.metadata} />
              <ExternalAction href={artifact.download.url} label={`Download ${artifact.name}`} />
            </article>
          ))}
        </div>
      </SectionCard>
    </DetailFrame>
  );
}
