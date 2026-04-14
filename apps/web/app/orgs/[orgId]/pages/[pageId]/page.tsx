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
  params: Promise<{ orgId: string; pageId: string }>;
}) {
  const { orgId, pageId } = await params;
  const detail = await getPageDetail(orgId, pageId);

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
      breadcrumbs={[
        { label: 'Home', href: '/' },
        { label: 'Pages', href: '/pages' },
        { label: page.display_name },
      ]}
      eyebrow={`${page.platform} page`}
      title={page.display_name}
      subtitle="This page explains what this account is, what rules shape it, and where to go next when you want to review recent reels or start new work."
      actions={
        <>
          <StatusBadge status={page.ownership} />
          <LinkAction href="/pages" label="Back to Pages" />
          <LinkAction
            href={`/actions?orgId=${page.org_id}&pageId=${page.id}`}
            label="Open in Actions"
            tone="primary"
          />
        </>
      }
      cues={[
        {
          label: 'What this page is for',
          value: 'Understand the page context before you trigger work or review related content.',
        },
        {
          label: 'What you can do here',
          value: 'See persona and constraints, inspect recent reels, and jump into actions with the correct page ID.',
        },
        {
          label: 'What comes next',
          value: 'Review a reel from this page or move into Actions to start or process work.',
        },
      ]}
    >
      <SectionCard
        title="Page overview"
        description="Use this summary to understand the account before you touch reels, runs, or policy."
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
        description="Start here if you want to understand what is already in flight or review a specific piece of content."
      >
        <div className="cl-stack-md">
          {recentReels.map((reel) =>
            (() => {
              const related = reelRelations.find((candidate) => candidate.reelId === reel.id);

              return (
                <article key={reel.id} className="cl-entity-card">
                  <div className="cl-split">
                    <div>
                      <div className="cl-step-label">{reel.origin}</div>
                      <div className="cl-entity-title">
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
                  <div className="cl-button-row">
                    <LinkAction
                      href={reelPath(page.org_id, page.id, reel.id)}
                      label="Open reel detail"
                    />
                    <LinkAction
                      href={`/actions?orgId=${page.org_id}&pageId=${page.id}&reelId=${reel.id}`}
                      label="Open in Actions"
                      tone="secondary"
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

      <SectionCard
        title="Policy summary"
        description="Page-level guardrails stay visible here so you can judge whether the account is set up safely before you trigger new work."
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
          <p className="cl-panel-description">No page policy is recorded yet for this page.</p>
        )}
      </SectionCard>
    </DetailFrame>
  );
}
