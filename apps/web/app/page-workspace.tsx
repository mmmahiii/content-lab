'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import type { FormEvent, ReactNode } from 'react';

import { normalizeOrgId, OPERATOR_ORG_COOKIE } from './_lib/operator-context';

const DEFAULT_ORG_ID =
  process.env.NEXT_PUBLIC_CONTENT_LAB_OPERATOR_ORG_ID ??
  '00000000-0000-4000-8000-000000000001';

type OrgRecord = {
  id: string;
  name: string;
  slug: string;
  created_at: string;
  page_count: number;
};

type PageRecord = {
  id: string;
  platform: string;
  display_name: string;
  external_page_id: string | null;
  handle: string | null;
  ownership: string;
  created_at: string;
  updated_at: string;
};

type PolicyDocument = {
  mode_ratios: {
    exploit: number;
    explore: number;
    mutation: number;
    chaos: number;
  };
  budget: {
    per_run_usd_limit: number;
    daily_usd_limit: number;
    monthly_usd_limit: number;
  };
  thresholds: {
    similarity: {
      warn_at: number;
      block_at: number;
    };
    min_quality_score: number;
  };
};

type PagePolicy = {
  state: PolicyDocument;
  updated_at: string | null;
  is_explicit_override: boolean;
  inherited_from: 'global' | 'default' | null;
};

type RunRecord = {
  id: string;
  workflow_key: string;
  flow_trigger: string;
  status: string;
  input_params: Record<string, unknown>;
  output_payload: Record<string, unknown> | null;
  run_metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

type SignedDownload = {
  url: string;
  storage_uri?: string;
  expires_at?: string;
};

type PackageArtifact = {
  name: string;
  storage_uri: string;
  kind: string | null;
  content_type: string | null;
  metadata?: Record<string, unknown>;
  download?: SignedDownload;
};

type PackageDetail = {
  run_id: string;
  status: string;
  workflow_key: string;
  reel_id: string | null;
  package_root_uri: string | null;
  manifest_uri: string | null;
  manifest_metadata: Record<string, unknown>;
  manifest_download?: SignedDownload | null;
  provenance: Record<string, unknown>;
  provenance_uri: string | null;
  provenance_download?: SignedDownload | null;
  creative_trace_uri: string | null;
  creative_trace_download?: SignedDownload | null;
  timeline_uri: string | null;
  timeline_download?: SignedDownload | null;
  operator_debug?: Record<string, unknown> | null;
  artifacts: PackageArtifact[];
  outbox_notification?: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
  packaged_at?: string | null;
};

type FormState = {
  displayName: string;
  handle: string;
  platform: string;
  ownership: 'owned' | 'competitor';
};

type ArtifactTab =
  | 'video'
  | 'cover'
  | 'captions'
  | 'plan'
  | 'qa'
  | 'runway'
  | 'timeline'
  | 'trace'
  | 'raw';

type WorkspaceWorkbenchTab =
  | 'two_button_reel_path'
  | 'asset_pack_generation'
  | 'live_hook_image_creator';

type AssetLibraryKind = 'background' | 'object' | 'video' | 'hook' | 'audio' | 'final_output';

type AssetLibraryItem = {
  id: string;
  title: string;
  kind: AssetLibraryKind;
  mediaType: string;
  pack: string;
  tags: string[];
  layerSuitability: string;
  reuseCount: number;
  performanceScore: number;
  previewTone: string;
  imageUrl?: string;
  storageUri?: string;
};

type AssetLibraryItemOut = {
  id: string;
  asset_kind: string | null;
  media_type: string | null;
  niche: string | null;
  tags: string[];
  asset_pack_ids: string[];
  has_transparency: boolean | null;
  ready_status: string;
  performance_score: number | null;
  reuse_count: number;
  source: string;
  storage_uri: string;
  download: SignedDownload | null;
  metadata: Record<string, unknown>;
};

type AssetPackPlannerState = {
  name: string;
  totalAssetCount: number;
  backgroundCount: number;
  objectCount: number;
  qualityLevel: 'lean' | 'balanced' | 'premium';
  format: 'proof reel' | 'listicle' | 'product demo' | 'objection handling';
  style: 'clean product' | 'ugc' | 'cinematic' | 'high contrast';
  provider: 'runway';
  model: 'gen4.5';
  ratio: '9:16' | '1:1' | '16:9';
};

type AssetPackRecord = {
  id: string;
  status:
    | 'draft'
    | 'planned'
    | 'approved'
    | 'rejected'
    | 'generating'
    | 'ready'
    | 'failed'
    | 'archived';
  name: string;
  niche: string;
  requested_asset_count?: number;
  asset_mix_requested_json?: Record<string, unknown> | null;
  asset_mix_final_json?: Record<string, unknown> | null;
  strategy_summary?: string | null;
  created_at?: string;
  updated_at?: string;
};

type AssetPackPlanResponse = {
  asset_pack: AssetPackRecord;
  asset_mix: Record<string, number>;
  strategy_summary: string;
  expected_reel_formats?: string[];
  reuse_rationale?: string;
  planning_resolution_summary?: Record<string, number>;
};

type AssetPackRenderResponse = {
  run_id: string;
  task_id: string;
  reel_id: string;
  reel_family_id: string;
  status: string;
  external_ref: string | null;
  accepted_for_rendering: boolean;
};

type CandidateCompositionAsset = {
  asset_id: string;
  asset_kind: string;
  pack_role: string | null;
  title: string | null;
  compatibility: Record<string, unknown>;
  metadata: Record<string, unknown>;
  performance_score: number | null;
  usage_count: number;
};

type CandidateComposition = {
  composition_id: string;
  roles: Record<string, CandidateCompositionAsset>;
  compatibility_score: number;
  diversity_score: number;
  performance_score: number;
  selection_score: number;
  reasons: string[];
  composition_manifest: Record<string, unknown>;
};

type AssetPackCombinationsResponse = {
  asset_pack: AssetPackRecord;
  candidate_compositions: CandidateComposition[];
};

type HookCanvasItem = {
  id: string;
  asset: AssetLibraryItem;
  x: number;
  y: number;
  size: number;
};

type SavedHookImageGeneration = {
  id: string;
  sourceRunId: string | null;
  name: string;
  selectedBackgroundId: string;
  background: AssetLibraryItem;
  items: HookCanvasItem[];
  updatedAt: string;
};

type HookCanvasDragState =
  | {
      itemId: string;
      mode: 'move';
      pointerStartX: number;
      pointerStartY: number;
      itemStartX: number;
      itemStartY: number;
    }
  | {
      itemId: string;
      mode: 'resize';
      pointerStartX: number;
      pointerStartY: number;
      itemStartSize: number;
    };

const emptyForm: FormState = {
  displayName: '',
  handle: '',
  platform: 'instagram',
  ownership: 'owned',
};

const policyLabels = {
  exploit: 'Exploit',
  explore: 'Explore',
  mutation: 'Mutation',
  chaos: 'Chaos',
  per_run_usd_limit: 'Per run',
  daily_usd_limit: 'Daily',
  monthly_usd_limit: 'Monthly',
  warn_at: 'Warn at',
  block_at: 'Block at',
  min_quality_score: 'Min QA',
} as const;

const workflowSteps = [
  { key: 'creative_planning', label: 'Planning' },
  { key: 'asset_resolution', label: 'Asset' },
  { key: 'editing', label: 'Editing' },
  { key: 'qa', label: 'QA' },
  { key: 'packaging', label: 'Packaging' },
];

const assetLibrarySeed: AssetLibraryItem[] = [
  {
    id: 'bg-01',
    title: 'Desk gradient loop',
    kind: 'background',
    mediaType: 'video/mp4',
    pack: 'Launch kit A',
    tags: ['desk', 'clean', 'loop'],
    layerSuitability: 'Backdrop, text-safe center',
    reuseCount: 8,
    performanceScore: 86,
    previewTone: 'linear-gradient(135deg, #213547, #5eead4)',
  },
  {
    id: 'bg-02',
    title: 'Phone scroll plate',
    kind: 'background',
    mediaType: 'image/png',
    pack: 'UGC starters',
    tags: ['phone', 'scroll', 'neutral'],
    layerSuitability: 'Backdrop, subject left',
    reuseCount: 5,
    performanceScore: 79,
    previewTone: 'linear-gradient(135deg, #334155, #f8fafc)',
  },
  {
    id: 'obj-01',
    title: 'Cutout product stack',
    kind: 'object',
    mediaType: 'image/png',
    pack: 'Launch kit A',
    tags: ['transparent', 'product', 'hero'],
    layerSuitability: 'Transparent foreground',
    reuseCount: 11,
    performanceScore: 91,
    previewTone: 'radial-gradient(circle at 50% 40%, #f8fafc 0 18%, #475569 19% 42%, #111827 43%)',
  },
  {
    id: 'obj-02',
    title: 'Creator reaction sticker',
    kind: 'object',
    mediaType: 'image/png',
    pack: 'UGC starters',
    tags: ['transparent', 'face', 'reaction'],
    layerSuitability: 'Overlay, lower third',
    reuseCount: 7,
    performanceScore: 83,
    previewTone: 'radial-gradient(circle at 50% 42%, #fde68a 0 20%, #fb7185 21% 44%, #111827 45%)',
  },
  {
    id: 'vid-01',
    title: 'Before-after swipe',
    kind: 'video',
    mediaType: 'video/mp4',
    pack: 'Proof pack',
    tags: ['before-after', 'proof', 'motion'],
    layerSuitability: 'Primary footage',
    reuseCount: 4,
    performanceScore: 88,
    previewTone: 'linear-gradient(90deg, #0f172a 0 50%, #fbbf24 50%)',
  },
  {
    id: 'hook-01',
    title: 'Stop doing this first',
    kind: 'hook',
    mediaType: 'text',
    pack: 'Hook bank',
    tags: ['problem', 'fast-open', 'educational'],
    layerSuitability: 'Opening caption',
    reuseCount: 16,
    performanceScore: 94,
    previewTone: 'linear-gradient(135deg, #0f172a, #7c3aed)',
  },
  {
    id: 'hook-02',
    title: 'Three signs it is working',
    kind: 'hook',
    mediaType: 'text',
    pack: 'Hook bank',
    tags: ['listicle', 'proof', 'retention'],
    layerSuitability: 'Opening caption',
    reuseCount: 9,
    performanceScore: 84,
    previewTone: 'linear-gradient(135deg, #064e3b, #22c55e)',
  },
  {
    id: 'aud-01',
    title: 'Tight soft pulse',
    kind: 'audio',
    mediaType: 'audio/wav',
    pack: 'Audio bed 01',
    tags: ['pulse', 'soft', 'loop'],
    layerSuitability: 'Bed under voiceover',
    reuseCount: 6,
    performanceScore: 78,
    previewTone: 'repeating-linear-gradient(90deg, #5eead4 0 8px, #0f172a 8px 16px)',
  },
  {
    id: 'out-01',
    title: 'Founder proof reel',
    kind: 'final_output',
    mediaType: 'video/mp4',
    pack: 'Published winners',
    tags: ['final', 'proof', 'winner'],
    layerSuitability: 'Reference output',
    reuseCount: 3,
    performanceScore: 92,
    previewTone: 'linear-gradient(135deg, #111827, #e2e8f0 50%, #5eead4)',
  },
];

function normalizeHandle(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }
  return trimmed.startsWith('@') ? trimmed : `@${trimmed}`;
}

function clonePolicy(policy: PolicyDocument): PolicyDocument {
  return {
    mode_ratios: { ...policy.mode_ratios },
    budget: { ...policy.budget },
    thresholds: {
      similarity: { ...policy.thresholds.similarity },
      min_quality_score: policy.thresholds.min_quality_score,
    },
  };
}

function formatPolicySource(policy: PagePolicy | null): string {
  if (!policy) {
    return 'Loading policy';
  }
  if (policy.is_explicit_override) {
    return 'Page override';
  }
  return policy.inherited_from === 'global' ? 'Global policy' : 'Default guardrails';
}

function validatePolicy(policy: PolicyDocument): string | null {
  const ratios = Object.values(policy.mode_ratios);
  const ratioTotal = ratios.reduce((sum, value) => sum + value, 0);
  if (ratios.some((value) => value < 0 || value > 1 || !Number.isFinite(value))) {
    return 'Every mode ratio must be between 0 and 1.';
  }
  if (Math.abs(ratioTotal - 1) > 0.001) {
    return 'Mode ratios must add up to 1.00.';
  }
  if (policy.budget.per_run_usd_limit > policy.budget.daily_usd_limit) {
    return 'Per-run budget must not exceed daily budget.';
  }
  if (policy.budget.daily_usd_limit > policy.budget.monthly_usd_limit) {
    return 'Daily budget must not exceed monthly budget.';
  }
  if (policy.thresholds.similarity.warn_at >= policy.thresholds.similarity.block_at) {
    return 'Similarity warning must be lower than the block threshold.';
  }
  return null;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function textValue(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null;
}

function activeOrgId(): string {
  if (typeof document !== 'undefined') {
    const cookie = document.cookie
      .split(';')
      .map((item) => item.trim())
      .find((item) => item.startsWith(`${OPERATOR_ORG_COOKIE}=`));
    const cookieValue = cookie ? decodeURIComponent(cookie.split('=', 2)[1] ?? '') : null;
    const normalizedCookie = normalizeOrgId(cookieValue);
    if (normalizedCookie) {
      return normalizedCookie;
    }
  }
  return normalizeOrgId(DEFAULT_ORG_ID) ?? '00000000-0000-4000-8000-000000000001';
}

function numericValue(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function stringList(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.map((item) => String(item)).filter(Boolean);
  }
  if (typeof value === 'string') {
    return value
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean);
  }
  return [];
}

function workflowStage(run: RunRecord): string {
  const client = asRecord(run.run_metadata.client);
  if (client && typeof client.workflow_stage === 'string') {
    return client.workflow_stage;
  }
  const stage = run.input_params.workflow_stage;
  return typeof stage === 'string' ? stage : run.workflow_key;
}

function generationMode(run: RunRecord | null): string | null {
  const mode = run?.input_params?.generation_mode;
  return typeof mode === 'string' ? mode : null;
}

function packagePlanRunId(run: RunRecord): string | null {
  const planRunId = run.input_params.plan_run_id;
  return typeof planRunId === 'string' ? planRunId : null;
}

function planRecord(run: RunRecord | null): Record<string, unknown> | null {
  return asRecord(run?.output_payload?.plan);
}

function planTitle(run: RunRecord | null): string {
  const plan = planRecord(run);
  const title = textValue(plan?.title);
  return title ?? (run ? `Plan ${run.id.slice(0, 8)}` : 'No plan');
}

function planBeats(plan: Record<string, unknown> | null): Record<string, unknown>[] {
  const beats = plan?.beats;
  return Array.isArray(beats) ? beats.map(asRecord).filter((beat) => beat !== null) : [];
}

function isIdeaPlan(run: RunRecord): boolean {
  return workflowStage(run) === 'idea_plan';
}

function isPlanUsed(run: RunRecord): boolean {
  return Boolean(run.output_payload?.used_in_package_run_id);
}

function isPlanAvailable(run: RunRecord): boolean {
  return isIdeaPlan(run) && run.status !== 'cancelled' && !isPlanUsed(run);
}

function isPackageGenerationRun(run: RunRecord): boolean {
  return workflowStage(run) === 'package_generation';
}

function isAssetCompositionRun(run: RunRecord): boolean {
  return workflowStage(run) === 'asset_composition_render';
}

function isGeneratedOutputRun(run: RunRecord): boolean {
  return isPackageGenerationRun(run) || isAssetCompositionRun(run);
}

function artifactIsAvailable(artifact: PackageArtifact | null): boolean {
  if (!artifact) {
    return false;
  }
  if (artifact.metadata?.available === false) {
    return false;
  }
  return Boolean(artifact.download?.url);
}

function artifactByName(
  packageDetail: PackageDetail | null,
  names: string[],
): PackageArtifact | null {
  if (!packageDetail) {
    return null;
  }
  const normalized = names.map((name) => name.toLowerCase());
  return (
    packageDetail.artifacts.find((artifact) => normalized.includes(artifact.name.toLowerCase())) ??
    null
  );
}

function runErrorMessage(run: RunRecord | null): string | null {
  const output = run?.output_payload;
  const direct = textValue(output?.error);
  if (direct) {
    return direct;
  }
  const packageQa = asRecord(output?.package_qa);
  return textValue(packageQa?.message);
}

function statusTone(status: string | null | undefined): string {
  if (status === 'succeeded') {
    return 'is-good';
  }
  if (status === 'failed' || status === 'cancelled') {
    return 'is-bad';
  }
  if (status === 'running' || status === 'queued') {
    return 'is-live';
  }
  return 'is-muted';
}

function formatDate(value: string | null | undefined): string {
  if (!value) {
    return 'Not set';
  }
  return new Date(value).toLocaleString();
}

function formatJson(value: unknown): string {
  return JSON.stringify(value ?? {}, null, 2);
}

function parseArtifactText(value: string): unknown {
  if (!value.trim()) {
    return null;
  }
  try {
    return JSON.parse(value);
  } catch {
    return value;
  }
}

function humanizeKey(value: string): string {
  return value
    .replace(/[_-]+/g, ' ')
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/^./, (letter) => letter.toUpperCase());
}

function scalarText(value: unknown): string {
  if (value === null || value === undefined) {
    return 'Not recorded';
  }
  if (typeof value === 'boolean') {
    return value ? 'Yes' : 'No';
  }
  if (typeof value === 'number') {
    return Number.isFinite(value) ? String(value) : 'Not recorded';
  }
  return String(value);
}

async function apiErrorMessage(response: Response): Promise<string> {
  const text = await response.text();
  if (!text.trim()) {
    return `Request failed with ${response.status}`;
  }
  try {
    const parsed = JSON.parse(text) as { detail?: unknown; error?: unknown };
    const detail = parsed.detail ?? parsed.error;
    if (typeof detail === 'string') {
      return detail;
    }
    if (Array.isArray(detail)) {
      return detail
        .map((item) => {
          if (typeof item === 'string') {
            return item;
          }
          if (item && typeof item === 'object' && 'msg' in item) {
            return String((item as { msg: unknown }).msg);
          }
          return JSON.stringify(item);
        })
        .join('; ');
    }
  } catch {
    return text;
  }
  return text;
}

function artifactSummary(value: unknown): string | null {
  if (value === null || value === undefined) {
    return 'Not recorded';
  }
  if (Array.isArray(value)) {
    return `${value.length} item${value.length === 1 ? '' : 's'}`;
  }
  if (typeof value === 'object') {
    const count = Object.keys(value).length;
    return `${count} field${count === 1 ? '' : 's'}`;
  }
  return null;
}

function stepOutput(run: RunRecord | null, step: string): Record<string, unknown> | null {
  return asRecord(asRecord(run?.output_payload?.step_outputs)?.[step]);
}

function localDownload(path: unknown): SignedDownload | null {
  const normalized = textValue(path);
  return normalized ? { url: `/api/local-artifact?path=${encodeURIComponent(normalized)}` } : null;
}

function localArtifact({
  name,
  path,
  contentType,
}: {
  name: string;
  path: unknown;
  contentType: string;
}): PackageArtifact | null {
  const download = localDownload(path);
  if (!download) {
    return null;
  }
  return {
    name,
    storage_uri: textValue(path) ?? '',
    kind: 'local_run_output',
    content_type: contentType,
    metadata: { available: true, source: 'qa_failed_run_output' },
    download,
  };
}

function fallbackArtifactForTab(run: RunRecord | null, tab: ArtifactTab): PackageArtifact | null {
  const editing = stepOutput(run, 'editing');
  if (tab === 'video') {
    return localArtifact({
      name: 'qa_failed_final_video',
      path: editing?.final_video_path,
      contentType: 'video/mp4',
    });
  }
  if (tab === 'cover') {
    return localArtifact({
      name: 'qa_failed_cover',
      path: editing?.cover_path,
      contentType: 'image/png',
    });
  }
  return null;
}

function availableArtifactTabs(
  packageDetail: PackageDetail | null,
  run: RunRecord | null,
): ArtifactTab[] {
  const tabs: ArtifactTab[] = [];
  if (artifactByName(packageDetail, ['final_video']) || fallbackArtifactForTab(run, 'video')) {
    tabs.push('video');
  }
  if (artifactByName(packageDetail, ['cover']) || fallbackArtifactForTab(run, 'cover')) {
    tabs.push('cover');
  }
  if (artifactByName(packageDetail, ['caption_variants'])) {
    tabs.push('captions');
  }
  if (artifactByName(packageDetail, ['posting_plan'])) {
    tabs.push('plan');
  }
  if (stepOutput(run, 'qa')) {
    tabs.push('qa');
  }
  if (generationMode(run) === 'runway' || stepOutput(run, 'asset_resolution')) {
    tabs.push('runway');
  }
  if (
    artifactByName(packageDetail, ['timeline']) ||
    packageDetail?.timeline_download ||
    fallbackArtifactForTab(run, 'timeline')
  ) {
    tabs.push('timeline');
  }
  if (
    artifactByName(packageDetail, ['creative_trace']) ||
    packageDetail?.creative_trace_download ||
    fallbackArtifactForTab(run, 'trace')
  ) {
    tabs.push('trace');
  }
  if (packageDetail || run?.output_payload) {
    tabs.push('raw');
  }
  return tabs;
}

function tabLabel(tab: ArtifactTab): string {
  const labels: Record<ArtifactTab, string> = {
    video: 'Video',
    cover: 'Cover',
    captions: 'Captions',
    plan: 'Plan',
    qa: 'QA',
    runway: 'Runway',
    timeline: 'Timeline',
    trace: 'Trace',
    raw: 'Raw',
  };
  return labels[tab];
}

function artifactForTab(
  packageDetail: PackageDetail | null,
  tab: ArtifactTab,
): PackageArtifact | null {
  if (tab === 'video') {
    return artifactByName(packageDetail, ['final_video']);
  }
  if (tab === 'cover') {
    return artifactByName(packageDetail, ['cover']);
  }
  if (tab === 'captions') {
    return artifactByName(packageDetail, ['caption_variants']);
  }
  if (tab === 'plan') {
    return artifactByName(packageDetail, ['posting_plan']);
  }
  if (tab === 'timeline') {
    return artifactByName(packageDetail, ['timeline']);
  }
  if (tab === 'trace') {
    return artifactByName(packageDetail, ['creative_trace']);
  }
  return null;
}

function extraDownloadForTab(
  packageDetail: PackageDetail | null,
  tab: ArtifactTab,
): SignedDownload | null {
  if (!packageDetail) {
    return null;
  }
  if (tab === 'timeline') {
    return packageDetail.timeline_download ?? null;
  }
  if (tab === 'trace') {
    return packageDetail.creative_trace_download ?? null;
  }
  return null;
}

function firstFailureMessages(
  packageDetail: PackageDetail | null,
  run: RunRecord | null,
): string[] {
  const messages = new Set<string>();
  const runError = runErrorMessage(run);
  if (runError) {
    messages.add(runError);
  }
  const debug = asRecord(packageDetail?.operator_debug);
  const qa = asRecord(debug?.qa);
  const failures = qa?.failure_messages;
  if (Array.isArray(failures)) {
    failures.forEach((item) => {
      if (typeof item === 'string' && item.trim()) {
        messages.add(item);
      }
    });
  }
  const findings = qa?.structured_findings;
  if (Array.isArray(findings)) {
    findings.forEach((item) => {
      const finding = asRecord(item);
      const passed = finding?.passed;
      const message = textValue(finding?.message);
      if (passed === false && message) {
        messages.add(message);
      }
    });
  }
  const runQa = stepOutput(run, 'qa');
  const checks = runQa?.checks;
  if (Array.isArray(checks)) {
    checks.forEach((item) => {
      const check = asRecord(item);
      const passed = check?.passed;
      const message = textValue(check?.message);
      if (passed === false && message) {
        messages.add(message);
      }
    });
  }
  const mediaSync = asRecord(runQa?.media_sync);
  const mediaSyncMessage = textValue(mediaSync?.message);
  if (mediaSyncMessage) {
    messages.add(mediaSyncMessage);
  }
  return Array.from(messages).slice(0, 4);
}

function runwayUsageSummary(run: RunRecord | null): {
  rows: string[];
  raw: Record<string, unknown> | null;
} {
  const asset = stepOutput(run, 'asset_resolution');
  const generation = asRecord(asset?.generation);
  const providerJob = asRecord(asset?.provider_job) ?? asRecord(generation?.provider_job);
  const download = asRecord(generation?.download);
  const params = asRecord(generation?.canonical_params);
  const rows = [
    `API mode: ${textValue(run?.input_params.runway_api_mode) ?? 'unknown'}`,
    `Runway called: ${providerJob ? 'yes' : 'not confirmed'}`,
    `Provider status: ${textValue(providerJob?.status) ?? textValue(generation?.status) ?? 'unknown'}`,
    `Provider job: ${textValue(providerJob?.external_ref) ?? 'not recorded'}`,
    `Model: ${textValue(params?.model) ?? 'unknown'}`,
    `Duration: ${params?.duration_seconds ?? 'unknown'}s`,
    `Downloaded bytes: ${download?.size_bytes ?? 'unknown'}`,
    'Credits used: not returned by the current Runway/provider payload.',
  ];
  return { rows, raw: asset };
}

function runTextForTab(run: RunRecord | null, tab: ArtifactTab): string | null {
  if (tab === 'qa') {
    return formatJson(stepOutput(run, 'qa'));
  }
  if (tab === 'runway') {
    const summary = runwayUsageSummary(run);
    return `${summary.rows.join('\n')}\n\n${formatJson(summary.raw)}`;
  }
  if (tab === 'timeline') {
    return formatJson(stepOutput(run, 'editing')?.timeline);
  }
  if (tab === 'trace') {
    return formatJson(stepOutput(run, 'editing')?.timeline_render_trace);
  }
  if (tab === 'raw') {
    return formatJson(run?.output_payload ?? run);
  }
  return null;
}

function hookImageStorageKey(orgId: string, pageId: string): string {
  return `content-lab:hook-images:${orgId}:${pageId}`;
}

function readSavedHookGenerations(orgId: string, pageId: string): SavedHookImageGeneration[] {
  if (typeof window === 'undefined') {
    return [];
  }
  try {
    const parsed = JSON.parse(
      window.localStorage.getItem(hookImageStorageKey(orgId, pageId)) ?? '[]',
    );
    return Array.isArray(parsed)
      ? parsed.map(asSavedHookGeneration).filter((item) => item !== null)
      : [];
  } catch {
    return [];
  }
}

function asSavedHookGeneration(value: unknown): SavedHookImageGeneration | null {
  const record = asRecord(value);
  if (!record) {
    return null;
  }
  const id = textValue(record.id);
  const name = textValue(record.name);
  const background = asAssetLibraryItem(record.background);
  if (!id || !name || !background) {
    return null;
  }
  const items = Array.isArray(record.items)
    ? record.items.map(asHookCanvasItem).filter((item) => item !== null)
    : [];
  return {
    id,
    sourceRunId: textValue(record.sourceRunId),
    name,
    selectedBackgroundId: textValue(record.selectedBackgroundId) ?? background.id,
    background,
    items,
    updatedAt: textValue(record.updatedAt) ?? new Date().toISOString(),
  };
}

function asHookCanvasItem(value: unknown): HookCanvasItem | null {
  const record = asRecord(value);
  const asset = asAssetLibraryItem(record?.asset);
  const id = textValue(record?.id);
  const x = numericValue(record?.x);
  const y = numericValue(record?.y);
  const size = numericValue(record?.size);
  if (!record || !asset || !id || x === null || y === null || size === null) {
    return null;
  }
  return { id, asset, x, y, size };
}

function asAssetLibraryItem(value: unknown): AssetLibraryItem | null {
  const record = asRecord(value);
  const id = textValue(record?.id);
  const title = textValue(record?.title);
  const kind = textValue(record?.kind);
  if (
    !record ||
    !id ||
    !title ||
    !kind ||
    !['background', 'object', 'video', 'hook', 'audio', 'final_output'].includes(kind)
  ) {
    return null;
  }
  return {
    id,
    title,
    kind: kind as AssetLibraryKind,
    mediaType: textValue(record.mediaType) ?? 'asset',
    pack: textValue(record.pack) ?? 'Saved generation',
    tags: stringList(record.tags),
    layerSuitability: textValue(record.layerSuitability) ?? 'Saved layer',
    reuseCount: numericValue(record.reuseCount) ?? 0,
    performanceScore: numericValue(record.performanceScore) ?? 75,
    previewTone: textValue(record.previewTone) ?? previewToneForAsset(id, kind, title),
    imageUrl: textValue(record.imageUrl) ?? undefined,
    storageUri: textValue(record.storageUri) ?? undefined,
  };
}

function saveHookGenerationsToStorage(
  orgId: string,
  pageId: string,
  generations: SavedHookImageGeneration[],
) {
  if (typeof window === 'undefined') {
    return;
  }
  window.localStorage.setItem(hookImageStorageKey(orgId, pageId), JSON.stringify(generations));
}

function upsertHookGeneration(
  generations: SavedHookImageGeneration[],
  nextGeneration: SavedHookImageGeneration,
): SavedHookImageGeneration[] {
  const withoutCurrent = generations.filter((generation) => generation.id !== nextGeneration.id);
  return [nextGeneration, ...withoutCurrent].sort((left, right) =>
    right.updatedAt.localeCompare(left.updatedAt),
  );
}

function stepStatus(run: RunRecord | null, stepKey: string): string {
  const statuses = asRecord(run?.output_payload?.task_statuses);
  const value = statuses?.[stepKey];
  return typeof value === 'string' ? value : run?.status === 'succeeded' ? 'succeeded' : 'pending';
}

export function PageWorkspace() {
  const [orgs, setOrgs] = useState<OrgRecord[]>([]);
  const [selectedOrgId, setSelectedOrgId] = useState<string>(DEFAULT_ORG_ID);
  const [pages, setPages] = useState<PageRecord[]>([]);
  const [selectedPageId, setSelectedPageId] = useState<string>('');
  const [form, setForm] = useState<FormState>(emptyForm);
  const [policy, setPolicy] = useState<PagePolicy | null>(null);
  const [policyDraft, setPolicyDraft] = useState<PolicyDocument | null>(null);
  const [runs, setRuns] = useState<RunRecord[]>([]);
  const [selectedPlanRunId, setSelectedPlanRunId] = useState<string>('');
  const [selectedPackageRunId, setSelectedPackageRunId] = useState<string>('');
  const [selectedCompositionRunId, setSelectedCompositionRunId] = useState<string>('');
  const [packageDetail, setPackageDetail] = useState<PackageDetail | null>(null);
  const [packageNotice, setPackageNotice] = useState('');
  const [pageLoadError, setPageLoadError] = useState<string | null>(null);
  const [artifactTab, setArtifactTab] = useState<ArtifactTab>('video');
  const [workbenchTab, setWorkbenchTab] = useState<WorkspaceWorkbenchTab>('two_button_reel_path');
  const [artifactText, setArtifactText] = useState('');
  const [artifactTextStatus, setArtifactTextStatus] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [isPolicySaving, setIsPolicySaving] = useState(false);
  const [isWorkflowSaving, setIsWorkflowSaving] = useState(false);
  const [isPolicyOpen, setIsPolicyOpen] = useState(false);
  const [message, setMessage] = useState('Loading saved pages...');
  const [savedHookGenerations, setSavedHookGenerations] = useState<SavedHookImageGeneration[]>([]);
  const selectedPackageRunRef = useRef<RunRecord | null>(null);

  const selectedPage = useMemo(
    () => pages.find((page) => page.id === selectedPageId) ?? pages[0] ?? null,
    [pages, selectedPageId],
  );
  const planRuns = useMemo(() => runs.filter(isPlanAvailable), [runs]);
  const selectedPlan = useMemo(
    () => planRuns.find((run) => run.id === selectedPlanRunId) ?? planRuns[0] ?? null,
    [planRuns, selectedPlanRunId],
  );
  const packageGenerationRuns = useMemo(() => runs.filter(isPackageGenerationRun), [runs]);
  const assetCompositionRuns = useMemo(() => runs.filter(isAssetCompositionRun), [runs]);
  const selectedPackageRun = useMemo(
    () =>
      packageGenerationRuns.find((run) => run.id === selectedPackageRunId) ??
      packageGenerationRuns[0] ??
      null,
    [packageGenerationRuns, selectedPackageRunId],
  );
  const selectedCompositionRun = useMemo(
    () =>
      assetCompositionRuns.find((run) => run.id === selectedCompositionRunId) ??
      assetCompositionRuns[0] ??
      null,
    [assetCompositionRuns, selectedCompositionRunId],
  );
  const activeOutputRun =
    workbenchTab === 'asset_pack_generation' ? selectedCompositionRun : selectedPackageRun;
  selectedPackageRunRef.current = activeOutputRun;
  const selectedPackageRunLoadKey = activeOutputRun
    ? `${activeOutputRun.id}:${activeOutputRun.status}`
    : '';
  const selectedPackagePlan = useMemo(() => {
    const planRunId = selectedPackageRun ? packagePlanRunId(selectedPackageRun) : null;
    return planRunId ? (runs.find((run) => run.id === planRunId) ?? null) : null;
  }, [runs, selectedPackageRun]);
  const selectedPlanPayload = planRecord(selectedPlan);
  const selectedPackagePlanPayload = planRecord(selectedPackagePlan);
  const selectedArtifact =
    artifactForTab(packageDetail, artifactTab) ??
    fallbackArtifactForTab(activeOutputRun, artifactTab);
  const selectedDownload =
    selectedArtifact?.download ?? extraDownloadForTab(packageDetail, artifactTab);
  const artifactTabs = availableArtifactTabs(packageDetail, activeOutputRun);
  const failureMessages = firstFailureMessages(packageDetail, activeOutputRun);
  const hasActiveGeneration = runs.some((run) =>
    isGeneratedOutputRun(run) && ['queued', 'running'].includes(run.status),
  );
  const selectedOrg = useMemo(
    () => orgs.find((org) => org.id === selectedOrgId) ?? null,
    [orgs, selectedOrgId],
  );

  async function saveOperatorOrg(orgId: string) {
    await fetch('/api/operator-context', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ orgId }),
    }).catch(() => undefined);
  }

  function handleOrgChange(orgId: string) {
    setSelectedOrgId(orgId);
    void saveOperatorOrg(orgId);
  }

  async function loadOrgs() {
    try {
      const response = await fetch('/api/orgs', { cache: 'no-store' });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const nextOrgs = (await response.json()) as OrgRecord[];
      setOrgs(nextOrgs);
      setSelectedOrgId((current) => {
        if (nextOrgs.some((org) => org.id === current)) {
          return current;
        }
        return nextOrgs[0]?.id ?? current;
      });
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not load orgs.');
    }
  }

  async function loadPages() {
    setIsLoading(true);
    try {
      const response = await fetch(`/api/orgs/${activeOrgId()}/pages`, { cache: 'no-store' });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const nextPages = (await response.json()) as PageRecord[];
      setPageLoadError(null);
      setPages(nextPages);
      setSelectedPageId((current) => {
        if (current && nextPages.some((page) => page.id === current)) {
          return current;
        }
        return nextPages[0]?.id ?? '';
      });
      setMessage(nextPages.length ? 'Pages loaded.' : 'Create a page to start.');
    } catch (error) {
      const nextError = error instanceof Error ? error.message : 'Could not load pages.';
      setPageLoadError(nextError);
      setMessage(nextError);
    } finally {
      setIsLoading(false);
    }
  }

  async function loadPolicy(pageId: string) {
    setPolicy(null);
    setPolicyDraft(null);
    try {
      const response = await fetch(`/api/orgs/${activeOrgId()}/policy/page/${pageId}`, {
        cache: 'no-store',
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const nextPolicy = (await response.json()) as PagePolicy;
      setPolicy(nextPolicy);
      setPolicyDraft(clonePolicy(nextPolicy.state));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not load page policy.');
    }
  }

  async function loadRuns(pageId: string) {
    try {
      const response = await fetch(`/api/orgs/${activeOrgId()}/pages/${pageId}/runs`, {
        cache: 'no-store',
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const nextRuns = (await response.json()) as RunRecord[];
      const nextPlanRuns = nextRuns.filter(isPlanAvailable);
      const nextPackageRuns = nextRuns.filter(isPackageGenerationRun);
      const nextCompositionRuns = nextRuns.filter(isAssetCompositionRun);
      setRuns(nextRuns);
      setSelectedPlanRunId((current) => {
        if (current && nextPlanRuns.some((run) => run.id === current)) {
          return current;
        }
        return nextPlanRuns[0]?.id ?? '';
      });
      setSelectedPackageRunId((current) => {
        if (current && nextPackageRuns.some((run) => run.id === current)) {
          return current;
        }
        return nextPackageRuns[0]?.id ?? '';
      });
      setSelectedCompositionRunId((current) => {
        if (current && nextCompositionRuns.some((run) => run.id === current)) {
          return current;
        }
        return nextCompositionRuns[0]?.id ?? '';
      });
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not load workflow queue.');
    }
  }

  async function loadPackage(run: RunRecord) {
    setPackageNotice('');
    try {
      const response = await fetch(`/api/orgs/${activeOrgId()}/packages/${run.id}`, { cache: 'no-store' });
      if (!response.ok) {
        if (response.status === 404) {
          setPackageDetail((current) => (current?.run_id === run.id ? current : null));
          setPackageNotice(
            run.status === 'failed' ? 'Artifacts not written.' : 'Package still running.',
          );
          return;
        }
        throw new Error(await response.text());
      }
      setPackageDetail((await response.json()) as PackageDetail);
      setPackageNotice('');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not load generated package.');
      setPackageNotice('Could not load package output.');
    }
  }

  useEffect(() => {
    void loadOrgs();
  }, []);

  useEffect(() => {
    setPages([]);
    setSelectedPageId('');
    setPolicy(null);
    setPolicyDraft(null);
    setRuns([]);
    setSelectedPlanRunId('');
    setSelectedPackageRunId('');
    setSelectedCompositionRunId('');
    setPackageDetail(null);
    setPackageNotice('');
    setMessage('Loading saved pages...');
    void loadPages();
  }, [selectedOrgId]);

  useEffect(() => {
    if (selectedPage?.id) {
      setSavedHookGenerations(readSavedHookGenerations(selectedOrgId, selectedPage.id));
      void loadPolicy(selectedPage.id);
      void loadRuns(selectedPage.id);
    } else {
      setPolicy(null);
      setPolicyDraft(null);
      setRuns([]);
      setSelectedPlanRunId('');
      setSelectedPackageRunId('');
      setSelectedCompositionRunId('');
      setPackageDetail(null);
      setPackageNotice('');
      setSavedHookGenerations([]);
    }
  }, [selectedOrgId, selectedPage?.id]);

  function persistHookGeneration(nextGeneration: SavedHookImageGeneration) {
    if (!selectedPage) {
      return;
    }
    setSavedHookGenerations((current) => {
      const nextGenerations = upsertHookGeneration(current, nextGeneration);
      saveHookGenerationsToStorage(selectedOrgId, selectedPage.id, nextGenerations);
      return nextGenerations;
    });
  }

  useEffect(() => {
    const run = selectedPackageRunRef.current;
    if (run) {
      void loadPackage(run);
    } else {
      setPackageDetail(null);
      setPackageNotice('');
    }
  }, [selectedOrgId, selectedPackageRunLoadKey]);

  useEffect(() => {
    if (!selectedPage?.id) {
      return undefined;
    }
    const intervalId = window.setInterval(
      () => {
        void loadRuns(selectedPage.id);
      },
      hasActiveGeneration ? 2500 : 4000,
    );
    return () => window.clearInterval(intervalId);
  }, [selectedOrgId, selectedPage?.id, hasActiveGeneration]);

  useEffect(() => {
    const tabs = availableArtifactTabs(packageDetail, selectedPackageRunRef.current);
    if (!packageDetail && !selectedPackageRunRef.current) {
      return;
    }
    if (!tabs.includes(artifactTab)) {
      setArtifactTab(tabs[0] ?? 'raw');
    }
  }, [artifactTab, packageDetail]);

  useEffect(() => {
    setArtifactText('');
    setArtifactTextStatus('');
    const run = selectedPackageRunRef.current;
    if ((!packageDetail && !run) || artifactTab === 'video' || artifactTab === 'cover') {
      return;
    }
    if (artifactTab === 'raw') {
      setArtifactText(formatJson(packageDetail ?? run?.output_payload ?? run));
      return;
    }
    const url = selectedDownload?.url;
    const runText = runTextForTab(run, artifactTab);
    if (!url && runText) {
      setArtifactText(runText);
      return;
    }
    if (!url) {
      setArtifactTextStatus('No downloadable artifact for this view.');
      return;
    }
    const controller = new AbortController();
    setArtifactTextStatus('Loading artifact...');
    fetch(`/api/artifact-proxy?url=${encodeURIComponent(url)}`, {
      cache: 'no-store',
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`Artifact returned ${response.status}`);
        }
        const contentType = response.headers.get('content-type') ?? '';
        if (contentType.includes('json')) {
          const body = await response.json();
          return formatJson(body);
        }
        return response.text();
      })
      .then((text) => {
        setArtifactText(text);
        setArtifactTextStatus('');
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === 'AbortError') {
          return;
        }
        setArtifactTextStatus(error instanceof Error ? error.message : 'Could not load artifact.');
      });
    return () => controller.abort();
  }, [artifactTab, packageDetail, selectedDownload?.url]);

  async function createPage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSaving(true);
    setMessage('Creating page...');
    try {
      const displayName = form.displayName.trim();
      if (!displayName) {
        throw new Error('Page name is required.');
      }
      const handle = normalizeHandle(form.handle);
      const response = await fetch(`/api/orgs/${activeOrgId()}/pages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          platform: form.platform,
          display_name: displayName,
          external_page_id: handle ? `${form.platform}-${handle.replace('@', '')}` : null,
          handle,
          ownership: form.ownership,
          metadata: {},
        }),
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const created = (await response.json()) as PageRecord;
      setForm(emptyForm);
      await loadPages();
      setSelectedPageId(created.id);
      setMessage(`Saved ${created.display_name}.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not create page.');
    } finally {
      setIsSaving(false);
    }
  }

  async function deleteSelectedPage() {
    if (!selectedPage) {
      return;
    }
    const confirmed = window.confirm(`Delete ${selectedPage.display_name}?`);
    if (!confirmed) {
      return;
    }
    setIsSaving(true);
    setMessage('Deleting page...');
    try {
      const response = await fetch(`/api/orgs/${activeOrgId()}/pages/${selectedPage.id}`, {
        method: 'DELETE',
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      await loadPages();
      setMessage(`Deleted ${selectedPage.display_name}.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not delete page.');
    } finally {
      setIsSaving(false);
    }
  }

  async function savePolicy() {
    if (!selectedPage || !policyDraft) {
      return;
    }
    const validationMessage = validatePolicy(policyDraft);
    if (validationMessage) {
      setMessage(validationMessage);
      return;
    }
    setIsPolicySaving(true);
    setMessage('Saving policy...');
    try {
      const response = await fetch(`/api/orgs/${activeOrgId()}/policy/page/${selectedPage.id}`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          'X-Actor-Id': 'operator:ui-rebuild',
        },
        body: JSON.stringify(policyDraft),
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const saved = (await response.json()) as PagePolicy;
      setPolicy(saved);
      setPolicyDraft(clonePolicy(saved.state));
      setMessage(`Policy saved for ${selectedPage.display_name}.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not save policy.');
    } finally {
      setIsPolicySaving(false);
    }
  }

  async function triggerIdeaPlan() {
    if (!selectedPage) {
      return;
    }
    setIsWorkflowSaving(true);
    setMessage('Creating plan...');
    try {
      const response = await fetch(`/api/orgs/${activeOrgId()}/pages/${selectedPage.id}/idea-plans`, {
        method: 'POST',
        headers: { 'X-Actor-Id': 'operator:ui-rebuild' },
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const created = (await response.json()) as RunRecord;
      await loadRuns(selectedPage.id);
      setSelectedPlanRunId(created.id);
      setMessage('Plan created.');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not create plan.');
    } finally {
      setIsWorkflowSaving(false);
    }
  }

  async function triggerVideoGeneration(mode: 'runway' | 'smoke_test') {
    if (!selectedPage || !selectedPlan) {
      setMessage('Create or select a plan first.');
      return;
    }
    setIsWorkflowSaving(true);
    setMessage(mode === 'runway' ? 'Creating Runway package...' : 'Creating smoke package...');
    try {
      const response = await fetch(
        `/api/orgs/${activeOrgId()}/pages/${selectedPage.id}/idea-plans/${selectedPlan.id}/generate-package`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-Actor-Id': 'operator:ui-rebuild',
          },
          body: JSON.stringify({ generation_mode: mode }),
        },
      );
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const created = (await response.json()) as RunRecord;
      await loadRuns(selectedPage.id);
      setSelectedPackageRunId(created.id);
      setMessage(mode === 'runway' ? 'Runway package queued.' : 'Smoke package queued.');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not create package.');
    } finally {
      setIsWorkflowSaving(false);
    }
  }

  async function discardSelectedPlan() {
    if (!selectedPage || !selectedPlan) {
      return;
    }
    const confirmed = window.confirm(`Discard ${planTitle(selectedPlan)}?`);
    if (!confirmed) {
      return;
    }
    setIsWorkflowSaving(true);
    setMessage('Discarding plan...');
    try {
      const response = await fetch(
        `/api/orgs/${activeOrgId()}/pages/${selectedPage.id}/idea-plans/${selectedPlan.id}/discard`,
        {
          method: 'POST',
          headers: { 'X-Actor-Id': 'operator:ui-rebuild' },
        },
      );
      if (!response.ok) {
        throw new Error(await response.text());
      }
      await loadRuns(selectedPage.id);
      setMessage('Plan discarded.');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not discard plan.');
    } finally {
      setIsWorkflowSaving(false);
    }
  }

  function updatePolicyDraft(updater: (current: PolicyDocument) => PolicyDocument) {
    setPolicyDraft((current) => (current ? updater(current) : current));
  }

  function numberValue(value: string): number {
    return Number.parseFloat(value || '0');
  }

  async function copyArtifactText() {
    if (!artifactText) {
      return;
    }
    await navigator.clipboard.writeText(artifactText);
    setMessage('Copied.');
  }

  return (
    <main className="workspace-shell">
      <aside className="pages-rail" aria-label="Pages">
        <div className="rail-header">
          <div>
            <p className="eyebrow">Pages</p>
            <h1>Content Lab</h1>
          </div>
          <button
            className="utility-button"
            type="button"
            onClick={() => void loadPages()}
            disabled={isLoading}
          >
            Refresh
          </button>
        </div>

        <label className="field">
          Select org
          <select
            value={selectedOrgId}
            onChange={(event) => handleOrgChange(event.target.value)}
            disabled={!orgs.length}
          >
            {orgs.map((org) => (
              <option key={org.id} value={org.id}>
                {formatOrgOption(org)}
              </option>
            ))}
            {!orgs.length && (
              <option value={selectedOrgId}>
                {selectedOrg ? formatOrgOption(selectedOrg) : `Org ${selectedOrgId.slice(0, 8)}`}
              </option>
            )}
          </select>
        </label>

        <label className="field">
          Select page
          <select
            value={selectedPage?.id ?? ''}
            onChange={(event) => setSelectedPageId(event.target.value)}
            disabled={!pages.length}
          >
            {pages.map((page) => (
              <option key={page.id} value={page.id}>
                {page.display_name} {page.handle ? `(${page.handle})` : ''}
              </option>
            ))}
            {!pages.length && <option value="">No pages yet</option>}
          </select>
        </label>

        {selectedPage ? (
          <section className="rail-section">
            <p className="eyebrow">{selectedPage.ownership}</p>
            <strong>{selectedPage.display_name}</strong>
            <span>{selectedPage.handle ?? selectedPage.platform}</span>
            <div className="rail-policy">
              <button
                className="policy-toggle"
                type="button"
                aria-expanded={isPolicyOpen}
                onClick={() => setIsPolicyOpen((current) => !current)}
              >
                <span>Policy</span>
                <strong>{isPolicyOpen ? 'Hide' : 'Show'}</strong>
              </button>
              <p className="muted">{formatPolicySource(policy)}</p>
              {isPolicyOpen && policyDraft ? (
                <PolicyEditor
                  policyDraft={policyDraft}
                  isSaving={isPolicySaving}
                  savePolicy={() => void savePolicy()}
                  updatePolicyDraft={updatePolicyDraft}
                  numberValue={numberValue}
                />
              ) : null}
              {isPolicyOpen && !policyDraft ? <p className="muted">Loading policy...</p> : null}
            </div>
            <button
              className="danger-button"
              type="button"
              onClick={deleteSelectedPage}
              disabled={isSaving}
            >
              Delete
            </button>
          </section>
        ) : null}

        <form className="rail-section" onSubmit={createPage}>
          <p className="eyebrow">Create</p>
          <label className="field">
            Name
            <input
              value={form.displayName}
              onChange={(event) =>
                setForm((current) => ({ ...current, displayName: event.target.value }))
              }
              placeholder="New brand page"
            />
          </label>
          <label className="field">
            Handle
            <input
              value={form.handle}
              onChange={(event) =>
                setForm((current) => ({ ...current, handle: event.target.value }))
              }
              placeholder="@new.page"
            />
          </label>
          <div className="field-row">
            <label className="field">
              Platform
              <select
                value={form.platform}
                onChange={(event) =>
                  setForm((current) => ({ ...current, platform: event.target.value }))
                }
              >
                <option value="instagram">Instagram</option>
                <option value="tiktok">TikTok</option>
                <option value="youtube">YouTube</option>
              </select>
            </label>
            <label className="field">
              Type
              <select
                value={form.ownership}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    ownership: event.target.value as FormState['ownership'],
                  }))
                }
              >
                <option value="owned">Owned</option>
                <option value="competitor">Competitor</option>
              </select>
            </label>
          </div>
          <button className="primary-button" type="submit" disabled={isSaving}>
            Create page
          </button>
        </form>
      </aside>

      <section className="workbench" aria-label="Reel workbench">
        <div className="notice-line">
          <span className={`status-dot ${hasActiveGeneration ? 'is-live' : ''}`} />
          <span>{message}</span>
        </div>

        {selectedPage ? (
          <>
            <header className="page-hero">
              <div>
                <p className="eyebrow">{selectedPage.platform}</p>
                <h2>{selectedPage.display_name}</h2>
                <p>
                  {selectedPage.handle ?? 'No handle'} · Updated{' '}
                  {formatDate(selectedPage.updated_at)}
                </p>
              </div>
              <div className="hero-metrics" aria-label="Page workflow counts">
                <span>{planRuns.length} queued</span>
                <span>{packageGenerationRuns.length + assetCompositionRuns.length} outputs</span>
                <span>{formatPolicySource(policy)}</span>
              </div>
            </header>

            <nav
              className="tabs workbench-mode-tabs"
              role="tablist"
              aria-label="Generation workspace"
            >
              <button
                type="button"
                role="tab"
                id="workbench-tab-two-button"
                aria-controls="workbench-panel-two-button"
                aria-selected={workbenchTab === 'two_button_reel_path'}
                className={workbenchTab === 'two_button_reel_path' ? 'is-active' : ''}
                onClick={() => setWorkbenchTab('two_button_reel_path')}
              >
                Two-button reel path
              </button>
              <button
                type="button"
                role="tab"
                id="workbench-tab-asset-pack"
                aria-controls="workbench-panel-asset-pack"
                aria-selected={workbenchTab === 'asset_pack_generation'}
                className={workbenchTab === 'asset_pack_generation' ? 'is-active' : ''}
                onClick={() => setWorkbenchTab('asset_pack_generation')}
              >
                Asset pack based generation
              </button>
              <button
                type="button"
                role="tab"
                id="workbench-tab-hook-image"
                aria-controls="workbench-panel-hook-image"
                aria-selected={workbenchTab === 'live_hook_image_creator'}
                className={workbenchTab === 'live_hook_image_creator' ? 'is-active' : ''}
                onClick={() => setWorkbenchTab('live_hook_image_creator')}
              >
                Live hook image creator
              </button>
            </nav>

            {workbenchTab === 'two_button_reel_path' ? (
              <>
                <section
                  className="generation-surface"
                  aria-label="Two-button reel path"
                  id="workbench-panel-two-button"
                  role="tabpanel"
                  aria-labelledby="workbench-tab-two-button"
                >
                  <div className="section-heading">
                    <div>
                      <p className="eyebrow">Reel workflow</p>
                      <h3>Two-button path</h3>
                    </div>
                    <button
                      className="primary-button"
                      type="button"
                      onClick={() => void triggerIdeaPlan()}
                      disabled={isWorkflowSaving}
                    >
                      Create plan
                    </button>
                  </div>

                  <div className="generation-grid">
                    <div className="plan-zone">
                      <div className="section-heading is-compact">
                        <div>
                          <p className="eyebrow">Reel workflow</p>
                          <h3>Queued plan</h3>
                        </div>
                      </div>
                      <div className="inline-controls">
                        <label className="field">
                          Queued plans
                          <select
                            value={selectedPlan?.id ?? ''}
                            onChange={(event) => setSelectedPlanRunId(event.target.value)}
                            disabled={!planRuns.length}
                          >
                            {planRuns.map((run) => (
                              <option key={run.id} value={run.id}>
                                {planTitle(run)}
                              </option>
                            ))}
                            {!planRuns.length && <option value="">No plans queued</option>}
                          </select>
                        </label>
                        <button
                          className="danger-button"
                          type="button"
                          onClick={() => void discardSelectedPlan()}
                          disabled={isWorkflowSaving || !selectedPlan}
                        >
                          Discard
                        </button>
                      </div>
                      <PlanSummary plan={selectedPlanPayload} emptyLabel="No plans queued" />
                    </div>

                    <div className="action-zone">
                      <button
                        className="mode-button"
                        type="button"
                        onClick={() => void triggerVideoGeneration('smoke_test')}
                        disabled={isWorkflowSaving || !selectedPlan}
                      >
                        Smoke
                        <span>No paid AI</span>
                      </button>
                      <button
                        className="mode-button"
                        type="button"
                        onClick={() => void triggerVideoGeneration('runway')}
                        disabled={isWorkflowSaving || !selectedPlan}
                      >
                        Runway
                        <span>Live video</span>
                      </button>
                    </div>
                  </div>
                </section>

                <section className="output-surface" aria-label="Generated packages">
                  <div className="section-heading">
                    <div>
                      <p className="eyebrow">Outputs</p>
                      <h3>Generated packages</h3>
                    </div>
                  </div>

                  {packageGenerationRuns.length ? (
                    <>
                      <label className="field">
                        Generated package
                        <select
                          value={selectedPackageRun?.id ?? ''}
                          onChange={(event) => setSelectedPackageRunId(event.target.value)}
                        >
                          {packageGenerationRuns.map((run) => {
                            const sourcePlanId = packagePlanRunId(run);
                            const sourcePlan = sourcePlanId
                              ? runs.find((candidate) => candidate.id === sourcePlanId)
                              : null;
                            return (
                              <option key={run.id} value={run.id}>
                                {sourcePlan
                                  ? planTitle(sourcePlan)
                                  : `Package ${run.id.slice(0, 8)}`}{' '}
                                · {generationMode(run) ?? 'package'} · {run.status}
                              </option>
                            );
                          })}
                        </select>
                      </label>

                      <PackageSummary
                        run={selectedPackageRun}
                        detail={packageDetail}
                        notice={packageNotice}
                        failures={failureMessages}
                      />
                      <LifecycleSteps run={selectedPackageRun} />

                      <section className="connected-panel">
                        <div className="section-heading is-compact">
                          <div>
                            <p className="eyebrow">Generated package</p>
                            <h3>Package plan</h3>
                          </div>
                        </div>
                        <PlanSummary
                          plan={selectedPackagePlanPayload}
                          emptyLabel="No package plan"
                          compact
                        />
                      </section>

                      {artifactTabs.length ? (
                        <ArtifactViewer
                          tabs={artifactTabs}
                          activeTab={artifactTab}
                          setActiveTab={setArtifactTab}
                          packageDetail={packageDetail}
                          run={selectedPackageRun}
                          artifact={selectedArtifact}
                          download={selectedDownload ?? null}
                          artifactText={artifactText}
                          artifactTextStatus={artifactTextStatus}
                          copyArtifactText={() => void copyArtifactText()}
                        />
                      ) : (
                        <div className="empty-state">
                          {selectedPackageRun?.status === 'failed'
                            ? (runErrorMessage(selectedPackageRun) ?? 'Artifacts not written.')
                            : packageNotice || 'Package still running.'}
                        </div>
                      )}
                    </>
                  ) : (
                    <div className="empty-state">No packages yet</div>
                  )}
                </section>
              </>
            ) : workbenchTab === 'asset_pack_generation' ? (
              <section
                className="asset-pack-workspace"
                id="workbench-panel-asset-pack"
                role="tabpanel"
                aria-labelledby="workbench-tab-asset-pack"
                aria-label="Asset pack based generation"
              >
                <AssetPackGenerationWorkspace
                  key={`${selectedOrgId}:${selectedPage.id}`}
                  orgId={selectedOrgId}
                  selectedPage={selectedPage}
                  onRunsChanged={() => void loadRuns(selectedPage.id)}
                  setWorkspaceMessage={setMessage}
                  assetCompositionRuns={assetCompositionRuns}
                  selectedOutputRun={selectedCompositionRun}
                  setSelectedOutputRunId={setSelectedCompositionRunId}
                  packageDetail={packageDetail}
                  packageNotice={packageNotice}
                  failureMessages={failureMessages}
                  artifactTabs={artifactTabs}
                  artifactTab={artifactTab}
                  setArtifactTab={setArtifactTab}
                  selectedArtifact={selectedArtifact}
                  selectedDownload={selectedDownload ?? null}
                  artifactText={artifactText}
                  artifactTextStatus={artifactTextStatus}
                  copyArtifactText={() => void copyArtifactText()}
                  savedHookGenerations={savedHookGenerations}
                  onSaveHookGeneration={persistHookGeneration}
                />
              </section>
            ) : (
              <section
                className="asset-pack-workspace"
                id="workbench-panel-hook-image"
                role="tabpanel"
                aria-labelledby="workbench-tab-hook-image"
                aria-label="Live hook image creator"
              >
                <HookImageCreator
                  orgId={selectedOrgId}
                  selectedPage={selectedPage}
                  onRunsChanged={() => void loadRuns(selectedPage.id)}
                  compositionRuns={assetCompositionRuns}
                  selectedRun={selectedCompositionRun}
                  setSelectedRunId={setSelectedCompositionRunId}
                  savedHookGenerations={savedHookGenerations}
                  onSaveGeneration={persistHookGeneration}
                  setWorkspaceMessage={setMessage}
                />
              </section>
            )}
          </>
        ) : (
          <section className="empty-page">
            <p className="eyebrow">{pageLoadError ? 'Connection' : 'Start'}</p>
            <h2>{pageLoadError ? 'Pages could not load' : 'Create your first page'}</h2>
            <p>
              {pageLoadError
                ? 'The saved pages may still exist, but the UI could not reach the API. Try Refresh after the backend is running.'
                : 'Use the left rail. Pages save through the API and reload here.'}
            </p>
          </section>
        )}
      </section>
    </main>
  );
}

function PlanSummary({
  plan,
  emptyLabel,
  compact = false,
}: {
  plan: Record<string, unknown> | null;
  emptyLabel: string;
  compact?: boolean;
}) {
  if (!plan) {
    return <div className="empty-state">{emptyLabel}</div>;
  }
  const beats = planBeats(plan);
  return (
    <div className={compact ? 'plan-summary is-compact' : 'plan-summary'}>
      <h4>{textValue(plan.title) ?? 'Untitled plan'}</h4>
      <dl>
        <div>
          <dt>Hook</dt>
          <dd>{textValue(plan.hook) ?? 'Not set'}</dd>
        </div>
        <div>
          <dt>Angle</dt>
          <dd>{textValue(plan.angle) ?? 'Not set'}</dd>
        </div>
      </dl>
      {beats.length ? (
        <ol>
          {beats.map((beat, index) => (
            <li key={`${textValue(beat.label) ?? 'beat'}-${index}`}>
              <strong>{textValue(beat.label) ?? `Beat ${index + 1}`}</strong>
              <span>{textValue(beat.text) ?? 'No copy'}</span>
            </li>
          ))}
        </ol>
      ) : null}
    </div>
  );
}

function PackageSummary({
  run,
  detail,
  notice,
  failures,
}: {
  run: RunRecord | null;
  detail: PackageDetail | null;
  notice: string;
  failures: string[];
}) {
  const runway = generationMode(run) === 'runway' ? runwayUsageSummary(run) : null;
  const hasLocalOutputs = Boolean(
    fallbackArtifactForTab(run, 'video') || fallbackArtifactForTab(run, 'cover'),
  );
  return (
    <div className="package-summary">
      <div>
        <span className={`status-pill ${statusTone(run?.status)}`}>{run?.status ?? 'none'}</span>
        <span>{generationMode(run) ?? 'package'}</span>
        <span>Updated {formatDate(run?.updated_at)}</span>
        <span>
          {detail
            ? `${detail.artifacts.length} artifacts`
            : hasLocalOutputs
              ? 'QA failed; local outputs available'
              : notice || 'Package still running'}
        </span>
      </div>
      {runway ? (
        <div className="runway-usage">
          {runway.rows.map((row) => (
            <span key={row}>{row}</span>
          ))}
        </div>
      ) : null}
      {failures.length ? (
        <ul>
          {failures.map((failure) => (
            <li key={failure}>{failure}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function LifecycleSteps({ run }: { run: RunRecord | null }) {
  return (
    <div className="lifecycle" aria-label="Run lifecycle">
      {workflowSteps.map((step) => {
        const status = stepStatus(run, step.key);
        return (
          <div className={`lifecycle-step ${statusTone(status)}`} key={step.key}>
            <strong>{step.label}</strong>
            <span>{status}</span>
          </div>
        );
      })}
    </div>
  );
}

function ArtifactViewer({
  tabs,
  activeTab,
  setActiveTab,
  packageDetail,
  run,
  artifact,
  download,
  artifactText,
  artifactTextStatus,
  copyArtifactText,
}: {
  tabs: ArtifactTab[];
  activeTab: ArtifactTab;
  setActiveTab: (tab: ArtifactTab) => void;
  packageDetail: PackageDetail | null;
  run: RunRecord | null;
  artifact: PackageArtifact | null;
  download: SignedDownload | null;
  artifactText: string;
  artifactTextStatus: string;
  copyArtifactText: () => void;
}) {
  const structuredContent =
    activeTab !== 'raw' && activeTab !== 'video' && activeTab !== 'cover'
      ? parseArtifactText(artifactText || artifactTextStatus)
      : null;

  return (
    <div className="artifact-viewer">
      <div className="tabs" role="tablist" aria-label="Package artifacts">
        {tabs.map((tab) => (
          <button
            className={tab === activeTab ? 'is-active' : ''}
            type="button"
            role="tab"
            aria-selected={tab === activeTab}
            key={tab}
            onClick={() => setActiveTab(tab)}
          >
            {tabLabel(tab)}
          </button>
        ))}
      </div>

      <div className="artifact-toolbar">
        <span>
          {artifact?.name ?? (activeTab === 'raw' ? 'package_detail' : tabLabel(activeTab))}
        </span>
        <div>
          {download?.url ? (
            <a href={download.url} target="_blank" rel="noreferrer">
              Open
            </a>
          ) : null}
          {artifactText ? (
            <button className="utility-button" type="button" onClick={copyArtifactText}>
              Copy
            </button>
          ) : null}
        </div>
      </div>

      {activeTab === 'video' && artifactIsAvailable(artifact) ? (
        <div className="media-frame">
          <video controls src={artifact?.download?.url} />
        </div>
      ) : null}

      {activeTab === 'cover' && artifactIsAvailable(artifact) ? (
        <div className="media-frame">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={artifact?.download?.url} alt="Generated cover" />
        </div>
      ) : null}

      {activeTab !== 'video' && activeTab !== 'cover' ? (
        activeTab === 'raw' ? (
          <pre className="artifact-code">
            {artifactText ||
              artifactTextStatus ||
              formatJson(packageDetail ?? run?.output_payload ?? run)}
          </pre>
        ) : (
          <StructuredArtifactContent value={structuredContent} />
        )
      ) : null}
    </div>
  );
}

export function AssetPackGenerationWorkspace({
  orgId: _orgId,
  selectedPage,
  onRunsChanged,
  setWorkspaceMessage,
  assetCompositionRuns = [],
  selectedOutputRun = null,
  setSelectedOutputRunId = () => undefined,
  packageDetail = null,
  packageNotice = '',
  failureMessages = [],
  artifactTabs = [],
  artifactTab = 'raw',
  setArtifactTab = () => undefined,
  selectedArtifact = null,
  selectedDownload = null,
  artifactText = '',
  artifactTextStatus = '',
  copyArtifactText = () => undefined,
  savedHookGenerations = [],
  onSaveHookGeneration = () => undefined,
}: {
  orgId?: string;
  selectedPage: PageRecord;
  onRunsChanged: () => void;
  setWorkspaceMessage: (message: string) => void;
  assetCompositionRuns?: RunRecord[];
  selectedOutputRun?: RunRecord | null;
  setSelectedOutputRunId?: (runId: string) => void;
  packageDetail?: PackageDetail | null;
  packageNotice?: string;
  failureMessages?: string[];
  artifactTabs?: ArtifactTab[];
  artifactTab?: ArtifactTab;
  setArtifactTab?: (tab: ArtifactTab) => void;
  selectedArtifact?: PackageArtifact | null;
  selectedDownload?: SignedDownload | null;
  artifactText?: string;
  artifactTextStatus?: string;
  copyArtifactText?: () => void;
  savedHookGenerations?: SavedHookImageGeneration[];
  onSaveHookGeneration?: (generation: SavedHookImageGeneration) => void;
}) {
  const [isAssetLibraryOpen, setIsAssetLibraryOpen] = useState(true);
  const [selectedBrowserAssetId, setSelectedBrowserAssetId] = useState('');
  const [assetBrowserFilter, setAssetBrowserFilter] = useState<'all' | 'background' | 'object'>('all');
  const [planner, setPlanner] = useState<AssetPackPlannerState>({
    name: `${selectedPage.display_name} asset pack`,
    totalAssetCount: 24,
    backgroundCount: 12,
    objectCount: 12,
    qualityLevel: 'balanced',
    format: 'proof reel',
    style: 'clean product',
    provider: 'runway',
    model: 'gen4.5',
    ratio: '9:16',
  });
  const [assetPack, setAssetPack] = useState<AssetPackRecord | null>(null);
  const [savedAssetPacks, setSavedAssetPacks] = useState<AssetPackRecord[]>([]);
  const [selectedAssetPackId, setSelectedAssetPackId] = useState('');
  const [packAssets, setPackAssets] = useState<AssetLibraryItem[]>([]);
  const [candidateCompositions, setCandidateCompositions] = useState<CandidateComposition[]>([]);
  const [packBrowserMessage, setPackBrowserMessage] = useState('Create or select a pack.');
  const [combinatorOutboxMessage, setCombinatorOutboxMessage] = useState(
    'Choose a saved pack, then queue a composition render.',
  );
  const [compositionPickIndex, setCompositionPickIndex] = useState(0);
  const [isPackActionRunning, setIsPackActionRunning] = useState(false);
  const assetBrowserItemRefs = useRef<Record<string, HTMLButtonElement | null>>({});

  const activeAssetLibrary = packAssets.length ? packAssets : assetLibrarySeed;
  const browserAssetPool = useMemo(
    () =>
      activeAssetLibrary.filter(
        (asset) => asset.kind === 'background' || asset.kind === 'object',
      ),
    [activeAssetLibrary],
  );
  const visiblePackAssets = useMemo(
    () =>
      assetBrowserFilter === 'all'
        ? browserAssetPool
        : browserAssetPool.filter((asset) => asset.kind === assetBrowserFilter),
    [assetBrowserFilter, browserAssetPool],
  );
  const visiblePackAssetIds = useMemo(
    () => visiblePackAssets.map((asset) => asset.id).join('|'),
    [visiblePackAssets],
  );
  const visibleBackgroundCount = browserAssetPool.filter((asset) => asset.kind === 'background').length;
  const visibleObjectCount = browserAssetPool.filter((asset) => asset.kind === 'object').length;
  const combinatorAssetPacks = savedAssetPacks.filter(isCombinatorEligibleAssetPack);
  const selectedSavedPack =
    savedAssetPacks.find((pack) => pack.id === selectedAssetPackId) ?? assetPack ?? null;
  const selectedCombinatorPack =
    combinatorAssetPacks.find((pack) => pack.id === selectedAssetPackId) ??
    (assetPack && isCombinatorEligibleAssetPack(assetPack) ? assetPack : null);
  const compositionSeed = `${selectedCombinatorPack?.id ?? selectedPage.id}:${compositionPickIndex}`;
  const selectedCandidate =
    candidateCompositions.length > 0
      ? candidateCompositions[compositionPickIndex % candidateCompositions.length]
      : null;
  const selectedBackground =
    assetFromCandidateRole(selectedCandidate, 'background') ??
    pickAsset('background', compositionSeed, 0, activeAssetLibrary);
  const selectedObject =
    assetFromCandidateRole(selectedCandidate, 'foreground') ??
    assetFromCandidateRole(selectedCandidate, 'object') ??
    pickAsset('object', compositionSeed, 1, activeAssetLibrary);
  const selectedHook =
    assetFromCandidateRole(selectedCandidate, 'hook') ??
    syntheticHookAsset(selectedSavedPack, selectedObject);
  const selectedAudio =
    assetFromCandidateRole(selectedCandidate, 'audio') ??
    pickOptionalAsset('audio', compositionSeed, 3, activeAssetLibrary);
  const selectedVideo =
    assetFromCandidateRole(selectedCandidate, 'format') ??
    pickOptionalAsset('video', compositionSeed, 4, activeAssetLibrary);
  const selectedCombinationAssets = [
    selectedBackground,
    selectedObject,
    selectedHook,
    selectedAudio,
    selectedVideo,
  ].filter((asset): asset is AssetLibraryItem => asset !== null);
  const outputScore = Math.round(
    selectedCombinationAssets.reduce(
      (sum, asset) => sum + asset.performanceScore,
      0,
    ) / Math.max(1, selectedCombinationAssets.length),
  );
  const actionDisabled = isPackActionRunning || !selectedPage;
  const selectedOutputIsComposition = selectedOutputRun ? isAssetCompositionRun(selectedOutputRun) : false;

  useEffect(() => {
    void loadSavedAssetPacks();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedPage.id]);

  useEffect(() => {
    if (!selectedAssetPackId) {
      setPackAssets([]);
      setCandidateCompositions([]);
      return;
    }
    void loadSelectedPackAssets(selectedAssetPackId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedAssetPackId]);

  useEffect(() => {
    if (
      selectedBrowserAssetId &&
      !visiblePackAssets.some((asset) => asset.id === selectedBrowserAssetId)
    ) {
      setSelectedBrowserAssetId('');
    }
  }, [selectedBrowserAssetId, visiblePackAssetIds, visiblePackAssets]);

  useEffect(() => {
    if (!selectedBrowserAssetId) {
      return;
    }
    assetBrowserItemRefs.current[selectedBrowserAssetId]?.scrollIntoView({
      block: 'nearest',
      inline: 'nearest',
    });
  }, [selectedBrowserAssetId]);

  async function loadSavedAssetPacks(preferredPackId?: string): Promise<AssetPackRecord[]> {
    try {
      const response = await fetch(`/api/orgs/${activeOrgId()}/asset-packs?limit=50`, {
        cache: 'no-store',
        headers: { 'X-Actor-Id': 'operator:ui-rebuild' },
      });
      if (!response.ok) {
        throw new Error(await apiErrorMessage(response));
      }
      const packs = ((await response.json()) as AssetPackRecord[]).filter(
        (pack) => pack.status !== 'rejected' && pack.status !== 'archived',
      );
      setSavedAssetPacks(packs);
      const fallbackPackId =
        packs.find((pack) => pack.id === selectedAssetPackId)?.id ?? packs[0]?.id ?? '';
      const nextSelected =
        preferredPackId ||
        packs.find((pack) => pack.id === selectedAssetPackId)?.id ||
        fallbackPackId;
      setSelectedAssetPackId(nextSelected);
      return packs;
    } catch (error) {
      setPackBrowserMessage(
        error instanceof Error ? error.message : 'Could not load saved asset packs.',
      );
      return [];
    }
  }

  async function loadSelectedPackAssets(assetPackId: string): Promise<AssetLibraryItem[]> {
    try {
      const assetsResponse = await fetch(
        `/api/orgs/${activeOrgId()}/assets?asset_pack_id=${assetPackId}&ready_status=ready&limit=200`,
        {
          cache: 'no-store',
          headers: { 'X-Actor-Id': 'operator:ui-rebuild' },
        },
      );
      if (!assetsResponse.ok) {
        throw new Error(await apiErrorMessage(assetsResponse));
      }
      const assetRows = (await assetsResponse.json()) as AssetLibraryItemOut[];
      const mappedAssets = assetRows.map((row) => mapAssetLibraryItemOut(row, activeOrgId()));
      setPackAssets(mappedAssets);

      const combinationsResponse = await fetch(
        `/api/orgs/${activeOrgId()}/asset-packs/${assetPackId}/combinations`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-Actor-Id': 'operator:ui-rebuild',
          },
          body: JSON.stringify({
            target_reel_count: 12,
            mode: 'balanced',
            filters: {},
          }),
        },
      );
      if (combinationsResponse.ok) {
        const combinations = (await combinationsResponse.json()) as AssetPackCombinationsResponse;
        setCandidateCompositions(combinations.candidate_compositions);
        setCombinatorOutboxMessage(
          combinations.candidate_compositions.length
            ? `Loaded ${combinations.candidate_compositions.length} backend combinations from ${combinations.asset_pack.name}.`
            : `${combinations.asset_pack.name} has visual assets but no backend hook-text combinations; preview will use its real PNGs with a generated hook label.`,
        );
      } else {
        setCandidateCompositions([]);
        setCombinatorOutboxMessage(
          `Loaded pack assets, but backend combinations are unavailable: ${await apiErrorMessage(
            combinationsResponse,
          )}`,
        );
      }
      return mappedAssets;
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Could not load pack assets.';
      setPackAssets([]);
      setCandidateCompositions([]);
      setCombinatorOutboxMessage(message);
      return [];
    }
  }

  async function createBackendPackPlan(): Promise<AssetPackPlanResponse> {
    const backgroundCount = Math.max(0, Math.floor(planner.backgroundCount));
    const objectCount = Math.max(0, Math.floor(planner.objectCount));
    const requestedAssetCount = Math.max(1, backgroundCount + objectCount);
    const response = await fetch(`/api/orgs/${activeOrgId()}/asset-packs/plan`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Actor-Id': 'operator:ui-rebuild',
      },
      body: JSON.stringify({
        name: planner.name.trim() || `${selectedPage.display_name} asset pack`,
        niche: selectedPage.handle ?? selectedPage.display_name,
        requested_asset_count: requestedAssetCount,
        asset_mix: {
          background_image: backgroundCount,
          transparent_cutout_png: objectCount,
        },
        target_reel_types: [planner.format],
        style_persona_constraints: {
          quality_level: planner.qualityLevel,
          style: planner.style,
          ratio: planner.ratio,
        },
        purpose: 'Reusable component pack for asset-led reel generation.',
        target_audience: selectedPage.handle ?? selectedPage.display_name,
      }),
    });
    if (!response.ok) {
      throw new Error(await apiErrorMessage(response));
    }
    const created = (await response.json()) as AssetPackPlanResponse;
    setAssetPack(created.asset_pack);
    setSelectedAssetPackId(created.asset_pack.id);
    setPackBrowserMessage(`Planned ${created.asset_pack.name}.`);
    return created;
  }

  async function approveSavedPack(pack: AssetPackRecord): Promise<AssetPackRecord> {
    if (pack.status === 'approved' || pack.status === 'ready' || pack.status === 'generating') {
      return pack;
    }
    if (pack.status !== 'planned') {
      throw new Error(`Asset pack is ${pack.status}; create a new planned pack before approving.`);
    }
    const response = await fetch(`/api/orgs/${activeOrgId()}/asset-packs/${pack.id}/approve`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Actor-Id': 'operator:ui-rebuild',
      },
      body: JSON.stringify({
        note: 'Approved from asset pack workspace.',
        metadata: { source: 'web_asset_pack_workspace' },
      }),
    });
    if (!response.ok) {
      throw new Error(await apiErrorMessage(response));
    }
    const approved = (await response.json()) as AssetPackRecord;
    setAssetPack(approved);
    setSelectedAssetPackId(approved.id);
    setPackBrowserMessage(`Approved ${approved.name}.`);
    return approved;
  }

  async function generateApprovedPack(pack: AssetPackRecord): Promise<AssetPackPlanResponse> {
    const response = await fetch(`/api/orgs/${activeOrgId()}/asset-packs/${pack.id}/generate`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Actor-Id': 'operator:ui-rebuild',
      },
      body: JSON.stringify({
        provider: planner.provider,
        model: planner.model,
        asset_class: 'component',
        ratio: planner.ratio,
        allow_existing_reuse: true,
      }),
    });
    if (!response.ok) {
      throw new Error(await apiErrorMessage(response));
    }
    return (await response.json()) as AssetPackPlanResponse;
  }

  async function createPack() {
    setIsPackActionRunning(true);
    setWorkspaceMessage('Creating asset pack...');
    setPackBrowserMessage('Planning asset pack...');
    try {
      const created = await createBackendPackPlan();
      setPackBrowserMessage('Approving asset pack...');
      const approved = await approveSavedPack(created.asset_pack);
      setPackBrowserMessage('Generating asset pack...');
      const generated = await generateApprovedPack(approved);
      const generatedPack = generated.asset_pack;
      setAssetPack(generatedPack);
      setSelectedAssetPackId(generatedPack.id);
      setSelectedBrowserAssetId('');
      setAssetBrowserFilter('all');
      await loadSavedAssetPacks(generatedPack.id);
      await loadSelectedPackAssets(generatedPack.id);
      setPackBrowserMessage(`Created ${generatedPack.name}.`);
      setWorkspaceMessage(`Created ${generatedPack.name}.`);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Could not create asset pack.';
      setPackBrowserMessage(message);
      setWorkspaceMessage(message);
    } finally {
      setIsPackActionRunning(false);
    }
  }

  async function deleteSelectedPack() {
    const packToDelete = selectedSavedPack;
    if (!packToDelete) {
      setPackBrowserMessage('No pack selected.');
      return;
    }
    const confirmed = window.confirm(`Delete ${packToDelete.name} from the pack browser?`);
    if (!confirmed) {
      return;
    }
    setIsPackActionRunning(true);
    setWorkspaceMessage('Deleting asset pack...');
    setPackBrowserMessage(`Deleting ${packToDelete.name}...`);
    try {
      const response = await fetch(`/api/orgs/${activeOrgId()}/asset-packs/${packToDelete.id}/reject`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Actor-Id': 'operator:ui-rebuild',
        },
        body: JSON.stringify({
          note: 'Deleted from asset pack browser.',
          metadata: { source: 'web_asset_pack_workspace' },
        }),
      });
      if (!response.ok) {
        throw new Error(await apiErrorMessage(response));
      }
      await response.json();
      const remainingPacks = savedAssetPacks.filter((pack) => pack.id !== packToDelete.id);
      setSavedAssetPacks(remainingPacks);
      const nextPack = remainingPacks[0] ?? null;
      setAssetPack(nextPack);
      setSelectedAssetPackId(nextPack?.id ?? '');
      setSelectedBrowserAssetId('');
      setAssetBrowserFilter('all');
      if (nextPack) {
        await loadSelectedPackAssets(nextPack.id);
      } else {
        setPackAssets([]);
        setCandidateCompositions([]);
      }
      setPackBrowserMessage(`Deleted ${packToDelete.name}.`);
      setWorkspaceMessage(`Deleted ${packToDelete.name}.`);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Could not delete asset pack.';
      setPackBrowserMessage(message);
      setWorkspaceMessage(
        message,
      );
    } finally {
      setIsPackActionRunning(false);
    }
  }

  return (
    <>
      <section className="generation-surface asset-library-panel">
        <button
          className="collapsible-section-toggle"
          type="button"
          aria-expanded={isAssetLibraryOpen}
          onClick={() => setIsAssetLibraryOpen((current) => !current)}
        >
          <div>
            <p className="eyebrow">Saved packs and asset library</p>
            <h3>Pack browser</h3>
          </div>
          <span>
            <span className="status-pill">
              {savedAssetPacks.length} saved /{' '}
              {packAssets.length ? `${packAssets.length} pack assets` : `${assetLibrarySeed.length} demo assets`}
            </span>
            <strong>{isAssetLibraryOpen ? 'Collapse' : 'Expand'}</strong>
          </span>
        </button>

        {isAssetLibraryOpen ? (
          <div className="pack-browser-shell">
            <aside className="pack-browser-controls" aria-label="Pack browser controls">
              <label className="field">
                Pack
                <select
                  value={selectedAssetPackId}
                  onChange={(event) => {
                    const pack = savedAssetPacks.find(
                      (candidate) => candidate.id === event.target.value,
                    );
                    setSelectedAssetPackId(event.target.value);
                    setSelectedBrowserAssetId('');
                    if (pack) {
                      setAssetPack(pack);
                      setPackBrowserMessage(`Selected ${pack.name}.`);
                      setCombinatorOutboxMessage(`${pack.name} is selected for the combinator.`);
                    }
                  }}
                  disabled={!savedAssetPacks.length}
                >
                  {savedAssetPacks.map((pack) => (
                    <option key={pack.id} value={pack.id}>
                      {formatAssetPackOption(pack)}
                    </option>
                  ))}
                  {!savedAssetPacks.length ? <option value="">No saved packs yet</option> : null}
                </select>
              </label>

              <label className="field">
                Asset
                <select
                  value={selectedBrowserAssetId}
                  onChange={(event) => setSelectedBrowserAssetId(event.target.value)}
                  disabled={!visiblePackAssets.length}
                >
                  <option value="">All backgrounds and objects</option>
                  {visiblePackAssets.map((asset) => (
                    <option key={asset.id} value={asset.id}>
                      {asset.title}
                    </option>
                  ))}
                </select>
              </label>

              <div className="asset-browser-filter" role="group" aria-label="Asset type filter">
                <button
                  className={assetBrowserFilter === 'all' ? 'is-active' : ''}
                  type="button"
                  onClick={() => setAssetBrowserFilter('all')}
                >
                  All
                </button>
                <button
                  className={assetBrowserFilter === 'background' ? 'is-active' : ''}
                  type="button"
                  onClick={() => setAssetBrowserFilter('background')}
                >
                  Backgrounds
                </button>
                <button
                  className={assetBrowserFilter === 'object' ? 'is-active' : ''}
                  type="button"
                  onClick={() => setAssetBrowserFilter('object')}
                >
                  Objects
                </button>
              </div>

              <div className="pack-browser-counts" aria-label="Visible asset counts">
                <span>{visibleBackgroundCount} backgrounds</span>
                <span>{visibleObjectCount} objects</span>
              </div>

              <button
                className="utility-button"
                type="button"
                onClick={() => void loadSavedAssetPacks()}
              >
                Refresh packs
              </button>
              <button
                className="danger-button"
                type="button"
                onClick={() => void deleteSelectedPack()}
                disabled={!selectedSavedPack || isPackActionRunning}
              >
                Delete pack
              </button>
              <p className="pack-browser-message">{packBrowserMessage}</p>
            </aside>

            <div className="pack-browser-scroll" aria-label="Background and object assets">
              {visiblePackAssets.length ? (
                visiblePackAssets.map((asset) => (
                  <button
                    className={
                      asset.id === selectedBrowserAssetId
                        ? 'pack-browser-asset is-selected'
                        : 'pack-browser-asset'
                    }
                    type="button"
                    key={asset.id}
                    ref={(element) => {
                      assetBrowserItemRefs.current[asset.id] = element;
                    }}
                    onClick={() => setSelectedBrowserAssetId(asset.id)}
                  >
                    <span className="asset-preview is-small" style={{ background: asset.previewTone }}>
                      {asset.imageUrl ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={asset.imageUrl} alt="" />
                      ) : null}
                    </span>
                    <span className="pack-browser-asset-name">{asset.title}</span>
                    <span className="pack-browser-kind">
                      {asset.kind === 'background' ? 'Background' : 'Object'}
                    </span>
                  </button>
                ))
              ) : (
                <div className="empty-state">No background or object assets ready for this pack.</div>
              )}
            </div>
          </div>
        ) : (
          <p className="muted">
            {selectedSavedPack
              ? `${selectedSavedPack.name} is selected. Expand to browse saved pack assets.`
              : 'Pack details and asset previews are hidden.'}
          </p>
        )}
      </section>

      <div className="asset-pack-grid">
        <section className="generation-surface asset-pack-creator">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Asset pack planner</p>
              <h3>Planner + creator</h3>
            </div>
            <button
              className="primary-button"
              type="button"
              onClick={() => void createPack()}
              disabled={actionDisabled}
            >
              {isPackActionRunning ? 'Working...' : 'Create pack'}
            </button>
          </div>

          <div className="planner-form">
            <label className="field">
              Name
              <input
                value={planner.name}
                onChange={(event) =>
                  setPlanner((current) => ({ ...current, name: event.target.value }))
                }
              />
            </label>
            <label className="field">
              Total asset count
              <input
                min="6"
                max="80"
                type="number"
                value={planner.totalAssetCount}
                onChange={(event) =>
                  setPlanner((current) => {
                    const totalAssetCount = Math.max(
                      1,
                      Number.parseInt(event.target.value || '0', 10),
                    );
                    const backgroundCount = Math.min(current.backgroundCount, totalAssetCount);
                    return {
                      ...current,
                      totalAssetCount,
                      backgroundCount,
                      objectCount: Math.max(0, totalAssetCount - backgroundCount),
                    };
                  })
                }
              />
            </label>
            <label className="field">
              Backgrounds
              <input
                min="0"
                max="80"
                type="number"
                value={planner.backgroundCount}
                onChange={(event) =>
                  setPlanner((current) => {
                    const backgroundCount = Math.max(
                      0,
                      Number.parseInt(event.target.value || '0', 10),
                    );
                    return {
                      ...current,
                      backgroundCount,
                      totalAssetCount: backgroundCount + current.objectCount,
                    };
                  })
                }
              />
            </label>
            <label className="field">
              Objects
              <input
                min="0"
                max="80"
                type="number"
                value={planner.objectCount}
                onChange={(event) =>
                  setPlanner((current) => {
                    const objectCount = Math.max(
                      0,
                      Number.parseInt(event.target.value || '0', 10),
                    );
                    return {
                      ...current,
                      objectCount,
                      totalAssetCount: current.backgroundCount + objectCount,
                    };
                  })
                }
              />
            </label>
            <label className="field">
              Quality
              <select
                value={planner.qualityLevel}
                onChange={(event) =>
                  setPlanner((current) => ({
                    ...current,
                    qualityLevel: event.target.value as AssetPackPlannerState['qualityLevel'],
                  }))
                }
              >
                <option value="lean">Lean</option>
                <option value="balanced">Balanced</option>
                <option value="premium">Premium</option>
              </select>
            </label>
            <label className="field">
              Format
              <select
                value={planner.format}
                onChange={(event) =>
                  setPlanner((current) => ({
                    ...current,
                    format: event.target.value as AssetPackPlannerState['format'],
                  }))
                }
              >
                <option value="proof reel">Proof reel</option>
                <option value="listicle">Listicle</option>
                <option value="product demo">Product demo</option>
                <option value="objection handling">Objection handling</option>
              </select>
            </label>
            <label className="field">
              Style
              <select
                value={planner.style}
                onChange={(event) =>
                  setPlanner((current) => ({
                    ...current,
                    style: event.target.value as AssetPackPlannerState['style'],
                  }))
                }
              >
                <option value="clean product">Clean product</option>
                <option value="ugc">UGC</option>
                <option value="cinematic">Cinematic</option>
                <option value="high contrast">High contrast</option>
              </select>
            </label>
            <label className="field">
              Provider
              <select
                value={planner.provider}
                onChange={(event) =>
                  setPlanner((current) => ({
                    ...current,
                    provider: event.target.value as AssetPackPlannerState['provider'],
                  }))
                }
              >
                <option value="runway">Runway</option>
              </select>
            </label>
            <label className="field">
              Model
              <select
                value={planner.model}
                onChange={(event) =>
                  setPlanner((current) => ({
                    ...current,
                    model: event.target.value as AssetPackPlannerState['model'],
                  }))
                }
              >
                <option value="gen4.5">Gen 4.5</option>
              </select>
            </label>
            <label className="field">
              Ratio
              <select
                value={planner.ratio}
                onChange={(event) =>
                  setPlanner((current) => ({
                    ...current,
                    ratio: event.target.value as AssetPackPlannerState['ratio'],
                  }))
                }
              >
                <option value="9:16">9:16</option>
                <option value="1:1">1:1</option>
                <option value="16:9">16:9</option>
              </select>
            </label>
          </div>
        </section>
      </div>

    </>
  );
}

function HookGenerationCanvas({
  generation,
  selectedItemId = null,
  mode = 'output',
  onPointerMove,
  onPointerUp,
  onPointerCancel,
  onPointerLeave,
  beginMove,
  beginResize,
  canvasRef,
}: {
  generation: SavedHookImageGeneration;
  selectedItemId?: string | null;
  mode?: 'output' | 'edit';
  onPointerMove?: (event: React.PointerEvent<HTMLElement>) => void;
  onPointerUp?: (event: React.PointerEvent<HTMLElement>) => void;
  onPointerCancel?: (event: React.PointerEvent<HTMLElement>) => void;
  onPointerLeave?: (event: React.PointerEvent<HTMLElement>) => void;
  beginMove?: (event: React.PointerEvent<HTMLButtonElement>, item: HookCanvasItem) => void;
  beginResize?: (event: React.PointerEvent<HTMLSpanElement>, item: HookCanvasItem) => void;
  canvasRef?: React.RefObject<HTMLDivElement | null>;
}) {
  const isEditable = mode === 'edit';
  return (
    <div
      className={`hook-canvas ${isEditable ? 'is-editing' : 'is-output'}`}
      ref={canvasRef}
      style={{ background: generation.background.previewTone }}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerCancel}
      onPointerLeave={onPointerLeave}
    >
      {generation.background.imageUrl ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          className="hook-canvas-background-image"
          src={generation.background.imageUrl}
          alt={generation.background.title}
        />
      ) : null}
      {isEditable && generation.items.length === 0 ? (
        <div className="hook-empty-state">Choose assets to place on this reel template.</div>
      ) : null}
      {generation.items.map((item) => {
        const showLabel = item.asset.kind === 'hook' || (isEditable && !item.asset.imageUrl);
        return (
          <button
            className={[
              'hook-canvas-item',
              item.asset.kind === 'hook' ? 'is-text' : 'is-visual',
              item.id === selectedItemId ? 'is-selected' : '',
            ]
              .filter(Boolean)
              .join(' ')}
            type="button"
            key={item.id}
            style={{
              '--layer-color': layerColorForItem(item),
              left: `${item.x}%`,
              top: `${item.y}%`,
              width: `${item.size}%`,
              background: item.asset.previewTone,
            } as React.CSSProperties & Record<'--layer-color', string>}
            onPointerDown={beginMove ? (event) => beginMove(event, item) : undefined}
            onPointerUp={onPointerUp}
            onPointerCancel={onPointerCancel}
            disabled={!isEditable || !beginMove}
          >
            {item.asset.imageUrl ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={item.asset.imageUrl} alt={item.asset.title} />
            ) : null}
            {showLabel ? <span>{item.asset.title}</span> : null}
            {item.id === selectedItemId && beginResize ? (
              <span
                className="hook-resize-handle"
                aria-hidden="true"
                onPointerDown={(event) => beginResize(event, item)}
                onPointerUp={onPointerUp}
                onPointerCancel={onPointerCancel}
              />
            ) : null}
          </button>
        );
      })}
    </div>
  );
}

export function HookImageCreator({
  orgId = DEFAULT_ORG_ID,
  selectedPage = null,
  onRunsChanged = () => undefined,
  compositionRuns = [],
  selectedRun = null,
  setSelectedRunId = () => undefined,
  savedHookGenerations = [],
  onSaveGeneration = () => undefined,
  setWorkspaceMessage = () => undefined,
}: {
  orgId?: string;
  selectedPage?: PageRecord | null;
  onRunsChanged?: () => void;
  compositionRuns?: RunRecord[];
  selectedRun?: RunRecord | null;
  setSelectedRunId?: (runId: string) => void;
  savedHookGenerations?: SavedHookImageGeneration[];
  onSaveGeneration?: (generation: SavedHookImageGeneration) => void;
  setWorkspaceMessage?: (message: string) => void;
}) {
  const seedBackgrounds = assetLibrarySeed.filter((asset) => asset.kind === 'background');
  const [activeGenerationId, setActiveGenerationId] = useState('new');
  const [generationName, setGenerationName] = useState('New hook image');
  const [selectedBackgroundId, setSelectedBackgroundId] = useState(bestAsset('background').id);
  const [customBackground, setCustomBackground] = useState<AssetLibraryItem | null>(null);
  const [items, setItems] = useState<HookCanvasItem[]>([]);
  const [selectedItemId, setSelectedItemId] = useState<string | null>(null);
  const [savedAssetPacks, setSavedAssetPacks] = useState<AssetPackRecord[]>([]);
  const [selectedAssetPackId, setSelectedAssetPackId] = useState('');
  const [selectedBrowserAssetId, setSelectedBrowserAssetId] = useState('');
  const [assetBrowserFilter, setAssetBrowserFilter] = useState<'all' | 'background' | 'object'>('all');
  const [packAssets, setPackAssets] = useState<AssetLibraryItem[]>([]);
  const [candidateCompositions, setCandidateCompositions] = useState<CandidateComposition[]>([]);
  const [compositionPickIndex, setCompositionPickIndex] = useState(0);
  const [isCombinatorRunning, setIsCombinatorRunning] = useState(false);
  const [combinatorMessage, setCombinatorMessage] = useState(
    'Choose an active saved pack to create a hook image on the canvas.',
  );
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const dragState = useRef<HookCanvasDragState | null>(null);
  const loadedDraftKey = useRef('');
  const assetBrowserItemRefs = useRef<Record<string, HTMLDivElement | null>>({});

  const savedForActive =
    savedHookGenerations.find((generation) => generation.id === activeGenerationId) ?? null;
  const selectedBackground =
    customBackground ??
    seedBackgrounds.find((asset) => asset.id === selectedBackgroundId) ??
    seedBackgrounds[0];
  const selectedItem = items.find((item) => item.id === selectedItemId) ?? null;
  const combinatorAssetPacks = savedAssetPacks.filter(isCombinatorEligibleAssetPack);
  const selectedCombinatorPack =
    combinatorAssetPacks.find((pack) => pack.id === selectedAssetPackId) ?? null;
  const combinatorLibrary = packAssets.length ? packAssets : assetLibrarySeed;
  const browserAssetPool = useMemo(
    () =>
      packAssets.filter(
        (asset) => asset.kind === 'background' || asset.kind === 'object' || asset.kind === 'hook',
      ),
    [packAssets],
  );
  const visiblePackAssets = useMemo(
    () =>
      assetBrowserFilter === 'all'
        ? browserAssetPool
        : browserAssetPool.filter((asset) =>
            assetBrowserFilter === 'background'
              ? asset.kind === 'background'
              : asset.kind === 'object' || asset.kind === 'hook',
          ),
    [assetBrowserFilter, browserAssetPool],
  );
  const visiblePackAssetIds = useMemo(
    () => visiblePackAssets.map((asset) => asset.id).join('|'),
    [visiblePackAssets],
  );
  const visibleBackgroundCount = browserAssetPool.filter((asset) => asset.kind === 'background').length;
  const visibleObjectCount = browserAssetPool.filter(
    (asset) => asset.kind === 'object' || asset.kind === 'hook',
  ).length;
  const compositionSeed = `${selectedCombinatorPack?.id ?? selectedPage?.id ?? orgId}:${compositionPickIndex}`;
  const selectedCandidate =
    candidateCompositions.length > 0
      ? candidateCompositions[compositionPickIndex % candidateCompositions.length]
      : null;
  const combinatorBackground =
    assetFromCandidateRole(selectedCandidate, 'background') ??
    pickAsset('background', compositionSeed, 0, combinatorLibrary);
  const combinatorObject =
    assetFromCandidateRole(selectedCandidate, 'foreground') ??
    assetFromCandidateRole(selectedCandidate, 'object') ??
    pickAsset('object', compositionSeed, 1, combinatorLibrary);
  const combinatorHook =
    assetFromCandidateRole(selectedCandidate, 'hook') ??
    syntheticHookAsset(selectedCombinatorPack, combinatorObject);
  const combinatorAudio =
    assetFromCandidateRole(selectedCandidate, 'audio') ??
    pickOptionalAsset('audio', compositionSeed, 3, combinatorLibrary);
  const combinatorVideo =
    assetFromCandidateRole(selectedCandidate, 'format') ??
    pickOptionalAsset('video', compositionSeed, 4, combinatorLibrary);
  const combinatorAssets = [
    combinatorBackground,
    combinatorObject,
    combinatorHook,
    combinatorAudio,
    combinatorVideo,
  ].filter((asset): asset is AssetLibraryItem => asset !== null);
  const combinatorScore = Math.round(
    combinatorAssets.reduce((sum, asset) => sum + asset.performanceScore, 0) /
      Math.max(1, combinatorAssets.length),
  );
  const currentGeneration: SavedHookImageGeneration = {
    id: activeGenerationId,
    sourceRunId: savedForActive?.sourceRunId ?? null,
    name: generationName,
    selectedBackgroundId: selectedBackground.id,
    background: selectedBackground,
    items,
    updatedAt: savedForActive?.updatedAt ?? new Date().toISOString(),
  };

  useEffect(() => {
    void loadSavedAssetPacks();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedPage?.id, orgId]);

  useEffect(() => {
    if (!selectedAssetPackId) {
      setPackAssets([]);
      setCandidateCompositions([]);
      setSelectedBrowserAssetId('');
      return;
    }
    void loadSelectedPackAssets(selectedAssetPackId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedAssetPackId, orgId]);

  useEffect(() => {
    if (
      selectedBrowserAssetId &&
      !visiblePackAssets.some((asset) => asset.id === selectedBrowserAssetId)
    ) {
      setSelectedBrowserAssetId('');
    }
  }, [selectedBrowserAssetId, visiblePackAssetIds, visiblePackAssets]);

  useEffect(() => {
    if (!selectedBrowserAssetId) {
      return;
    }
    assetBrowserItemRefs.current[selectedBrowserAssetId]?.scrollIntoView({
      block: 'nearest',
      inline: 'nearest',
    });
  }, [selectedBrowserAssetId]);

  useEffect(() => {
    if (activeGenerationId === 'new') {
      return;
    }
    const generation = editableHookGenerationForId({
      generationId: activeGenerationId,
      compositionRuns,
      savedHookGenerations,
      orgId,
    });
    if (generation) {
      const draftKey = `${generation.id}:${generation.updatedAt}:${generation.name}`;
      if (loadedDraftKey.current === draftKey) {
        return;
      }
      loadedDraftKey.current = draftKey;
      loadGenerationDraft(generation);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeGenerationId, compositionRuns, savedHookGenerations]);

  useEffect(() => {
    if (selectedRun && activeGenerationId === 'new') {
      setActiveGenerationId(selectedRun.id);
    }
  }, [activeGenerationId, selectedRun]);

  async function loadSavedAssetPacks(preferredPackId?: string): Promise<AssetPackRecord[]> {
    try {
      const response = await fetch(`/api/orgs/${orgId}/asset-packs?limit=50`, {
        cache: 'no-store',
        headers: { 'X-Actor-Id': 'operator:ui-rebuild' },
      });
      if (!response.ok) {
        throw new Error(await apiErrorMessage(response));
      }
      const packs = ((await response.json()) as AssetPackRecord[]).filter(
        (pack) => pack.status !== 'rejected' && pack.status !== 'archived',
      );
      setSavedAssetPacks(packs);
      const fallbackPackId =
        packs.find(isCombinatorEligibleAssetPack)?.id ?? packs[0]?.id ?? '';
      setSelectedAssetPackId(preferredPackId || selectedAssetPackId || fallbackPackId);
      return packs;
    } catch (error) {
      setCombinatorMessage(
        error instanceof Error ? error.message : 'Could not load saved asset packs.',
      );
      return [];
    }
  }

  async function loadSelectedPackAssets(assetPackId: string): Promise<AssetLibraryItem[]> {
    try {
      setCombinatorMessage('Loading selected pack assets...');
      const assetsResponse = await fetch(
        `/api/orgs/${orgId}/assets?asset_pack_id=${assetPackId}&ready_status=ready&limit=200`,
        {
          cache: 'no-store',
          headers: { 'X-Actor-Id': 'operator:ui-rebuild' },
        },
      );
      if (!assetsResponse.ok) {
        throw new Error(await apiErrorMessage(assetsResponse));
      }
      const assetRows = (await assetsResponse.json()) as AssetLibraryItemOut[];
      const mappedAssets = assetRows.map((row) => mapAssetLibraryItemOut(row, orgId));
      setPackAssets(mappedAssets);

      const combinationsResponse = await fetch(
        `/api/orgs/${orgId}/asset-packs/${assetPackId}/combinations`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-Actor-Id': 'operator:ui-rebuild',
          },
          body: JSON.stringify({
            target_reel_count: 12,
            mode: 'balanced',
            filters: {},
          }),
        },
      );
      if (combinationsResponse.ok) {
        const combinations = (await combinationsResponse.json()) as AssetPackCombinationsResponse;
        setCandidateCompositions(combinations.candidate_compositions);
        setCombinatorMessage(
          combinations.candidate_compositions.length
            ? `Loaded ${combinations.candidate_compositions.length} combinations from ${combinations.asset_pack.name}.`
            : `${combinations.asset_pack.name} has no backend combinations; the canvas will use its ready assets with generated hook text.`,
        );
      } else {
        setCandidateCompositions([]);
        setCombinatorMessage(
          `Loaded pack assets, but backend combinations are unavailable: ${await apiErrorMessage(
            combinationsResponse,
          )}`,
        );
      }
      return mappedAssets;
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Could not load pack assets.';
      setPackAssets([]);
      setCandidateCompositions([]);
      setCombinatorMessage(message);
      return [];
    }
  }

  async function approveCombinatorPack(pack: AssetPackRecord): Promise<AssetPackRecord> {
    if (pack.status === 'approved' || pack.status === 'ready' || pack.status === 'generating') {
      return pack;
    }
    if (pack.status !== 'planned') {
      throw new Error(`Asset pack is ${pack.status}; choose a planned or active pack.`);
    }
    const response = await fetch(`/api/orgs/${orgId}/asset-packs/${pack.id}/approve`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Actor-Id': 'operator:ui-rebuild',
      },
      body: JSON.stringify({
        note: 'Approved from live hook image creator.',
        metadata: { source: 'web_live_hook_image_creator' },
      }),
    });
    if (!response.ok) {
      throw new Error(await apiErrorMessage(response));
    }
    const approved = (await response.json()) as AssetPackRecord;
    await loadSavedAssetPacks(approved.id);
    return approved;
  }

  async function queueCombinatorRender() {
    if (!selectedPage || !selectedCombinatorPack) {
      setCombinatorMessage('Choose an active saved pack first.');
      return;
    }
    setIsCombinatorRunning(true);
    setWorkspaceMessage('Creating asset-led hook image...');
    setCombinatorMessage('Creating selected hook image composition...');
    try {
      const approved = await approveCombinatorPack(selectedCombinatorPack);
      const backgroundCount = packAssets.filter((asset) => asset.kind === 'background').length;
      const objectCount = packAssets.filter((asset) => asset.kind === 'object').length;
      const planner: AssetPackPlannerState = {
        name: approved.name,
        totalAssetCount: approved.requested_asset_count ?? Math.max(1, packAssets.length),
        backgroundCount,
        objectCount,
        qualityLevel: 'balanced',
        format: 'proof reel',
        style: 'clean product',
        provider: 'runway',
        model: 'gen4.5',
        ratio: '9:16',
      };
      const baseCompositionManifest =
        selectedCandidate?.composition_manifest ??
        buildCompositionManifest({
          assetPackId: approved.id,
          assetPackName: approved.name,
          planner,
          selectedBackground: combinatorBackground,
          selectedObject: combinatorObject,
          selectedHook: combinatorHook,
          selectedAudio: combinatorAudio,
          selectedVideo: combinatorVideo,
          outputScore: combinatorScore,
        });
      const compositionManifest = withHookLayoutIntent({
        manifest: baseCompositionManifest,
        selectedBackground: combinatorBackground,
        selectedObject: combinatorObject,
        selectedHook: combinatorHook,
      });
      const response = await fetch(
        `/api/orgs/${orgId}/asset-packs/${approved.id}/composition-renders`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-Actor-Id': 'operator:ui-rebuild',
          },
          body: JSON.stringify({
            page_id: selectedPage.id,
            composition_manifest: compositionManifest,
            render_mode: 'preview',
            dry_run: true,
            idempotency_key: `hook-image-creator:${approved.id}:${Date.now()}`,
            metadata: {
              source: 'web_live_hook_image_creator',
              page_id: selectedPage.id,
            },
          }),
        },
      );
      if (!response.ok) {
        throw new Error(await apiErrorMessage(response));
      }
      const submitted = (await response.json()) as AssetPackRenderResponse;
      setSelectedRunId(submitted.run_id);
      setActiveGenerationId(submitted.run_id);
      setGenerationName(`${approved.name} hook image`);
      setSelectedBackgroundId(combinatorBackground.id);
      setCustomBackground(
        seedBackgrounds.some((asset) => asset.id === combinatorBackground.id)
          ? null
          : combinatorBackground,
      );
      const editorItems = asRecord(compositionManifest.editor_state)?.items;
      setItems(
        (Array.isArray(editorItems) ? editorItems : [])
          .map(asHookCanvasItem)
          .filter((item): item is HookCanvasItem => item !== null),
      );
      setSelectedItemId(null);
      setCompositionPickIndex((current) => current + 1);
      setCombinatorMessage(`Created hook image ${submitted.run_id.slice(0, 8)} on the canvas.`);
      setWorkspaceMessage(`Created asset-led hook image ${submitted.run_id.slice(0, 8)}.`);
      onRunsChanged();
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Could not create hook image.';
      setCombinatorMessage(message);
      setWorkspaceMessage(message);
    } finally {
      setIsCombinatorRunning(false);
    }
  }

  function loadGenerationDraft(generation: SavedHookImageGeneration) {
    setGenerationName(generation.name);
    setSelectedBackgroundId(generation.selectedBackgroundId);
    setCustomBackground(
      seedBackgrounds.some((asset) => asset.id === generation.background.id)
        ? null
        : generation.background,
      );
    setItems(generation.items);
    setSelectedItemId(null);
  }

  function handleGenerationChange(generationId: string) {
    setActiveGenerationId(generationId);
    if (generationId === 'new') {
      setGenerationName('New hook image');
      setSelectedBackgroundId(bestAsset('background').id);
      setCustomBackground(null);
      setItems([]);
      setSelectedItemId(null);
      return;
    }
    const generation = editableHookGenerationForId({
      generationId,
      compositionRuns,
      savedHookGenerations,
      orgId,
    });
    if (generation) {
      loadedDraftKey.current = `${generation.id}:${generation.updatedAt}:${generation.name}`;
      loadGenerationDraft(generation);
      if (generation.sourceRunId) {
        setSelectedRunId(generation.sourceRunId);
      }
      return;
    }
  }

  function addItem(asset: AssetLibraryItem) {
    const siblingCount = items.filter((item) => item.asset.id === asset.id).length;
    const nextItem: HookCanvasItem = {
      id: `${asset.id}-${Date.now()}-${siblingCount}`,
      asset,
      x: Math.min(72, 26 + siblingCount * 7),
      y: Math.min(76, asset.kind === 'hook' ? 14 + siblingCount * 7 : 50 + siblingCount * 5),
      size: asset.kind === 'hook' ? 42 : 34,
    };
    setItems((current) => [...current, nextItem]);
    setSelectedItemId(nextItem.id);
  }

  function setCanvasBackground(asset: AssetLibraryItem) {
    setSelectedBackgroundId(asset.id);
    setCustomBackground(
      seedBackgrounds.some((seedAsset) => seedAsset.id === asset.id) ? null : asset,
    );
    setSelectedItemId(null);
  }

  function removeItemsForAsset(assetId: string) {
    setItems((current) => current.filter((item) => item.asset.id !== assetId));
    setSelectedItemId((current) => {
      if (!current) {
        return null;
      }
      const selectedRemoved = items.some((item) => item.id === current && item.asset.id === assetId);
      return selectedRemoved ? null : current;
    });
  }

  function handleLiveAssetAction(asset: AssetLibraryItem) {
    setSelectedBrowserAssetId(asset.id);
    if (asset.kind === 'background') {
      setCanvasBackground(asset);
      return;
    }
    addItem(asset);
  }

  function updateSelectedItemSize(size: number) {
    if (!selectedItemId) {
      return;
    }
    setItems((current) =>
      current.map((item) =>
        item.id === selectedItemId ? { ...item, size: clamp(size, 16, 76) } : item,
      ),
    );
  }

  function deleteSelectedItem() {
    if (!selectedItemId) {
      return;
    }
    setItems((current) => current.filter((item) => item.id !== selectedItemId));
    setSelectedItemId(null);
  }

  function resetCanvas() {
    setItems([]);
    setSelectedItemId(null);
  }

  async function saveGeneration() {
    const sourceRunId = compositionRuns.some((run) => run.id === activeGenerationId)
      ? activeGenerationId
      : (savedForActive?.sourceRunId ?? null);
    const id =
      activeGenerationId !== 'new'
        ? activeGenerationId
        : `local-hook:${selectedPage?.id ?? orgId}:${Date.now()}`;
    const name = generationName.trim() || 'Untitled hook image';
    const nextGeneration: SavedHookImageGeneration = {
      id,
      sourceRunId,
      name,
      selectedBackgroundId: selectedBackground.id,
      background: selectedBackground,
      items,
      updatedAt: new Date().toISOString(),
    };
    onSaveGeneration(nextGeneration);
    setActiveGenerationId(id);
    setGenerationName(name);
    setWorkspaceMessage(`${name} saved.`);
    if (sourceRunId) {
      await syncHookGenerationToRun(orgId, sourceRunId, nextGeneration);
    }
  }

  function beginMove(event: React.PointerEvent<HTMLButtonElement>, item: HookCanvasItem) {
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    setSelectedItemId(item.id);
    dragState.current = {
      itemId: item.id,
      mode: 'move',
      pointerStartX: event.clientX,
      pointerStartY: event.clientY,
      itemStartX: item.x,
      itemStartY: item.y,
    };
  }

  function beginResize(event: React.PointerEvent<HTMLSpanElement>, item: HookCanvasItem) {
    event.preventDefault();
    event.stopPropagation();
    event.currentTarget.setPointerCapture(event.pointerId);
    setSelectedItemId(item.id);
    dragState.current = {
      itemId: item.id,
      mode: 'resize',
      pointerStartX: event.clientX,
      pointerStartY: event.clientY,
      itemStartSize: item.size,
    };
  }

  function continuePointer(event: React.PointerEvent<HTMLElement>) {
    const currentDrag = dragState.current;
    const canvas = canvasRef.current;
    if (!currentDrag || !canvas) {
      return;
    }

    const rect = canvas.getBoundingClientRect();
    if (currentDrag.mode === 'move') {
      const deltaX = ((event.clientX - currentDrag.pointerStartX) / rect.width) * 100;
      const deltaY = ((event.clientY - currentDrag.pointerStartY) / rect.height) * 100;
      setItems((current) =>
        current.map((item) =>
          item.id === currentDrag.itemId
            ? {
                ...item,
                x: clamp(currentDrag.itemStartX + deltaX, 4, 96),
                y: clamp(currentDrag.itemStartY + deltaY, 4, 96),
              }
            : item,
        ),
      );
      return;
    }

    const delta = ((event.clientX - currentDrag.pointerStartX) / rect.width) * 100;
    setItems((current) =>
      current.map((item) =>
        item.id === currentDrag.itemId
          ? { ...item, size: clamp(currentDrag.itemStartSize + delta, 16, 76) }
          : item,
      ),
    );
  }

  function endPointer() {
    dragState.current = null;
  }

  return (
    <section className="output-surface hook-creator">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Live hook image creator</p>
          <h3>Reel hook image</h3>
        </div>
        <span className="status-pill">
          {activeGenerationId === 'new' ? 'New image' : 'Editable generation'}
        </span>
      </div>

      <div className="hook-creator-layout">
        <div className="hook-controls">
          <div className="hook-control-group">
            <div className="section-heading is-compact">
              <div>
                <h4>Live asset browser</h4>
                <p className="muted">Browse the selected pack and place assets on the live canvas.</p>
              </div>
            </div>
            <label className="field">
              Pack
              <select
                value={selectedAssetPackId}
                onChange={(event) => {
                  setSelectedAssetPackId(event.target.value);
                  setSelectedBrowserAssetId('');
                }}
                disabled={!savedAssetPacks.length}
              >
                {!savedAssetPacks.length ? <option value="">No saved packs yet</option> : null}
                {savedAssetPacks.map((pack) => (
                  <option key={pack.id} value={pack.id}>
                    {formatAssetPackOption(pack)}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              Asset
              <select
                value={selectedBrowserAssetId}
                onChange={(event) => setSelectedBrowserAssetId(event.target.value)}
                disabled={!visiblePackAssets.length}
              >
                <option value="">All backgrounds and objects</option>
                {visiblePackAssets.map((asset) => (
                  <option key={asset.id} value={asset.id}>
                    {asset.title}
                  </option>
                ))}
              </select>
            </label>
            <div className="asset-browser-filter" role="group" aria-label="Live asset type filter">
              <button
                className={assetBrowserFilter === 'all' ? 'is-active' : ''}
                type="button"
                onClick={() => setAssetBrowserFilter('all')}
              >
                All
              </button>
              <button
                className={assetBrowserFilter === 'background' ? 'is-active' : ''}
                type="button"
                onClick={() => setAssetBrowserFilter('background')}
              >
                Backgrounds
              </button>
              <button
                className={assetBrowserFilter === 'object' ? 'is-active' : ''}
                type="button"
                onClick={() => setAssetBrowserFilter('object')}
              >
                Objects
              </button>
            </div>

            <div className="pack-browser-counts" aria-label="Live asset counts">
              <span>{visibleBackgroundCount} backgrounds</span>
              <span>{visibleObjectCount} objects</span>
            </div>

            <div className="review-actions">
              <button
                className="utility-button"
                type="button"
                onClick={() => void loadSavedAssetPacks()}
              >
                Refresh packs
              </button>
            </div>

            <div className="pack-browser-scroll live-pack-browser-scroll" aria-label="Live background and object assets">
              {visiblePackAssets.length ? (
                visiblePackAssets.map((asset) => {
                  const canvasCount = items.filter((item) => item.asset.id === asset.id).length;
                  const isSelected = asset.id === selectedBrowserAssetId;
                  return (
                    <div
                      className={
                        isSelected
                          ? 'pack-browser-asset live-browser-asset is-selected'
                          : 'pack-browser-asset live-browser-asset'
                      }
                      key={asset.id}
                      ref={(element) => {
                        assetBrowserItemRefs.current[asset.id] = element;
                      }}
                    >
                      <button
                        className="live-browser-select"
                        type="button"
                        onClick={() => handleLiveAssetAction(asset)}
                      >
                        <span className="asset-preview is-small" style={{ background: asset.previewTone }}>
                          {asset.imageUrl ? (
                            // eslint-disable-next-line @next/next/no-img-element
                            <img src={asset.imageUrl} alt="" />
                          ) : null}
                        </span>
                        <span className="pack-browser-asset-name">{asset.title}</span>
                        <span className="pack-browser-kind">
                          {asset.kind === 'background'
                            ? 'Background'
                            : asset.kind === 'hook'
                              ? 'Hook'
                              : 'Object'}
                        </span>
                      </button>
                      <div className="live-browser-actions">
                        <button
                          className={asset.kind === 'background' ? 'utility-button' : 'primary-button'}
                          type="button"
                          onClick={() => handleLiveAssetAction(asset)}
                        >
                          {asset.kind === 'background' ? 'Set background' : 'Add to canvas'}
                        </button>
                        {asset.kind !== 'background' && canvasCount > 0 ? (
                          <button
                            className="danger-button"
                            type="button"
                            onClick={() => removeItemsForAsset(asset.id)}
                          >
                            Remove from canvas
                          </button>
                        ) : null}
                      </div>
                    </div>
                  );
                })
              ) : (
                <div className="empty-state">No background or object assets ready for this pack.</div>
              )}
            </div>
          </div>

          <div className="hook-control-group">
            <div className="section-heading is-compact">
              <div>
                <h4>Selection</h4>
                <p className="muted">
                  {selectedItem ? selectedItem.asset.title : 'Select an item on the template.'}
                </p>
              </div>
            </div>
            <label className="field">
              Size
              <input
                min="16"
                max="76"
                type="range"
                value={selectedItem?.size ?? 34}
                disabled={!selectedItem}
                onChange={(event) =>
                  updateSelectedItemSize(Number.parseInt(event.target.value, 10))
                }
              />
            </label>
            <div className="review-actions">
              <button
                className="danger-button"
                type="button"
                onClick={deleteSelectedItem}
                disabled={!selectedItem}
              >
                Delete asset
              </button>
              <button
                className="utility-button"
                type="button"
                onClick={resetCanvas}
                disabled={items.length === 0}
              >
                Reset local image
              </button>
            </div>
          </div>

          <div className="hook-control-group">
            <div className="section-heading is-compact">
              <div>
                <h4>Asset combinator</h4>
                <p className="muted">{combinatorMessage}</p>
              </div>
            </div>
            <label className="field">
              Saved pack
              <select
                value={selectedCombinatorPack?.id ?? ''}
                onChange={(event) => setSelectedAssetPackId(event.target.value)}
                disabled={!combinatorAssetPacks.length}
              >
                {!combinatorAssetPacks.length ? (
                  <option value="">No active packs available</option>
                ) : null}
                {combinatorAssetPacks.length && !selectedCombinatorPack ? (
                  <option value="">Choose an active pack</option>
                ) : null}
                {combinatorAssetPacks.map((pack) => (
                  <option key={pack.id} value={pack.id}>
                    {formatAssetPackOption(pack)}
                  </option>
                ))}
              </select>
            </label>
            <div className="live-combinator-score">
              <span>Score</span>
              <strong>{combinatorScore}</strong>
            </div>
            <div className="review-actions">
              <button
                className="utility-button"
                type="button"
                onClick={() => void loadSavedAssetPacks()}
              >
                Refresh packs
              </button>
              <button
                className="primary-button"
                type="button"
                onClick={() => void queueCombinatorRender()}
                disabled={isCombinatorRunning || !selectedCombinatorPack || !selectedPage}
              >
                {isCombinatorRunning ? 'Working...' : 'Create on canvas'}
              </button>
            </div>
          </div>
        </div>

        <div className="hook-canvas-wrap">
          <HookGenerationCanvas
            generation={currentGeneration}
            mode="edit"
            selectedItemId={selectedItemId}
            onPointerMove={continuePointer}
            onPointerUp={endPointer}
            onPointerCancel={endPointer}
            onPointerLeave={endPointer}
            beginMove={beginMove}
            beginResize={beginResize}
            canvasRef={canvasRef}
          />
          <div className="hook-canvas-contents" aria-label="Canvas contents">
            <button
              className={!selectedItemId ? 'hook-canvas-chip is-selected is-background' : 'hook-canvas-chip is-background'}
              type="button"
              onClick={() => setSelectedItemId(null)}
            >
              <span className="asset-preview is-small" style={{ background: selectedBackground.previewTone }}>
                {selectedBackground.imageUrl ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={selectedBackground.imageUrl} alt="" />
                ) : null}
              </span>
              <span>
                <strong>Background</strong>
                <small>{selectedBackground.title}</small>
              </span>
            </button>
            {items.map((item) => (
              <div
                className={
                  item.id === selectedItemId ? 'hook-canvas-chip is-selected' : 'hook-canvas-chip'
                }
                key={item.id}
              >
                <button type="button" onClick={() => setSelectedItemId(item.id)}>
                  <span className="asset-preview is-small" style={{ background: item.asset.previewTone }}>
                    {item.asset.imageUrl ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={item.asset.imageUrl} alt="" />
                    ) : null}
                  </span>
                  <span>
                    <strong>{item.asset.kind === 'hook' ? 'Hook' : 'Object'}</strong>
                    <small>{item.asset.title}</small>
                  </span>
                </button>
                <button
                  className="hook-canvas-chip-remove"
                  type="button"
                  aria-label={`Remove ${item.asset.title}`}
                  onClick={() => {
                    setItems((current) => current.filter((candidate) => candidate.id !== item.id));
                    setSelectedItemId((current) => (current === item.id ? null : current));
                  }}
                >
                  Remove
                </button>
              </div>
            ))}
          </div>
          <div className="hook-save-panel">
            <label className="field">
              Existing saved image
              <select
                value={activeGenerationId}
                onChange={(event) => handleGenerationChange(event.target.value)}
              >
                <option value="new">Create new hook image</option>
                {compositionRuns.map((run) => (
                  <option key={run.id} value={run.id}>
                    {formatGeneratedRunOption(run, savedHookGenerations)}
                  </option>
                ))}
                {savedHookGenerations
                  .filter((generation) => !generation.sourceRunId)
                  .map((generation) => (
                    <option key={generation.id} value={generation.id}>
                      {generation.name} - saved
                    </option>
                  ))}
              </select>
            </label>
            <label className="field">
              Name
              <input
                value={generationName}
                onChange={(event) => setGenerationName(event.target.value)}
                onBlur={() => void saveGeneration()}
              />
            </label>
            <button
              className="primary-button"
              type="button"
              onClick={() => void saveGeneration()}
            >
              Save image
            </button>
            <button
              className="utility-button"
              type="button"
              onClick={() => handleGenerationChange('new')}
            >
              Create blank/new
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}

function hookGenerationForRun(
  run: RunRecord,
  savedHookGenerations: SavedHookImageGeneration[],
  orgId: string,
): SavedHookImageGeneration {
  const runGeneration = buildHookGenerationFromRun(run, orgId);
  const savedGeneration =
    savedHookGenerations.find((generation) => generation.sourceRunId === run.id) ??
    savedHookGenerations.find((generation) => generation.id === run.id);
  return savedGeneration
    ? mergeRunHookGenerationWithSaved(runGeneration, savedGeneration)
    : runGeneration;
}

function editableHookGenerationForId({
  generationId,
  compositionRuns,
  savedHookGenerations,
  orgId,
}: {
  generationId: string;
  compositionRuns: RunRecord[];
  savedHookGenerations: SavedHookImageGeneration[];
  orgId: string;
}): SavedHookImageGeneration | null {
  const run =
    compositionRuns.find((candidate) => candidate.id === generationId) ??
    compositionRuns.find((candidate) =>
      savedHookGenerations.some(
        (generation) =>
          generation.id === generationId && generation.sourceRunId === candidate.id,
      ),
    );
  if (run) {
    return hookGenerationForRun(run, savedHookGenerations, orgId);
  }
  return savedHookGenerations.find((generation) => generation.id === generationId) ?? null;
}

function mergeRunHookGenerationWithSaved(
  runGeneration: SavedHookImageGeneration,
  savedGeneration: SavedHookImageGeneration,
): SavedHookImageGeneration {
  const mergedItems = mergeRunItemsWithSavedGeometry(runGeneration.items, savedGeneration.items);
  return {
    ...runGeneration,
    id: savedGeneration.id,
    sourceRunId: savedGeneration.sourceRunId ?? runGeneration.sourceRunId,
    name: savedGeneration.name || runGeneration.name,
    selectedBackgroundId: runGeneration.background.id,
    background: runGeneration.background,
    items: mergedItems,
    updatedAt:
      savedGeneration.updatedAt > runGeneration.updatedAt
        ? savedGeneration.updatedAt
        : runGeneration.updatedAt,
  };
}

function mergeRunItemsWithSavedGeometry(
  runItems: HookCanvasItem[],
  savedItems: HookCanvasItem[],
): HookCanvasItem[] {
  const mergedItems = savedItems.map((savedItem, index) => {
    const runItem =
      runItems.find((item) => item.id === savedItem.id) ??
      runItems.find((item) => item.asset.kind === savedItem.asset.kind) ??
      runItems[index];
    if (!runItem) {
      return savedItem;
    }
    return {
      ...savedItem,
      asset: runItem.asset,
    };
  });
  runItems.forEach((runItem) => {
    if (!mergedItems.some((item) => item.id === runItem.id || item.asset.kind === runItem.asset.kind)) {
      mergedItems.push(runItem);
    }
  });
  return mergedItems;
}

function buildHookGenerationFromRun(run: RunRecord, orgId: string): SavedHookImageGeneration {
  const cover = hookCoverPayload(run);
  const editorState = asRecord(cover?.editor_state);
  const layout = asRecord(cover?.layout);
  const editorItems = Array.isArray(editorState?.items)
    ? editorState.items.map(asHookCanvasItem).filter((item) => item !== null)
    : null;
  const roles = asRecord(cover?.roles) ?? {};
  const background = assetFromCoverRole(asRecord(roles.background), 'background', run.id, orgId);
  const foreground = assetFromCoverRole(asRecord(roles.foreground), 'object', run.id, orgId);
  const hookText = textValue(cover?.hook) ?? textValue(cover?.title) ?? 'Hook cover';
  const hookAsset: AssetLibraryItem = {
    id: `run-hook:${run.id}`,
    title: hookText,
    kind: 'hook',
    mediaType: 'text',
    pack: textValue(asRecord(run.input_params?.composition_manifest)?.asset_pack_name) ?? 'Combinator',
    tags: ['generated-hook'],
    layerSuitability: 'Opening caption',
    reuseCount: 0,
    performanceScore: 80,
    previewTone: 'linear-gradient(135deg, #101827, #f97316)',
  };
  const defaultLayout = intentionalHookLayout({
    seed: textValue(cover?.composition_id) ?? run.id,
    hookText,
    foreground,
  });
  const foregroundLayout = asRecord(layout?.foreground);
  const hookLayout = asRecord(layout?.hook);
  const defaultItems = [
    foreground
      ? {
          id: `run-object:${run.id}`,
          asset: foreground,
          x: numericValue(foregroundLayout?.x) ?? defaultLayout.foreground.x,
          y: numericValue(foregroundLayout?.y) ?? defaultLayout.foreground.y,
          size: numericValue(foregroundLayout?.size) ?? defaultLayout.foreground.size,
        }
      : null,
    {
      id: `run-copy:${run.id}`,
      asset: hookAsset,
      x: numericValue(hookLayout?.x) ?? defaultLayout.hook.x,
      y: numericValue(hookLayout?.y) ?? defaultLayout.hook.y,
      size: numericValue(hookLayout?.size) ?? defaultLayout.hook.size,
    },
  ].filter((item): item is HookCanvasItem => item !== null);
  const items = editorItems ? mergeRunItemsWithSavedGeometry(defaultItems, editorItems) : defaultItems;
  const title =
    textValue(cover?.title) ??
    textValue(asRecord(run.input_params?.composition_manifest)?.title) ??
    `Output ${run.id.slice(0, 8)}`;
  return {
    id: run.id,
    sourceRunId: run.id,
    name: title,
    selectedBackgroundId: background.id,
    background,
    items,
    updatedAt: run.updated_at,
  };
}

function assetFromCoverRole(
  role: Record<string, unknown> | null,
  fallbackKind: AssetLibraryKind,
  runId: string,
  orgId: string,
): AssetLibraryItem {
  const metadata = asRecord(role?.metadata);
  const title =
    textValue(role?.title) ??
    textValue(metadata?.title) ??
    (fallbackKind === 'background' ? 'Generated background' : 'Generated foreground');
  const assetId = textValue(role?.asset_id) ?? textValue(role?.id) ?? `${fallbackKind}:${runId}`;
  const kind = roleToLibraryKind(
    fallbackKind === 'object' ? 'foreground' : fallbackKind,
    textValue(role?.asset_kind) ?? fallbackKind,
  );
  return {
    id: `${fallbackKind === 'background' ? 'run-bg' : 'run-asset'}:${assetId}`,
    title,
    kind,
    mediaType: textValue(metadata?.media_type) ?? 'asset',
    pack: textValue(metadata?.asset_pack_niche) ?? 'Combinator output',
    tags: stringList(metadata?.tags),
    layerSuitability: textValue(metadata?.category) ?? 'Generated layer',
    reuseCount: 0,
    performanceScore: Math.round((numericValue(role?.performance_score) ?? 0.78) * 100),
    previewTone: assetPreviewTone(role, previewToneForAsset(assetId, kind, title)),
    imageUrl: stableAssetImageUrl(orgId, assetId) ?? assetImageUrl(role) ?? undefined,
    storageUri: textValue(role?.storage_uri) ?? textValue(metadata?.storage_uri) ?? undefined,
  };
}

function intentionalHookLayout({
  seed,
  hookText,
  foreground,
}: {
  seed: string;
  hookText: string;
  foreground: AssetLibraryItem;
}): {
  foreground: { x: number; y: number; size: number };
  hook: { x: number; y: number; size: number };
  intent: string;
} {
  const variant = hashString(`${seed}:${hookText}:${foreground.id}`) % 4;
  const hookLength = hookText.length;
  const hookSize = hookLength > 42 ? 58 : hookLength > 26 ? 54 : 48;
  const layouts = [
    {
      foreground: { x: 66, y: 64, size: 56 },
      hook: { x: 42, y: 24, size: hookSize },
      intent: 'subject-low-right_hook-upper-left',
    },
    {
      foreground: { x: 36, y: 66, size: 58 },
      hook: { x: 58, y: 25, size: hookSize },
      intent: 'subject-low-left_hook-upper-right',
    },
    {
      foreground: { x: 68, y: 42, size: 52 },
      hook: { x: 42, y: 74, size: hookSize },
      intent: 'subject-mid-right_hook-lower-left',
    },
    {
      foreground: { x: 50, y: 67, size: 62 },
      hook: { x: 50, y: 22, size: hookSize },
      intent: 'subject-bottom-center_hook-top-center',
    },
  ];
  return layouts[variant];
}

async function syncHookGenerationToRun(
  orgId: string,
  runId: string,
  generation: SavedHookImageGeneration,
) {
  try {
    await fetch(`/api/orgs/${orgId}/runs/${runId}/hook-cover`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        'X-Actor-Id': 'operator:ui-rebuild',
      },
      body: JSON.stringify({
        title: generation.name,
        editor_state: {
          selected_background_id: generation.selectedBackgroundId,
          background: generation.background,
          items: generation.items,
          updated_at: generation.updatedAt,
        },
      }),
    });
  } catch {
    // Local persistence still keeps the editor and asset-pack tab in sync.
  }
}

function bestAsset(kind: AssetLibraryKind, library: AssetLibraryItem[] = assetLibrarySeed): AssetLibraryItem {
  return [...library]
    .filter((asset) => asset.kind === kind)
    .sort((left, right) => right.performanceScore - left.performanceScore)[0] ?? assetLibrarySeed[0];
}

function pickAsset(
  kind: AssetLibraryKind,
  seed: string,
  offset: number,
  library: AssetLibraryItem[] = assetLibrarySeed,
): AssetLibraryItem {
  const assets = [...library]
    .filter((asset) => asset.kind === kind)
    .sort((left, right) => right.performanceScore - left.performanceScore);
  if (!assets.length) {
    return bestAsset(kind);
  }
  return assets[(hashString(`${seed}:${kind}:${offset}`) + offset) % assets.length];
}

function pickOptionalAsset(
  kind: AssetLibraryKind,
  seed: string,
  offset: number,
  library: AssetLibraryItem[],
): AssetLibraryItem | null {
  const assets = library.filter((asset) => asset.kind === kind);
  if (!assets.length) {
    return null;
  }
  return pickAsset(kind, seed, offset, assets);
}

function assetFromCandidateRole(
  candidate: CandidateComposition | null,
  role: string,
): AssetLibraryItem | null {
  const asset = candidate?.roles[role];
  if (!asset) {
    return null;
  }
  return mapCandidateAssetToLibraryItem(asset, role);
}

function mapAssetLibraryItemOut(row: AssetLibraryItemOut, orgId: string = DEFAULT_ORG_ID): AssetLibraryItem {
  const metadata = row.metadata ?? {};
  const intent = asRecord(metadata.intent);
  const request = asRecord(intent?.request);
  const requestMetadata = asRecord(request?.metadata);
  const title =
    textValue(metadata.title) ??
    textValue(requestMetadata?.title) ??
    textValue(metadata.pack_role) ??
    row.asset_kind ??
    row.id.slice(0, 8);
  const packName = textValue(metadata.asset_pack_niche) ?? row.niche ?? 'Selected pack';
  const tags = row.tags.length ? row.tags : stringList(metadata.tags);
  return {
    id: row.id,
    title,
    kind: assetKindToLibraryKind(row.asset_kind),
    mediaType: row.media_type ?? 'image',
    pack: packName,
    tags: tags.length ? tags : [row.source],
    layerSuitability: row.has_transparency ? 'Transparent overlay' : 'Reusable source asset',
    reuseCount: row.reuse_count,
    performanceScore: Math.round((row.performance_score ?? numericValue(metadata.performance_score) ?? 0.72) * 100),
    previewTone: previewToneForAsset(row.id, row.asset_kind, title),
    imageUrl: stableAssetImageUrl(orgId, row.id) ?? proxiedDownloadUrl(row.download?.url),
    storageUri: row.storage_uri,
  };
}

function mapCandidateAssetToLibraryItem(
  asset: CandidateCompositionAsset,
  role: string,
): AssetLibraryItem {
  const tags = stringList(asset.metadata.tags);
  return {
    id: asset.asset_id,
    title: asset.title ?? asset.pack_role ?? asset.asset_kind,
    kind: roleToLibraryKind(role, asset.asset_kind),
    mediaType: textValue(asset.metadata.media_type) ?? 'asset',
    pack: textValue(asset.metadata.asset_pack_niche) ?? 'Selected pack',
    tags: tags.length ? tags : [asset.asset_kind],
    layerSuitability: textValue(asset.metadata.category) ?? asset.pack_role ?? role,
    reuseCount: asset.usage_count,
    performanceScore: Math.round((asset.performance_score ?? 0.72) * 100),
    previewTone: previewToneForAsset(asset.asset_id, asset.asset_kind, asset.title ?? role),
    imageUrl: stableAssetImageUrl(DEFAULT_ORG_ID, asset.asset_id) ?? textValue(asset.metadata.image_url) ?? undefined,
    storageUri: textValue(asset.metadata.storage_uri) ?? undefined,
  };
}

function syntheticHookAsset(
  pack: AssetPackRecord | null,
  visualAsset: AssetLibraryItem | null,
): AssetLibraryItem {
  const packName = pack?.name ?? 'Selected pack';
  const visualTitle = visualAsset?.title ?? pack?.niche ?? 'asset';
  return {
    id: `generated-hook:${pack?.id ?? visualAsset?.id ?? 'local'}`,
    title: `Try this ${visualTitle.toLowerCase()} prep trick`,
    kind: 'hook',
    mediaType: 'text',
    pack: packName,
    tags: ['generated-hook', pack?.niche ?? 'asset-pack'].filter(Boolean),
    layerSuitability: 'Generated hook label for visual-only pack',
    reuseCount: 0,
    performanceScore: 78,
    previewTone: 'linear-gradient(135deg, #0f172a, #f97316)',
  };
}

function assetKindToLibraryKind(assetKind: string | null): AssetLibraryKind {
  if (!assetKind) {
    return 'object';
  }
  if (assetKind.includes('background')) {
    return 'background';
  }
  if (assetKind.includes('hook') || assetKind.includes('caption') || assetKind.includes('text')) {
    return 'hook';
  }
  if (assetKind.includes('audio') || assetKind.includes('voiceover') || assetKind.includes('sound')) {
    return 'audio';
  }
  if (assetKind.includes('video') || assetKind.includes('clip')) {
    return 'video';
  }
  if (assetKind.includes('final') || assetKind.includes('package')) {
    return 'final_output';
  }
  return 'object';
}

function roleToLibraryKind(role: string, assetKind: string): AssetLibraryKind {
  if (role === 'foreground') {
    return 'object';
  }
  if (role === 'format') {
    return 'video';
  }
  return assetKindToLibraryKind(assetKind);
}

function previewToneForAsset(id: string, assetKind: string | null, title: string): string {
  const hue = hashString(`${id}:${title}`) % 360;
  if (assetKind?.includes('background')) {
    return `linear-gradient(135deg, hsl(${hue} 48% 24%), hsl(${(hue + 60) % 360} 68% 72%))`;
  }
  return `radial-gradient(circle at 50% 42%, hsl(${hue} 80% 72%) 0 22%, hsl(${(hue + 35) % 360} 65% 45%) 23% 48%, #101827 49%)`;
}

function hashString(value: string): number {
  let hash = 0;
  for (let index = 0; index < value.length; index += 1) {
    hash = (hash * 31 + value.charCodeAt(index)) >>> 0;
  }
  return hash;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function layerColorForItem(item: HookCanvasItem): string {
  const palette = ['#5eead4', '#f59e0b', '#a78bfa', '#fb7185', '#38bdf8', '#84cc16'];
  return palette[hashString(`${item.id}:${item.asset.id}`) % palette.length];
}

function formatAssetMix(value: Record<string, unknown> | null): string {
  if (!value || Object.keys(value).length === 0) {
    return 'Not recorded';
  }
  return Object.entries(value)
    .map(([key, item]) => `${humanizeKey(key)} ${item}`)
    .join(', ');
}

function formatAssetPackOption(pack: AssetPackRecord): string {
  const count = pack.requested_asset_count ?? '?';
  return `${pack.name} - ${pack.status} - ${count} assets`;
}

function isCombinatorEligibleAssetPack(pack: AssetPackRecord): boolean {
  return pack.status !== 'rejected' && pack.status !== 'archived';
}

function formatGeneratedRunOption(
  run: RunRecord,
  savedHookGenerations: SavedHookImageGeneration[] = [],
): string {
  const savedName = savedHookGenerations.find((generation) => generation.sourceRunId === run.id)?.name;
  const title =
    savedName ??
    textValue(hookCoverPayload(run)?.title) ??
    textValue(asRecord(run.input_params?.composition_manifest)?.title) ??
    `Output ${run.id.slice(0, 8)}`;
  return `${title} - ${run.status}`;
}

function formatOrgOption(org: OrgRecord): string {
  const count = `${org.page_count} page${org.page_count === 1 ? '' : 's'}`;
  return `${org.name} (${org.slug}) - ${count}`;
}

function hookCoverPayload(run: RunRecord | null): Record<string, unknown> | null {
  const packagePayload = asRecord(run?.output_payload?.package);
  const stepOutputs = asRecord(run?.output_payload?.step_outputs);
  const packaging = asRecord(stepOutputs?.packaging);
  return (
    asRecord(packagePayload?.hook_cover) ??
    asRecord(run?.output_payload?.hook_cover) ??
    asRecord(packaging?.hook_cover)
  );
}

function assetPreviewTone(asset: Record<string, unknown> | null, fallback: string): string {
  const metadata = asRecord(asset?.metadata);
  return textValue(metadata?.preview_tone) ?? fallback;
}

function assetImageUrl(asset: Record<string, unknown> | null): string | null {
  const metadata = asRecord(asset?.metadata);
  const download = asRecord(asset?.download);
  return (
    textValue(metadata?.image_url) ??
    textValue(asset?.image_url) ??
    textValue(asset?.preview_url) ??
    proxiedDownloadUrl(textValue(download?.url) ?? undefined) ??
    null
  );
}

function proxiedDownloadUrl(url: string | undefined): string | undefined {
  if (!url) {
    return undefined;
  }
  try {
    const parsed = new URL(url);
    if (['127.0.0.1', 'localhost'].includes(parsed.hostname)) {
      return `/api/artifact-proxy?url=${encodeURIComponent(url)}`;
    }
  } catch {
    return url;
  }
  return url;
}

function stableAssetImageUrl(orgId: string, assetId: string | null | undefined): string | undefined {
  if (!assetId || !isUuid(assetId)) {
    return undefined;
  }
  return `/api/orgs/${encodeURIComponent(orgId)}/assets/${encodeURIComponent(assetId)}/file`;
}

function isUuid(value: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(
    value,
  );
}

function buildCompositionManifest({
  assetPackId,
  assetPackName,
  planner,
  selectedBackground,
  selectedObject,
  selectedHook,
  selectedAudio,
  selectedVideo,
  outputScore,
}: {
  assetPackId: string;
  assetPackName: string;
  planner: AssetPackPlannerState;
  selectedBackground: AssetLibraryItem;
  selectedObject: AssetLibraryItem;
  selectedHook: AssetLibraryItem;
  selectedAudio: AssetLibraryItem | null;
  selectedVideo: AssetLibraryItem | null;
  outputScore: number;
}): Record<string, unknown> {
  const compositionId = [
    selectedBackground.id,
    selectedObject.id,
    selectedHook.id,
    selectedAudio?.id ?? 'no-audio',
    selectedVideo?.id ?? 'no-format',
    Date.now(),
  ].join(':');
  const layout = intentionalHookLayout({
    seed: compositionId,
    hookText: selectedHook.title,
    foreground: selectedObject,
  });
  const roles: Record<string, unknown> = {
    background: localAssetForManifest(selectedBackground),
    foreground: localAssetForManifest(selectedObject),
    hook: localAssetForManifest(selectedHook),
  };
  if (selectedAudio) {
    roles.audio = localAssetForManifest(selectedAudio);
  }
  if (selectedVideo) {
    roles.format = localAssetForManifest(selectedVideo);
  }
  return {
    schema_version: 'asset_composition_manifest.v1',
    output_type: 'hook_cover_image',
    asset_pack_id: assetPackId,
    composition_id: compositionId,
    title: `${assetPackName} hook cover`,
    roles,
    layout: {
      intent: layout.intent,
      background: { treatment: 'full_bleed', safe_crop: 'center_weighted' },
      foreground: layout.foreground,
      hook: layout.hook,
      rationale:
        'Combinator places the strongest visual subject away from the hook text and reserves a readable copy zone.',
    },
    editor_state: {
      selected_background_id: selectedBackground.id,
      background: selectedBackground,
      items: [
        {
          id: `manifest-object:${selectedObject.id}`,
          asset: selectedObject,
          ...layout.foreground,
        },
        {
          id: `manifest-hook:${selectedHook.id}`,
          asset: selectedHook,
          ...layout.hook,
        },
      ],
      updated_at: new Date().toISOString(),
      intent: layout.intent,
    },
    scores: {
      selection: outputScore / 100,
      compatibility: 0.82,
      diversity: 0.76,
      performance: outputScore / 100,
    },
    planner_context: {
      name: planner.name,
      requested_asset_count: planner.totalAssetCount,
      requested_split: {
        background_image: planner.backgroundCount,
        transparent_cutout_png: planner.objectCount,
      },
      target_reel_types: [planner.format],
      style_constraints: {
        style: planner.style,
        ratio: planner.ratio,
      },
      quality_level: planner.qualityLevel,
    },
  };
}

function withHookLayoutIntent({
  manifest,
  selectedBackground,
  selectedObject,
  selectedHook,
}: {
  manifest: Record<string, unknown>;
  selectedBackground: AssetLibraryItem;
  selectedObject: AssetLibraryItem;
  selectedHook: AssetLibraryItem;
}): Record<string, unknown> {
  const manifestLayout = asRecord(manifest.layout);
  const compositionId =
    textValue(manifest.composition_id) ??
    `${selectedBackground.id}:${selectedObject.id}:${selectedHook.id}`;
  const layout = intentionalHookLayout({
    seed: compositionId,
    hookText: selectedHook.title,
    foreground: selectedObject,
  });
  return {
    ...manifest,
    layout: {
      ...manifestLayout,
      intent: textValue(manifestLayout?.intent) ?? layout.intent,
      background: asRecord(manifestLayout?.background) ?? {
        treatment: 'full_bleed',
        safe_crop: 'center_weighted',
      },
      foreground: asRecord(manifestLayout?.foreground) ?? layout.foreground,
      hook: asRecord(manifestLayout?.hook) ?? layout.hook,
      rationale:
        textValue(manifestLayout?.rationale) ??
        'Combinator places the strongest visual subject away from the hook text and reserves a readable copy zone.',
    },
    editor_state: asRecord(manifest.editor_state) ?? {
      selected_background_id: selectedBackground.id,
      background: selectedBackground,
      items: [
        {
          id: `manifest-object:${selectedObject.id}`,
          asset: selectedObject,
          ...layout.foreground,
        },
        {
          id: `manifest-hook:${selectedHook.id}`,
          asset: selectedHook,
          ...layout.hook,
        },
      ],
      updated_at: new Date().toISOString(),
      intent: layout.intent,
    },
  };
}

function localAssetForManifest(asset: AssetLibraryItem): Record<string, unknown> {
  return {
    asset_id: asset.id,
    asset_kind: asset.kind,
    pack_role: asset.kind,
    title: asset.title,
    metadata: {
      media_type: asset.mediaType,
      pack: asset.pack,
      tags: asset.tags,
      layer_suitability: asset.layerSuitability,
      reuse_count: asset.reuseCount,
      performance_score: asset.performanceScore / 100,
      preview_tone: asset.previewTone,
      image_url: asset.imageUrl,
      storage_uri: asset.storageUri,
    },
  };
}

function CombinationSlot({ label, asset }: { label: string; asset: AssetLibraryItem | null }) {
  if (!asset) {
    return (
      <article className="combo-slot">
        <div className="asset-preview is-small" style={{ background: 'linear-gradient(135deg, #1f2937, #475569)' }} />
        <div>
          <span>{label}</span>
          <strong>Not used</strong>
          <p>This pack has no asset for this optional role.</p>
        </div>
      </article>
    );
  }
  return (
    <article className="combo-slot">
      <div className="asset-preview is-small" style={{ background: asset.previewTone }} />
      <div>
        <span>{label}</span>
        <strong>{asset.title}</strong>
        <p>{asset.tags.join(', ')}</p>
      </div>
    </article>
  );
}

function StructuredArtifactContent({ value }: { value: unknown }) {
  if (value === null || value === undefined || value === '') {
    return <div className="empty-state">No content recorded for this view.</div>;
  }

  return <div className="artifact-readable">{renderArtifactValue(value, 'artifact-root')}</div>;
}

function renderArtifactValue(value: unknown, keyPrefix: string): ReactNode {
  if (Array.isArray(value)) {
    if (value.length === 0) {
      return <span className="artifact-muted">No items recorded</span>;
    }

    return (
      <ol className="artifact-list">
        {value.map((item, index) => (
          <li key={`${keyPrefix}-${index}`}>
            {renderArtifactValue(item, `${keyPrefix}-${index}`)}
          </li>
        ))}
      </ol>
    );
  }

  const record = asRecord(value);
  if (record) {
    const entries = Object.entries(record);
    if (entries.length === 0) {
      return <span className="artifact-muted">No fields recorded</span>;
    }

    return (
      <div className="artifact-fields">
        {entries.map(([key, item]) => {
          const summary = artifactSummary(item);
          return (
            <section className="artifact-field" key={`${keyPrefix}-${key}`}>
              <div className="artifact-field-heading">
                <h4>{humanizeKey(key)}</h4>
                {summary ? <span>{summary}</span> : null}
              </div>
              {renderArtifactValue(item, `${keyPrefix}-${key}`)}
            </section>
          );
        })}
      </div>
    );
  }

  const text = scalarText(value);
  if (text.includes('\n')) {
    return (
      <div className="artifact-prose">
        {text
          .split(/\n{2,}/)
          .map((paragraph) => paragraph.trim())
          .filter(Boolean)
          .map((paragraph, index) => (
            <p key={`${keyPrefix}-${index}`}>{paragraph}</p>
          ))}
      </div>
    );
  }

  return <span className="artifact-value">{text}</span>;
}

function PolicyEditor({
  policyDraft,
  isSaving,
  savePolicy,
  updatePolicyDraft,
  numberValue,
}: {
  policyDraft: PolicyDocument;
  isSaving: boolean;
  savePolicy: () => void;
  updatePolicyDraft: (updater: (current: PolicyDocument) => PolicyDocument) => void;
  numberValue: (value: string) => number;
}) {
  return (
    <div className="policy-editor">
      <div className="policy-group">
        <h4>Mode ratios</h4>
        {Object.entries(policyDraft.mode_ratios).map(([key, value]) => (
          <label className="field" key={key}>
            {policyLabels[key as keyof typeof policyLabels]}
            <input
              min="0"
              max="1"
              step="0.01"
              type="number"
              value={value}
              onChange={(event) =>
                updatePolicyDraft((current) => ({
                  ...current,
                  mode_ratios: {
                    ...current.mode_ratios,
                    [key]: numberValue(event.target.value),
                  },
                }))
              }
            />
          </label>
        ))}
        <span className="policy-total">
          Total{' '}
          {Object.values(policyDraft.mode_ratios)
            .reduce((sum, value) => sum + value, 0)
            .toFixed(2)}
        </span>
      </div>

      <div className="policy-group">
        <h4>Budget</h4>
        {Object.entries(policyDraft.budget).map(([key, value]) => (
          <label className="field" key={key}>
            {policyLabels[key as keyof typeof policyLabels]}
            <input
              min="0"
              step="0.01"
              type="number"
              value={value}
              onChange={(event) =>
                updatePolicyDraft((current) => ({
                  ...current,
                  budget: {
                    ...current.budget,
                    [key]: numberValue(event.target.value),
                  },
                }))
              }
            />
          </label>
        ))}
      </div>

      <div className="policy-group">
        <h4>Quality</h4>
        <label className="field">
          {policyLabels.warn_at}
          <input
            min="0"
            max="1"
            step="0.01"
            type="number"
            value={policyDraft.thresholds.similarity.warn_at}
            onChange={(event) =>
              updatePolicyDraft((current) => ({
                ...current,
                thresholds: {
                  ...current.thresholds,
                  similarity: {
                    ...current.thresholds.similarity,
                    warn_at: numberValue(event.target.value),
                  },
                },
              }))
            }
          />
        </label>
        <label className="field">
          {policyLabels.block_at}
          <input
            min="0"
            max="1"
            step="0.01"
            type="number"
            value={policyDraft.thresholds.similarity.block_at}
            onChange={(event) =>
              updatePolicyDraft((current) => ({
                ...current,
                thresholds: {
                  ...current.thresholds,
                  similarity: {
                    ...current.thresholds.similarity,
                    block_at: numberValue(event.target.value),
                  },
                },
              }))
            }
          />
        </label>
        <label className="field">
          {policyLabels.min_quality_score}
          <input
            min="0"
            max="1"
            step="0.01"
            type="number"
            value={policyDraft.thresholds.min_quality_score}
            onChange={(event) =>
              updatePolicyDraft((current) => ({
                ...current,
                thresholds: {
                  ...current.thresholds,
                  min_quality_score: numberValue(event.target.value),
                },
              }))
            }
          />
        </label>
      </div>

      <button className="primary-button" type="button" onClick={savePolicy} disabled={isSaving}>
        Save policy
      </button>
    </div>
  );
}
