import React from 'react';
import { notFound } from 'next/navigation';

import {
  DetailFrame,
  LinkAction,
  MetaGrid,
  SectionCard,
  StatusBadge,
} from '../../../../_components/detail-ui';
import {
  formatShortId,
  getPackageDetail,
  getPageDetail,
  getRelatedRunForReel,
  packagePath,
  reelPath,
  runPath,
} from '../../../../_lib/content-lab-data';

function strongestMode(
  policy: NonNullable<Awaited<ReturnType<typeof getPageDetail>>>['policy'],
): string {
  if (policy === null) {
    return 'No page-specific policy';
  }

  const modes = Object.entries(policy.state.mode_ratios).sort((left, right) => right[1] - left[1]);
  const primary = modes[0];
  return primary ? `${primary[0]} at ${(primary[1] * 100).toFixed(0)}%` : 'Balanced';
}

export default async function PageDetailPage({
  params,
}: {
  params: { orgId: string; pageId: string };
}) {
  const detail = await getPageDetail(params.orgId, params.pageId);

  if (detail === null) {
    notFound();
  }

  const { page, policy, recentReels } = detail;
  const disclosureCount = page.metadata.constraints.required_disclosures.length;
  const reelRelations = await Promise.all(
    recentReels.map(async (reel) => {
      const relatedRun = await getRelatedRunForReel(page.org_id, reel.id);
      const relatedPackage =
        relatedRun === null ? null : await getPackageDetail(page.org_id, relatedRun.id);
      return {
        reelId: reel.id,
        relatedRun,
        relatedPackage,
      };
    }),
  );

  return (
    <DetailFrame
      eyebrow={`${page.platform} page`}
      title={page.display_name}
      subtitle="Page detail keeps policy, persona constraints, and recent reel activity in one org-scoped view."
      actions={<StatusBadge status={page.ownership} />}
    >
      <SectionCard
        title="Policy summary"
        description="Page-level policy stays visible alongside creative constraints so operators can judge risk before triggering new work."
      >
        {policy ? (
          <MetaGrid
            items={[
              { label: 'Policy scope', value: `${policy.scope_type}:${policy.scope_id}` },
              { label: 'Primary mode', value: strongestMode(policy) },
              {
                label: 'Per-run budget',
                value: `$${policy.state.budget.per_run_usd_limit.toFixed(2)}`,
              },
              {
                label: 'Daily budget',
                value: `$${policy.state.budget.daily_usd_limit.toFixed(2)}`,
              },
              {
                label: 'Similarity guardrail',
                value: `${policy.state.thresholds.similarity.warn_at} / ${policy.state.thresholds.similarity.block_at}`,
              },
              {
                label: 'Min QA score',
                value: policy.state.thresholds.min_quality_score.toFixed(2),
              },
            ]}
          />
        ) : (
          <p style={{ margin: 0, color: '#55627a' }}>
            No page policy is recorded yet for this page.
          </p>
        )}
      </SectionCard>

      <SectionCard
        title="Page profile"
        description="The page contract carries persona, CTA posture, disclosures, and operator-safe scoping metadata."
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
            {
              label: 'Required disclosures',
              value: disclosureCount === 0 ? 'None' : disclosureCount,
            },
            {
              label: 'Max script words',
              value: page.metadata.constraints.max_script_words ?? 'Unbounded',
            },
            {
              label: 'Niche',
              value: typeof page.metadata.niche === 'string' ? page.metadata.niche : 'Not recorded',
            },
          ]}
        />
      </SectionCard>

      <SectionCard
        title="Recent reels"
        description="Operators can jump from the page into individual reels, related runs, and published packages without leaving the org namespace."
      >
        <div style={{ display: 'grid', gap: 14 }}>
          {recentReels.map((reel) =>
            (() => {
              const related = reelRelations.find((candidate) => candidate.reelId === reel.id);

              return (
                <article
                  key={reel.id}
                  style={{
                    display: 'grid',
                    gap: 12,
                    padding: 18,
                    borderRadius: 18,
                    border: '1px solid rgba(23, 32, 51, 0.12)',
                    background: 'rgba(255, 255, 255, 0.72)',
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
                        {reel.origin}
                      </div>
                      <div
                        style={{
                          fontSize: 20,
                          fontFamily: 'Georgia, Cambria, "Times New Roman", Times, serif',
                        }}
                      >
                        {reel.variant_label ?? `Observed reel ${formatShortId(reel.id)}`}
                      </div>
                    </div>
                    <StatusBadge status={reel.status} />
                  </div>
                  <MetaGrid
                    items={[
                      { label: 'Reel id', value: formatShortId(reel.id) },
                      { label: 'Family', value: formatShortId(reel.reel_family_id) },
                      {
                        label: 'External reel id',
                        value: reel.external_reel_id ?? 'Generated only',
                      },
                      {
                        label: 'Updated',
                        value: new Date(reel.updated_at).toLocaleString('en-GB'),
                      },
                    ]}
                  />
                  <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                    <LinkAction
                      href={reelPath(page.org_id, page.id, reel.id)}
                      label="Open reel detail"
                    />
                    {related?.relatedRun ? (
                      <LinkAction
                        href={runPath(page.org_id, related.relatedRun.id)}
                        label="Open related run"
                      />
                    ) : null}
                    {related?.relatedPackage ? (
                      <LinkAction
                        href={packagePath(page.org_id, related.relatedPackage.run.id)}
                        label="Open package output"
                      />
                    ) : null}
                  </div>
                </article>
              );
            })(),
          )}
        </div>
      </SectionCard>
    </DetailFrame>
  );
}
