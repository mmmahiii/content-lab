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
import { getPackageDetail, pagePath, reelPath, runPath } from '../../../../_lib/content-lab-data';

export default async function PackageDetailPage({
  params,
}: {
  params: { orgId: string; runId: string };
}) {
  const detail = await getPackageDetail(params.orgId, params.runId);

  if (detail === null) {
    notFound();
  }

  const { packageDetail, run, page, reel } = detail;

  return (
    <DetailFrame
      eyebrow="Package output"
      title={`Package ${packageDetail.run_id.slice(0, 8)}`}
      subtitle="Package detail shows provenance, signed downloads, and the ready-to-post artifact set for a single org-scoped run."
      actions={
        <>
          <StatusBadge status={packageDetail.status} />
          <LinkAction href={runPath(packageDetail.org_id, run.id)} label="Open run" />
          {page ? (
            <LinkAction href={pagePath(packageDetail.org_id, page.id)} label="Open page" />
          ) : null}
          {page && reel ? (
            <LinkAction href={reelPath(packageDetail.org_id, page.id, reel.id)} label="Open reel" />
          ) : null}
        </>
      }
    >
      <SectionCard
        title="Package summary"
        description="Operators can confirm which reel and run produced the package, when it was created, and where it lives in storage."
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
        description="Support artifacts remain separate from the publishable assets so audit and QA data stay visible before any autopost workflow."
      >
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
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
        description="The artifact list stays focused on ready-to-use outputs: video, cover, captions, and posting plan."
      >
        <div style={{ display: 'grid', gap: 14 }}>
          {packageDetail.artifacts.map((artifact) => (
            <article
              key={artifact.name}
              style={{
                display: 'grid',
                gap: 12,
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
                <div
                  style={{
                    fontSize: 20,
                    fontFamily: 'Georgia, Cambria, "Times New Roman", Times, serif',
                  }}
                >
                  {artifact.name}
                </div>
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
