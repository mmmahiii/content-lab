'use client';

import React, { useMemo, useState } from 'react';

import type {
  JsonObject,
  JsonValue,
  PackageDetailOut,
  ProcessReelOperatorDebugOut,
} from '@shared/types';

import { ExternalAction, JsonPanel, LinkAction, MetaGrid, SectionCard } from './detail-ui';
import { packagePath, reelPath, runPath } from '../_lib/content-lab-data';

type TabId = 'overview' | 'brief' | 'scene' | 'prompt' | 'qa' | 'package';

export type CreativeReviewPanelProps = {
  orgId: string;
  pageId: string;
  reelId: string;
  runId: string | null;
  operatorDebug: ProcessReelOperatorDebugOut | null;
  creativePlanning: JsonObject | null;
  packageDetail: PackageDetailOut | null;
};

function asRecord(value: unknown): JsonObject | null {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    return null;
  }
  return value as JsonObject;
}

function verdictTone(verdict: string | null | undefined): string {
  const v = (verdict ?? '').toLowerCase();
  if (v === 'pass' || v === 'skip') {
    return 'is-success';
  }
  if (v === 'fail') {
    return 'is-danger';
  }
  if (v === 'warn') {
    return 'is-warning';
  }
  return '';
}

function formatVerdictLabel(label: string, value: string | null | undefined): string {
  if (!value) {
    return `${label}: not recorded`;
  }
  return `${label}: ${value.replaceAll('_', ' ')}`;
}

const TABS: Array<{ id: TabId; label: string }> = [
  { id: 'overview', label: 'Overview' },
  { id: 'brief', label: 'Brief & script' },
  { id: 'scene', label: 'Scene plan' },
  { id: 'prompt', label: 'Prompt trace' },
  { id: 'qa', label: 'QA' },
  { id: 'package', label: 'Package' },
];

export function CreativeReviewPanel({
  orgId,
  pageId,
  reelId,
  runId,
  operatorDebug,
  creativePlanning,
  packageDetail,
}: CreativeReviewPanelProps) {
  const [tab, setTab] = useState<TabId>('overview');

  const script = useMemo(() => asRecord(creativePlanning?.script), [creativePlanning]);
  const brief = useMemo(() => asRecord(creativePlanning?.brief), [creativePlanning]);
  const semantic = operatorDebug?.qa?.semantic_script ?? null;
  const semanticVerdict = semantic && typeof semantic.verdict === 'string' ? semantic.verdict : null;
  const formatVerdict =
    operatorDebug?.qa?.format && typeof operatorDebug.qa.format.verdict === 'string'
      ? operatorDebug.qa.format.verdict
      : null;
  const findings = useMemo(() => {
    const raw = semantic?.findings;
    if (!Array.isArray(raw)) {
      return [] as JsonObject[];
    }
    return raw.filter((item): item is JsonObject => asRecord(item) !== null);
  }, [semantic]);

  const hasSignal =
    operatorDebug !== null ||
    creativePlanning !== null ||
    (packageDetail !== null &&
      (packageDetail.creative_trace_download !== null ||
        packageDetail.operator_debug !== null));

  if (!hasSignal) {
    return (
      <SectionCard
        title="Creative review"
        description="Once a process-reel run finishes planning and QA, the brief, scene plan, prompts, and semantic findings will appear here."
      >
        <p className="cl-panel-description">
          No creative debug payload is available yet. Trigger processing for this reel, then refresh
          this page.
        </p>
      </SectionCard>
    );
  }

  return (
    <SectionCard
      title="Creative review"
      description="Follow the chain from brief through prompts to QA. Semantic checks can fail even when technical media checks pass—read both before you ship."
      actions={
        <nav className="cl-review-tabs" aria-label="Creative review sections">
          {TABS.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`cl-review-tab${tab === item.id ? ' is-active' : ''}`}
              onClick={() => setTab(item.id)}
            >
              {item.label}
            </button>
          ))}
        </nav>
      }
    >
      {tab === 'overview' ? (
        <div className="cl-stack-md">
          <div className="cl-callout cl-callout--accent">
            <div className="cl-callout-title">What to decide</div>
            <p className="cl-panel-description">
              Use <strong>Technical QA</strong> for media readiness (duration, resolution, repetition).
              Use <strong>Semantic QA</strong> for copy quality (hook strength, filler, CTA balance).
              When they disagree, trust semantic warnings for viewer experience and technical passes for
              delivery constraints.
            </p>
          </div>
          <div className="cl-review-grid">
            <article className="cl-review-card">
              <div className="cl-review-card-title">Technical QA (media &amp; delivery)</div>
              <div className={`cl-verdict-pill ${verdictTone(formatVerdict)}`}>
                {formatVerdictLabel('Format gate', formatVerdict)}
              </div>
              <MetaGrid
                items={[
                  {
                    label: 'Repetition / similarity',
                    value: (() => {
                      const rep = operatorDebug?.qa?.repetition;
                      const verdict =
                        rep && typeof rep.verdict === 'string' ? rep.verdict : null;
                      return verdict ? verdict.replaceAll('_', ' ') : '—';
                    })(),
                  },
                  {
                    label: 'Package QA',
                    value:
                      operatorDebug?.package_qa?.passed === true
                        ? 'Passed'
                        : operatorDebug?.package_qa?.passed === false
                          ? 'Failed'
                          : '—',
                  },
                  {
                    label: 'Run QA (rollup)',
                    value: operatorDebug?.qa?.passed === true ? 'Passed' : operatorDebug?.qa?.passed === false ? 'Failed' : '—',
                  },
                ]}
              />
            </article>
            <article className="cl-review-card">
              <div className="cl-review-card-title">Semantic QA (copy &amp; story)</div>
              <div className={`cl-verdict-pill ${verdictTone(semanticVerdict)}`}>
                {formatVerdictLabel('Semantic verdict', semanticVerdict)}
              </div>
              {semantic && typeof semantic.message === 'string' && semantic.message.trim() ? (
                <p className="cl-panel-description">{semantic.message}</p>
              ) : null}
              {findings.length > 0 ? (
                <ul className="cl-finding-list">
                  {findings.map((finding, index) => {
                    const code = typeof finding.code === 'string' ? finding.code : `finding-${index}`;
                    const outcome =
                      typeof finding.outcome === 'string' ? finding.outcome : 'note';
                    const message =
                      typeof finding.message === 'string'
                        ? finding.message
                        : JSON.stringify(finding as JsonValue);
                    return (
                      <li key={`${code}-${index}`} className="cl-finding-item">
                        <span className={`cl-finding-badge ${verdictTone(outcome)}`}>
                          {outcome.replaceAll('_', ' ')}
                        </span>
                        <span className="cl-finding-code">{code.replaceAll('_', ' ')}</span>
                        <span className="cl-finding-message">{message}</span>
                      </li>
                    );
                  })}
                </ul>
              ) : (
                <p className="cl-panel-description">No semantic findings recorded.</p>
              )}
            </article>
          </div>
          <MetaGrid
            items={[
              {
                label: 'Scene beats',
                value:
                  operatorDebug?.scene_plan_summary?.beat_count !== null &&
                  operatorDebug?.scene_plan_summary?.beat_count !== undefined
                    ? String(operatorDebug.scene_plan_summary.beat_count)
                    : '—',
              },
              {
                label: 'Prompt trace steps',
                value:
                  operatorDebug?.prompt_trace_summary?.step_count !== null &&
                  operatorDebug?.prompt_trace_summary?.step_count !== undefined
                    ? String(operatorDebug.prompt_trace_summary.step_count)
                    : '—',
              },
            ]}
          />
        </div>
      ) : null}

      {tab === 'brief' ? (
        <div className="cl-stack-md">
          {brief ? <JsonPanel title="Brief" value={brief} /> : null}
          {script ? <JsonPanel title="Script payload" value={script} /> : null}
          {!brief && !script ? (
            <p className="cl-panel-description">
              Brief and script outputs are not on this snapshot. Expand debug on the API or open the
              packaged creative trace download.
            </p>
          ) : null}
        </div>
      ) : null}

      {tab === 'scene' ? (
        <div className="cl-stack-md">
          {operatorDebug?.scene_plan_summary ? (
            <MetaGrid
              items={[
                { label: 'Title', value: operatorDebug.scene_plan_summary.title ?? '—' },
                {
                  label: 'Beats',
                  value:
                    operatorDebug.scene_plan_summary.beat_count !== null
                      ? String(operatorDebug.scene_plan_summary.beat_count)
                      : '—',
                },
                {
                  label: 'Duration (s)',
                  value:
                    operatorDebug.scene_plan_summary.duration_seconds !== null
                      ? String(operatorDebug.scene_plan_summary.duration_seconds)
                      : '—',
                },
              ]}
            />
          ) : null}
          {operatorDebug?.scene_plan ? (
            <JsonPanel title="Scene plan" value={operatorDebug.scene_plan} />
          ) : (
            <p className="cl-panel-description">No expanded scene plan is available on this view.</p>
          )}
        </div>
      ) : null}

      {tab === 'prompt' ? (
        <div className="cl-stack-md">
          {operatorDebug?.prompt_trace_summary?.excerpt ? (
            <div className="cl-callout">
              <div className="cl-callout-title">Trace excerpt</div>
              <pre className="cl-pre-inline">{operatorDebug.prompt_trace_summary.excerpt}</pre>
            </div>
          ) : null}
          {operatorDebug?.prompt_trace ? (
            <JsonPanel title="Prompt trace" value={operatorDebug.prompt_trace} />
          ) : (
            <p className="cl-panel-description">No prompt trace payload is available on this view.</p>
          )}
        </div>
      ) : null}

      {tab === 'qa' ? (
        <div className="cl-stack-md">
          {operatorDebug?.qa ? <JsonPanel title="QA rollup" value={operatorDebug.qa} /> : null}
          {operatorDebug?.package_qa ? (
            <JsonPanel title="Package QA" value={operatorDebug.package_qa} />
          ) : null}
          {!operatorDebug?.qa && !operatorDebug?.package_qa ? (
            <p className="cl-panel-description">No QA payload is stored for this snapshot.</p>
          ) : null}
        </div>
      ) : null}

      {tab === 'package' ? (
        <div className="cl-stack-md">
          <div className="cl-button-row">
            {runId ? <LinkAction href={runPath(orgId, runId)} label="Open run detail" /> : null}
            <LinkAction href={reelPath(orgId, pageId, reelId)} label="Open reel detail" />
            {packageDetail ? (
              <LinkAction
                href={packagePath(orgId, packageDetail.run_id)}
                label="Open package workspace"
              />
            ) : null}
          </div>
          {packageDetail?.manifest_download ? (
            <ExternalAction href={packageDetail.manifest_download.url} label="Download manifest" />
          ) : null}
          {packageDetail?.provenance_download ? (
            <ExternalAction
              href={packageDetail.provenance_download.url}
              label="Download provenance"
            />
          ) : null}
          {packageDetail?.creative_trace_download ? (
            <ExternalAction
              href={packageDetail.creative_trace_download.url}
              label="Download creative trace (full JSON)"
            />
          ) : operatorDebug?.creative_trace?.storage_uri ? (
            <p className="cl-panel-description">
              Creative trace object: {operatorDebug.creative_trace.storage_uri}
            </p>
          ) : null}
          {operatorDebug?.creative_trace?.body ? (
            <JsonPanel title="Creative trace (inline)" value={operatorDebug.creative_trace.body} />
          ) : null}
          {packageDetail?.artifacts?.length ? (
            <div className="cl-stack-sm">
              <div className="cl-entity-title">Handoff artifacts</div>
              {packageDetail.artifacts.map((artifact) => (
                <div key={artifact.name} className="cl-split cl-review-artifact-row">
                  <div>{artifact.name}</div>
                  <ExternalAction href={artifact.download.url} label={`Download ${artifact.name}`} />
                </div>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
    </SectionCard>
  );
}
