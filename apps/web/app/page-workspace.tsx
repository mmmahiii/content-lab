'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import type { FormEvent, ReactNode } from 'react';

import { normalizeOrgId, OPERATOR_ORG_COOKIE } from './_lib/operator-context';

const DEFAULT_ORG_ID =
  process.env.NEXT_PUBLIC_CONTENT_LAB_OPERATOR_ORG_ID ??
  '00000000-0000-4000-8000-000000000001';

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
  niche: string;
  totalAssetCount: number;
  split: string;
  targetReelTypes: string;
  styleConstraints: string;
  qualityLevel: 'lean' | 'balanced' | 'premium';
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

const assetKindTabs: { kind: AssetLibraryKind; label: string }[] = [
  { kind: 'background', label: 'Backgrounds' },
  { kind: 'object', label: 'PNG objects' },
  { kind: 'video', label: 'Videos' },
  { kind: 'hook', label: 'Hooks' },
  { kind: 'audio', label: 'Audio' },
  { kind: 'final_output', label: 'Final outputs' },
];

const assetLibrarySeed: AssetLibraryItem[] = [
  {
    id: 'steak-hook-bg',
    title: 'Steakpagetest pan hook plate',
    kind: 'background',
    mediaType: 'image/jpeg',
    pack: 'steakpagetest screenshot recreation',
    tags: ['steakpagetest', 'steak', 'pan', 'instagram-hook'],
    layerSuitability: 'Vertical reel background, native UI chrome',
    reuseCount: 12,
    performanceScore: 97,
    previewTone: 'linear-gradient(180deg, #d9c4a1 0%, #f3ead8 38%, #161b1d 39%, #0d1113 100%)',
    imageUrl:
      'https://commons.wikimedia.org/wiki/Special:Redirect/file/Beef_round_top_round_steak_in_pan,_raw.jpg',
  },
  {
    id: 'steak-hook-herbs',
    title: 'Countertop herb planter cue',
    kind: 'object',
    mediaType: 'image/png',
    pack: 'steakpagetest screenshot recreation',
    tags: ['steakpagetest', 'herbs', 'countertop', 'foreground'],
    layerSuitability: 'Upper-right herb planter foreground cue',
    reuseCount: 9,
    performanceScore: 92,
    previewTone: 'radial-gradient(circle at 50% 40%, #86a85e 0 23%, #36522b 24% 45%, #2c2118 46%)',
    imageUrl: 'https://commons.wikimedia.org/wiki/Special:Redirect/file/Basil.png',
  },
  {
    id: 'steak-hook-copy',
    title: 'Verse kruiden binnen handbereik',
    kind: 'hook',
    mediaType: 'text/plain',
    pack: 'steakpagetest screenshot recreation',
    tags: ['steakpagetest', 'dutch-caption', 'native-ui'],
    layerSuitability: 'Native Instagram lower caption hook',
    reuseCount: 14,
    performanceScore: 95,
    previewTone: 'linear-gradient(135deg, #0f172a, #f97316)',
  },
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

const steakHookAssets = {
  herbs: assetLibrarySeed.find((asset) => asset.id === 'steak-hook-herbs') ?? assetLibrarySeed[0],
  copy: assetLibrarySeed.find((asset) => asset.id === 'steak-hook-copy') ?? assetLibrarySeed[0],
};

const steakPresetItems: HookCanvasItem[] = [
  {
    id: 'steak-hook-herbs-preset',
    asset: steakHookAssets.herbs,
    x: 69,
    y: 31,
    size: 40,
  },
  {
    id: 'steak-hook-copy-preset',
    asset: steakHookAssets.copy,
    x: 36,
    y: 93,
    size: 46,
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

function stepStatus(run: RunRecord | null, stepKey: string): string {
  const statuses = asRecord(run?.output_payload?.task_statuses);
  const value = statuses?.[stepKey];
  return typeof value === 'string' ? value : run?.status === 'succeeded' ? 'succeeded' : 'pending';
}

export function PageWorkspace() {
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
    void loadPages();
  }, []);

  useEffect(() => {
    if (selectedPage?.id) {
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
    }
  }, [selectedPage?.id]);

  useEffect(() => {
    const run = selectedPackageRunRef.current;
    if (run) {
      void loadPackage(run);
    } else {
      setPackageDetail(null);
      setPackageNotice('');
    }
  }, [selectedPackageRunLoadKey]);

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
  }, [selectedPage?.id, hasActiveGeneration]);

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
                <HookImageCreator />
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
}: {
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
}) {
  const [assetKind, setAssetKind] = useState<AssetLibraryKind>('background');
  const [isAssetLibraryOpen, setIsAssetLibraryOpen] = useState(true);
  const [isSavedPackBrowserOpen, setIsSavedPackBrowserOpen] = useState(true);
  const [planner, setPlanner] = useState<AssetPackPlannerState>({
    niche: selectedPage.handle ?? selectedPage.display_name,
    totalAssetCount: 24,
    split: '6 backgrounds, 6 transparent objects, 4 clips, 4 hooks, 2 audio, 2 reference outputs',
    targetReelTypes: 'proof reel, listicle, product demo, objection handling',
    styleConstraints: 'High contrast captions, clean product cutouts, mobile-first safe areas',
    qualityLevel: 'balanced',
  });
  const [assetPackPlan, setAssetPackPlan] = useState<AssetPackPlanResponse | null>(null);
  const [assetPack, setAssetPack] = useState<AssetPackRecord | null>(null);
  const [savedAssetPacks, setSavedAssetPacks] = useState<AssetPackRecord[]>([]);
  const [selectedAssetPackId, setSelectedAssetPackId] = useState('');
  const [packAssets, setPackAssets] = useState<AssetLibraryItem[]>([]);
  const [packAssetMessage, setPackAssetMessage] = useState('Select a saved pack to load its assets.');
  const [candidateCompositions, setCandidateCompositions] = useState<CandidateComposition[]>([]);
  const [packOutboxMessage, setPackOutboxMessage] = useState('No pack plan saved yet.');
  const [combinatorOutboxMessage, setCombinatorOutboxMessage] = useState(
    'Choose a saved pack, then queue a composition render.',
  );
  const [lastRender, setLastRender] = useState<AssetPackRenderResponse | null>(null);
  const [compositionPickIndex, setCompositionPickIndex] = useState(0);
  const [isPackActionRunning, setIsPackActionRunning] = useState(false);

  const activeAssetLibrary = packAssets.length ? packAssets : assetLibrarySeed;
  const filteredAssets = activeAssetLibrary.filter((asset) => asset.kind === assetKind);
  const plan = buildAssetPackPlan(planner);
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
      setPackAssetMessage('Select a saved pack to load its assets.');
      return;
    }
    void loadSelectedPackAssets(selectedAssetPackId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedAssetPackId]);

  async function loadSavedAssetPacks(preferredPackId?: string): Promise<AssetPackRecord[]> {
    try {
      const response = await fetch(`/api/orgs/${activeOrgId()}/asset-packs?limit=50`, {
        cache: 'no-store',
        headers: { 'X-Actor-Id': 'operator:ui-rebuild' },
      });
      if (!response.ok) {
        throw new Error(await apiErrorMessage(response));
      }
      const packs = (await response.json()) as AssetPackRecord[];
      setSavedAssetPacks(packs);
      const fallbackPackId =
        packs.find((pack) => pack.status !== 'rejected' && pack.status !== 'archived')?.id ??
        packs[0]?.id ??
        '';
      const nextSelected =
        preferredPackId ||
        selectedAssetPackId ||
        fallbackPackId;
      setSelectedAssetPackId(nextSelected);
      return packs;
    } catch (error) {
      setPackOutboxMessage(
        error instanceof Error ? error.message : 'Could not load saved asset packs.',
      );
      return [];
    }
  }

  async function loadSelectedPackAssets(assetPackId: string): Promise<AssetLibraryItem[]> {
    try {
      setPackAssetMessage('Loading selected pack assets...');
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
      const mappedAssets = assetRows.map(mapAssetLibraryItemOut);
      setPackAssets(mappedAssets);
      setPackAssetMessage(
        mappedAssets.length
          ? `Loaded ${mappedAssets.length} real assets from the selected pack.`
          : 'Selected pack has no ready assets yet.',
      );

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
      setPackAssetMessage(message);
      setCombinatorOutboxMessage(message);
      return [];
    }
  }

  async function createBackendPackPlan(): Promise<AssetPackPlanResponse> {
    const response = await fetch(`/api/orgs/${activeOrgId()}/asset-packs/plan`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Actor-Id': 'operator:ui-rebuild',
      },
      body: JSON.stringify({
        name: `${planner.niche || selectedPage.display_name} asset pack`,
        niche: planner.niche || selectedPage.display_name,
        requested_asset_count: Math.max(1, planner.totalAssetCount),
        asset_mix: null,
        target_reel_types: plan.formats,
        style_persona_constraints: {
          quality_level: planner.qualityLevel,
          notes: planner.styleConstraints,
          requested_split: planner.split,
        },
        purpose: 'Reusable component pack for asset-led reel generation.',
        target_audience: selectedPage.handle ?? selectedPage.display_name,
      }),
    });
    if (!response.ok) {
      throw new Error(await apiErrorMessage(response));
    }
    const created = (await response.json()) as AssetPackPlanResponse;
    setAssetPackPlan(created);
    setAssetPack(created.asset_pack);
    setSelectedAssetPackId(created.asset_pack.id);
    setPackOutboxMessage(`Saved ${created.asset_pack.name} as a backend pack plan.`);
    await loadSavedAssetPacks(created.asset_pack.id);
    return created;
  }

  async function savePackPlan() {
    setIsPackActionRunning(true);
    setWorkspaceMessage('Saving asset pack plan...');
    setPackOutboxMessage('Saving pack plan to the backend...');
    try {
      const created = await createBackendPackPlan();
      setWorkspaceMessage(`Saved ${created.asset_pack.name}.`);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Could not save asset pack plan.';
      setPackOutboxMessage(message);
      setWorkspaceMessage(message);
    } finally {
      setIsPackActionRunning(false);
    }
  }

  async function ensurePackPlan(): Promise<AssetPackRecord> {
    if (assetPack && assetPack.status !== 'rejected') {
      return assetPack;
    }
    const created = await createBackendPackPlan();
    return created.asset_pack;
  }

  async function ensureApprovedPack(): Promise<AssetPackRecord> {
    const pack = await ensurePackPlan();
    if (pack.status === 'approved' || pack.status === 'ready' || pack.status === 'generating') {
      return pack;
    }
    return approveSavedPack(pack);
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
      setPackOutboxMessage(`Approved ${approved.name}. It is now available for the combinator.`);
      await loadSavedAssetPacks(approved.id);
      return approved;
  }

  async function approvePackPlan() {
    setIsPackActionRunning(true);
    setWorkspaceMessage('Approving asset pack plan...');
    try {
      const pack = selectedSavedPack ?? (await ensurePackPlan());
      const approved = await approveSavedPack(pack);
      setWorkspaceMessage(`Approved ${approved.name}.`);
    } catch (error) {
      setWorkspaceMessage(
        error instanceof Error ? error.message : 'Could not approve asset pack plan.',
      );
    } finally {
      setIsPackActionRunning(false);
    }
  }

  async function stopPackPlan() {
    const packToStop = selectedSavedPack ?? assetPack;
    if (!packToStop || packToStop.status === 'rejected') {
      setAssetPack(null);
      setAssetPackPlan(null);
      setLastRender(null);
      setSelectedAssetPackId('');
      setWorkspaceMessage('No active asset pack plan to stop.');
      return;
    }
    const confirmed = window.confirm(`Stop ${packToStop.name}?`);
    if (!confirmed) {
      return;
    }
    setIsPackActionRunning(true);
    setWorkspaceMessage('Stopping asset pack plan...');
    try {
      const response = await fetch(`/api/orgs/${activeOrgId()}/asset-packs/${packToStop.id}/reject`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Actor-Id': 'operator:ui-rebuild',
        },
        body: JSON.stringify({
          note: 'Stopped from asset pack workspace.',
          metadata: { source: 'web_asset_pack_workspace' },
        }),
      });
      if (!response.ok) {
        throw new Error(await apiErrorMessage(response));
      }
      const rejected = (await response.json()) as AssetPackRecord;
      setAssetPack(rejected);
      setSelectedAssetPackId(rejected.id);
      setPackOutboxMessage(`Stopped ${rejected.name}.`);
      await loadSavedAssetPacks(rejected.id);
      setWorkspaceMessage(`Stopped ${rejected.name}.`);
    } catch (error) {
      setWorkspaceMessage(
        error instanceof Error ? error.message : 'Could not stop asset pack plan.',
      );
    } finally {
      setIsPackActionRunning(false);
    }
  }

  async function queueRender() {
    setIsPackActionRunning(true);
    setWorkspaceMessage('Creating asset-led hook / cover...');
    setCombinatorOutboxMessage('Creating selected hook / cover composition...');
    try {
      const selectedPack = selectedCombinatorPack ?? (await ensurePackPlan());
      if (!isCombinatorEligibleAssetPack(selectedPack)) {
        throw new Error('Choose an active saved pack before queueing a render.');
      }
      const approved = await approveSavedPack(selectedPack);
      const compositionManifest =
        selectedCandidate?.composition_manifest ??
        buildCompositionManifest({
          assetPackId: approved.id,
          assetPackName: approved.name,
          planner,
          selectedBackground,
          selectedObject,
          selectedHook,
          selectedAudio,
          selectedVideo,
          outputScore,
        });
      const response = await fetch(
        `/api/orgs/${activeOrgId()}/asset-packs/${approved.id}/composition-renders`,
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
            idempotency_key: `asset-pack-ui:${approved.id}:${Date.now()}`,
            metadata: {
              source: 'web_asset_pack_workspace',
              page_id: selectedPage.id,
            },
          }),
        },
      );
      if (!response.ok) {
        throw new Error(await apiErrorMessage(response));
      }
      const submitted = (await response.json()) as AssetPackRenderResponse;
      setLastRender(submitted);
      setCombinatorOutboxMessage(
        selectedCandidate
          ? `Created a backend-selected hook / cover from ${approved.name}. The preview is ready below.`
          : `Created a hook / cover from ${approved.name}'s real pack assets. The preview is ready below.`,
      );
      onRunsChanged();
      setSelectedOutputRunId(submitted.run_id);
      setCompositionPickIndex((current) => current + 1);
      setWorkspaceMessage(`Created asset-led hook / cover ${submitted.run_id.slice(0, 8)}.`);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Could not queue asset-led render.';
      setCombinatorOutboxMessage(message);
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
            <p className="eyebrow">Asset library</p>
            <h3>Reusable assets</h3>
          </div>
          <span>
            <span className="status-pill">
              {packAssets.length ? `${packAssets.length} pack assets` : `${assetLibrarySeed.length} demo assets`}
            </span>
            <strong>{isAssetLibraryOpen ? 'Collapse' : 'Expand'}</strong>
          </span>
        </button>

        {isAssetLibraryOpen ? (
          <>
            <p className="muted">{packAssetMessage}</p>
            <div className="tabs asset-kind-tabs" role="tablist" aria-label="Asset library categories">
              {assetKindTabs.map((tab) => (
                <button
                  className={assetKind === tab.kind ? 'is-active' : ''}
                  type="button"
                  role="tab"
                  aria-selected={assetKind === tab.kind}
                  key={tab.kind}
                  onClick={() => setAssetKind(tab.kind)}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            {filteredAssets.length ? (
              <div className="asset-library-grid">
                {filteredAssets.map((asset) => (
                  <AssetLibraryCard asset={asset} key={asset.id} />
                ))}
              </div>
            ) : (
              <div className="empty-state">No {assetKind.replace('_', ' ')} assets in this pack.</div>
            )}
          </>
        ) : (
          <p className="muted">Asset previews are hidden. Expand to browse reusable assets.</p>
        )}
      </section>

      <div className="asset-pack-grid">
        <section className="generation-surface">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Asset pack planner</p>
              <h3>User-defined pack</h3>
            </div>
          </div>

          <div className="planner-form">
            <label className="field">
              Niche
              <input
                value={planner.niche}
                onChange={(event) =>
                  setPlanner((current) => ({ ...current, niche: event.target.value }))
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
                  setPlanner((current) => ({
                    ...current,
                    totalAssetCount: Number.parseInt(event.target.value || '0', 10),
                  }))
                }
              />
            </label>
            <label className="field">
              Optional asset split
              <textarea
                value={planner.split}
                onChange={(event) =>
                  setPlanner((current) => ({ ...current, split: event.target.value }))
                }
              />
            </label>
            <label className="field">
              Target reel types
              <textarea
                value={planner.targetReelTypes}
                onChange={(event) =>
                  setPlanner((current) => ({ ...current, targetReelTypes: event.target.value }))
                }
              />
            </label>
            <label className="field">
              Style constraints
              <textarea
                value={planner.styleConstraints}
                onChange={(event) =>
                  setPlanner((current) => ({ ...current, styleConstraints: event.target.value }))
                }
              />
            </label>
            <label className="field">
              Generation budget / quality
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
          </div>
        </section>

        <section className="generation-surface">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Asset pack review</p>
              <h3>Proposed plan</h3>
            </div>
            <span className={`status-pill ${plan.warningCount ? 'is-live' : 'is-good'}`}>
              {plan.warningCount
                ? `${plan.warningCount} warning${plan.warningCount === 1 ? '' : 's'}`
                : 'Ready'}
            </span>
          </div>

          <div className="review-summary">
            <span>{plan.mixSummary}</span>
            <span>{plan.outputPotential}</span>
            <span>{assetPack ? `Backend: ${assetPack.status}` : 'Backend: local draft'}</span>
          </div>

          <div className="planned-assets">
            {plan.specs.map((spec) => (
              <article className="planned-asset" key={spec.category}>
                <div>
                  <h4>{spec.category}</h4>
                  <p>{spec.reason}</p>
                </div>
                <span>{spec.count}</span>
              </article>
            ))}
          </div>

          <div className="review-columns">
            <div>
              <h4>Expected reel formats</h4>
              <ul>
                {plan.formats.map((format) => (
                  <li key={format}>{format}</li>
                ))}
              </ul>
            </div>
            <div>
              <h4>Review notes</h4>
              <ul>
                {plan.notes.map((note) => (
                  <li key={note}>{note}</li>
                ))}
              </ul>
            </div>
          </div>

          <div className="review-actions">
            <button
              className="utility-button"
              type="button"
              onClick={() => void savePackPlan()}
              disabled={actionDisabled}
            >
              {isPackActionRunning ? 'Working...' : 'Save pack plan'}
            </button>
            <button
              className="primary-button"
              type="button"
              onClick={() => void approvePackPlan()}
              disabled={actionDisabled || assetPack?.status === 'approved'}
            >
              {isPackActionRunning ? 'Working...' : 'Approve pack plan'}
            </button>
            <button
              className="danger-button"
              type="button"
              onClick={() => void stopPackPlan()}
              disabled={actionDisabled || !assetPack || assetPack.status === 'rejected'}
            >
              Stop plan
            </button>
          </div>
          <AssetPackOutbox
            activePack={assetPack}
            savedPacks={savedAssetPacks}
            plan={assetPackPlan}
            message={packOutboxMessage}
          />
        </section>
      </div>

      <section className="output-surface">
        <button
          className="collapsible-section-toggle"
          type="button"
          aria-expanded={isSavedPackBrowserOpen}
          onClick={() => setIsSavedPackBrowserOpen((current) => !current)}
        >
          <div>
            <p className="eyebrow">Saved packs</p>
            <h3>Pack browser</h3>
          </div>
          <span>
            <span className="status-pill">{savedAssetPacks.length} saved</span>
            <strong>{isSavedPackBrowserOpen ? 'Collapse' : 'Expand'}</strong>
          </span>
        </button>

        {isSavedPackBrowserOpen ? (
          <>
            <div className="inline-controls">
              <label className="field">
                View pack
                <select
                  value={selectedAssetPackId}
                  onChange={(event) => {
                    const pack = savedAssetPacks.find(
                      (candidate) => candidate.id === event.target.value,
                    );
                    setSelectedAssetPackId(event.target.value);
                    if (pack) {
                      setAssetPack(pack);
                      setPackOutboxMessage(`Selected ${pack.name}.`);
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
              <button
                className="utility-button"
                type="button"
                onClick={() => void loadSavedAssetPacks()}
              >
                Refresh packs
              </button>
            </div>

            {selectedSavedPack ? (
              <SelectedSavedPackDetail
                pack={selectedSavedPack}
                assets={packAssets}
                candidateCount={candidateCompositions.length}
              />
            ) : (
              <div className="empty-state">No saved packs loaded. Save a pack plan or refresh packs.</div>
            )}
          </>
        ) : (
          <p className="muted">
            {selectedSavedPack
              ? `${selectedSavedPack.name} is selected.`
              : 'Saved pack details are hidden.'}
          </p>
        )}
      </section>

      <section className="output-surface">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Asset combinator</p>
            <h3>Reel combinations</h3>
          </div>
          <div className="review-actions">
            <button className="utility-button" type="button" onClick={() => void loadSavedAssetPacks()}>
              Refresh packs
            </button>
            <button
              className="primary-button"
              type="button"
              onClick={() => void queueRender()}
                disabled={actionDisabled || !selectedCombinatorPack}
            >
              {isPackActionRunning ? 'Working...' : 'Create hook / cover'}
            </button>
          </div>
        </div>

        <label className="field">
          Saved pack
          <select
            value={selectedCombinatorPack?.id ?? ''}
            onChange={(event) => {
              setSelectedAssetPackId(event.target.value);
              const pack = combinatorAssetPacks.find(
                (candidate) => candidate.id === event.target.value,
              );
              if (pack) {
                setAssetPack(pack);
                setCombinatorOutboxMessage(`${pack.name} is selected for the combinator.`);
              }
            }}
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

        <div className="combo-grid">
          <CombinationSlot label="Background" asset={selectedBackground} />
          <CombinationSlot label="Foreground object" asset={selectedObject} />
          <CombinationSlot label="Hook" asset={selectedHook} />
          <CombinationSlot label="Audio" asset={selectedAudio} />
          <CombinationSlot label="Format / template" asset={selectedVideo} />
          <div className="combo-score">
            <span>Estimated output score</span>
            <strong>{outputScore}</strong>
          </div>
        </div>
        <GeneratedCompositionOutputBox
          compositionRuns={assetCompositionRuns}
          selectedOutputRun={selectedOutputIsComposition ? selectedOutputRun : null}
          setSelectedOutputRunId={setSelectedOutputRunId}
          packageDetail={selectedOutputIsComposition ? packageDetail : null}
          packageNotice={selectedOutputIsComposition ? packageNotice : ''}
          failureMessages={selectedOutputIsComposition ? failureMessages : []}
          artifactTabs={
            selectedOutputIsComposition
              ? artifactTabs.filter((tab) => tab !== 'video' && tab !== 'runway')
              : []
          }
          artifactTab={artifactTab}
          setArtifactTab={setArtifactTab}
          selectedArtifact={selectedOutputIsComposition ? selectedArtifact : null}
          selectedDownload={selectedOutputIsComposition ? selectedDownload : null}
          artifactText={selectedOutputIsComposition ? artifactText : ''}
          artifactTextStatus={selectedOutputIsComposition ? artifactTextStatus : ''}
          copyArtifactText={copyArtifactText}
          message={combinatorOutboxMessage}
        />
      </section>

    </>
  );
}

function AssetPackOutbox({
  activePack,
  savedPacks,
  plan,
  message,
}: {
  activePack: AssetPackRecord | null;
  savedPacks: AssetPackRecord[];
  plan: AssetPackPlanResponse | null;
  message: string;
}) {
  const pack = activePack ?? plan?.asset_pack ?? null;
  const mix = plan?.asset_mix ?? pack?.asset_mix_final_json ?? pack?.asset_mix_requested_json ?? null;
  return (
    <section className="outbox-panel" aria-label="Pack plan outbox">
      <div className="outbox-heading">
        <div>
          <p className="eyebrow">Pack plan outbox</p>
          <h4>{pack ? pack.name : 'No saved pack selected'}</h4>
        </div>
        <span className={`status-pill ${pack ? statusTone(pack.status) : 'is-muted'}`}>
          {pack?.status ?? 'draft'}
        </span>
      </div>
      <dl className="outbox-grid">
        <div>
          <dt>Saved packs</dt>
          <dd>{savedPacks.length}</dd>
        </div>
        <div>
          <dt>Requested assets</dt>
          <dd>{pack?.requested_asset_count ?? planAssetCount(plan) ?? 'Not saved'}</dd>
        </div>
        <div>
          <dt>Asset mix</dt>
          <dd>{formatAssetMix(mix)}</dd>
        </div>
        <div>
          <dt>Formats</dt>
          <dd>{plan?.expected_reel_formats?.join(', ') || 'Uses planner formats'}</dd>
        </div>
      </dl>
      <p>{message}</p>
      {plan?.strategy_summary ? <p>{plan.strategy_summary}</p> : null}
    </section>
  );
}

function SelectedSavedPackDetail({
  pack,
  assets,
  candidateCount,
}: {
  pack: AssetPackRecord;
  assets: AssetLibraryItem[];
  candidateCount: number;
}) {
  return (
    <article className="saved-pack-card is-selected">
      <div className="saved-pack-card-heading">
        <div>
          <h4>{pack.name}</h4>
          <p>{pack.niche}</p>
        </div>
        <span className={`status-pill ${statusTone(pack.status)}`}>{pack.status}</span>
      </div>
      <dl className="saved-pack-meta">
        <div>
          <dt>Assets</dt>
          <dd>
            {assets.length || pack.requested_asset_count || 'Unknown'}
            {assets.length ? ' loaded' : ''}
          </dd>
        </div>
        <div>
          <dt>Mix</dt>
          <dd>{formatAssetMix(pack.asset_mix_final_json ?? pack.asset_mix_requested_json ?? null)}</dd>
        </div>
        <div>
          <dt>Combinations</dt>
          <dd>{candidateCount || 'Visual fallback'}</dd>
        </div>
      </dl>
      {pack.strategy_summary ? <p>{pack.strategy_summary}</p> : null}
      {assets.length ? (
        <div className="pack-asset-browser" aria-label="Selected pack assets">
          {assets.slice(0, 12).map((asset) => (
            <AssetLibraryCard asset={asset} compact key={asset.id} />
          ))}
        </div>
      ) : (
        <p>No ready assets loaded for this pack yet.</p>
      )}
    </article>
  );
}

function AssetLibraryCard({ asset, compact = false }: { asset: AssetLibraryItem; compact?: boolean }) {
  return (
    <article className={`asset-card ${compact ? 'is-compact' : ''}`}>
      <div className="asset-preview" style={{ background: asset.previewTone }}>
        {asset.imageUrl ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={asset.imageUrl} alt={asset.title} />
        ) : (
          <span>{asset.kind.replace('_', ' ')}</span>
        )}
      </div>
      <div className="asset-card-body">
        <div>
          <h4>{asset.title}</h4>
          <p className="muted">{asset.mediaType}</p>
        </div>
        <dl className="asset-meta">
          <div>
            <dt>Pack</dt>
            <dd>{asset.pack}</dd>
          </div>
          <div>
            <dt>Layer</dt>
            <dd>{asset.layerSuitability}</dd>
          </div>
          <div>
            <dt>Reuse</dt>
            <dd>{asset.reuseCount}</dd>
          </div>
          <div>
            <dt>Score</dt>
            <dd>{asset.performanceScore}</dd>
          </div>
        </dl>
        <div className="tag-row">
          {asset.tags.map((tag) => (
            <span key={tag}>{tag}</span>
          ))}
        </div>
      </div>
    </article>
  );
}

function GeneratedCompositionOutputBox({
  compositionRuns,
  selectedOutputRun,
  setSelectedOutputRunId,
  packageDetail,
  packageNotice,
  failureMessages,
  artifactTabs,
  artifactTab,
  setArtifactTab,
  selectedArtifact,
  selectedDownload,
  artifactText,
  artifactTextStatus,
  copyArtifactText,
  message,
}: {
  compositionRuns: RunRecord[];
  selectedOutputRun: RunRecord | null;
  setSelectedOutputRunId: (runId: string) => void;
  packageDetail: PackageDetail | null;
  packageNotice: string;
  failureMessages: string[];
  artifactTabs: ArtifactTab[];
  artifactTab: ArtifactTab;
  setArtifactTab: (tab: ArtifactTab) => void;
  selectedArtifact: PackageArtifact | null;
  selectedDownload: SignedDownload | null;
  artifactText: string;
  artifactTextStatus: string;
  copyArtifactText: () => void;
  message: string;
}) {
  const visibleArtifactTabs = artifactTabs.filter((tab) => tab !== 'video' && tab !== 'runway');
  const visibleArtifactTab = visibleArtifactTabs.some((tab) => tab === artifactTab)
    ? artifactTab
    : (visibleArtifactTabs[0] ?? 'raw');
  return (
    <section className="generated-output-box" aria-label="Combinator generated output">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Combinator output</p>
          <h3>Generated hook / cover</h3>
        </div>
        <span className={`status-pill ${statusTone(selectedOutputRun?.status)}`}>
          {selectedOutputRun?.status ?? 'waiting'}
        </span>
      </div>

      {compositionRuns.length ? (
        <>
          <label className="field">
            Hook / cover run
            <select
              value={selectedOutputRun?.id ?? ''}
              onChange={(event) => setSelectedOutputRunId(event.target.value)}
            >
              {compositionRuns.map((run) => (
                <option key={run.id} value={run.id}>
                  {formatGeneratedRunOption(run)}
                </option>
              ))}
            </select>
          </label>

          <PackageSummary
            run={selectedOutputRun}
            detail={packageDetail}
            notice={packageNotice || message}
            failures={failureMessages}
          />
          <LifecycleSteps run={selectedOutputRun} />

          <CompositionHookCoverPreview run={selectedOutputRun} />

          {visibleArtifactTabs.length ? (
            <ArtifactViewer
              tabs={visibleArtifactTabs}
              activeTab={visibleArtifactTab}
              setActiveTab={setArtifactTab}
              packageDetail={packageDetail}
              run={selectedOutputRun}
              artifact={selectedArtifact}
              download={selectedDownload}
              artifactText={artifactText}
              artifactTextStatus={artifactTextStatus}
              copyArtifactText={copyArtifactText}
            />
          ) : (
            <div className="empty-state">
              {selectedOutputRun?.status === 'failed'
                ? (runErrorMessage(selectedOutputRun) ?? 'Artifacts not written.')
                : packageNotice || message}
            </div>
          )}
        </>
      ) : (
        <div className="empty-state">{message}</div>
      )}
    </section>
  );
}

function SteakHookScene() {
  return (
    <div className="steak-hook-scene" aria-hidden="true">
      <div className="steak-hook-countertop">
        <div className="steak-hook-tray">
          <span />
          <span />
          <span />
        </div>
        <div className="steak-hook-planter">
          <span />
          <span />
          <span />
        </div>
      </div>
      <div className="steak-hook-hob">
        <div className="steak-hook-pan">
          <span className="steak-hook-steak is-left" />
          <span className="steak-hook-steak is-right" />
          <span className="steak-hook-fat" />
        </div>
        <div className="steak-hook-vent" />
      </div>
      <div className="instagram-status-bar">
        <span>17:12</span>
        <span className="instagram-phone-icons">▮▮▮ ◔ ▰</span>
      </div>
      <div className="instagram-actions">
        <span>♡<small>222K</small></span>
        <span>◉<small>1,063</small></span>
        <span>↪<small>4,623</small></span>
        <span>⌁<small>121K</small></span>
        <span>⋯</span>
      </div>
      <div className="instagram-caption-strip">
        <span className="instagram-avatar">GRANDO</span>
        <strong>grandohazerswoudedorp</strong>
        <span className="instagram-follow">Follow</span>
        <p>Verse kruiden binnen handbereik 🌿 ...</p>
        <span className="instagram-page-badge">GRANDO</span>
      </div>
      <div className="instagram-tabbar">
        <span>⌂</span>
        <span>▶</span>
        <span>♡<i /></span>
        <span>⌕</span>
        <span>●<i /></span>
      </div>
    </div>
  );
}

function CompositionHookCoverPreview({ run }: { run: RunRecord | null }) {
  const cover = hookCoverPayload(run);
  if (!cover) {
    return (
      <div className="empty-state">
        Queue a new hook / cover run to see the asset-pack image preview here.
      </div>
    );
  }
  if (isSteakHookCover(cover)) {
    return (
      <section className="hook-cover-output" aria-label="Generated hook cover preview">
        <div className="hook-cover-preview is-steak-hook">
          <SteakHookScene />
        </div>
        <div className="hook-cover-meta">
          <span className="status-pill success">Local image</span>
          <span>{textValue(cover.title) ?? 'steakpagetest Instagram hook recreation'}</span>
        </div>
      </section>
    );
  }
  const roles = asRecord(cover.roles) ?? {};
  const background = asRecord(roles.background);
  const foreground = asRecord(roles.foreground);
  const hook = textValue(cover.hook) ?? textValue(cover.title) ?? 'Hook cover';
  const backgroundTone = assetPreviewTone(background, 'linear-gradient(160deg, #101827, #334155)');
  const foregroundTone = assetPreviewTone(foreground, 'linear-gradient(135deg, #5eead4, #f8fafc)');
  const backgroundImageUrl = assetImageUrl(background);
  const foregroundImageUrl = assetImageUrl(foreground);
  const variant = hashString(textValue(cover.composition_id) ?? textValue(cover.title) ?? hook);
  const objectStyle = {
    background: foregroundTone,
    right: `${-18 + (variant % 18)}%`,
    bottom: `${8 + (variant % 24)}%`,
    width: `${48 + (variant % 18)}%`,
  };
  const objectImageStyle = {
    right: objectStyle.right,
    bottom: objectStyle.bottom,
    width: objectStyle.width,
  };
  const copyStyle =
    variant % 3 === 0
      ? { top: '9%', bottom: 'auto' }
      : variant % 3 === 1
        ? { top: '38%', bottom: 'auto' }
        : { bottom: '9%' };
  return (
    <section className="hook-cover-output" aria-label="Generated hook cover preview">
      <div className="hook-cover-preview" style={{ background: backgroundTone }}>
        {backgroundImageUrl ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img className="hook-cover-background-image" src={backgroundImageUrl} alt="Selected background asset" />
        ) : null}
        <div className="hook-cover-shine" />
        {foregroundImageUrl ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            className="hook-cover-object-image"
            src={foregroundImageUrl}
            alt="Selected foreground asset"
            style={objectImageStyle}
          />
        ) : (
          <div className="hook-cover-object" style={objectStyle} />
        )}
        <div className="hook-cover-copy" style={copyStyle}>
          <span>Hook / cover</span>
          <strong>{hook}</strong>
        </div>
      </div>
      <div className="hook-cover-meta">
        <span className="status-pill success">Local image</span>
        <span>{textValue(cover.title) ?? 'Asset-pack hook cover'}</span>
      </div>
    </section>
  );
}

export function HookImageCreator() {
  const backgrounds = assetLibrarySeed.filter((asset) => asset.kind === 'background');
  const placeableAssets = assetLibrarySeed.filter(
    (asset) => asset.kind === 'object' || asset.kind === 'hook',
  );
  const [selectedBackgroundId, setSelectedBackgroundId] = useState('steak-hook-bg');
  const [items, setItems] = useState<HookCanvasItem[]>(steakPresetItems);
  const [selectedItemId, setSelectedItemId] = useState<string | null>('steak-hook-copy-preset');
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const dragState = useRef<HookCanvasDragState | null>(null);

  const selectedBackground =
    backgrounds.find((asset) => asset.id === selectedBackgroundId) ?? backgrounds[0];
  const selectedItem = items.find((item) => item.id === selectedItemId) ?? null;
  const isSteakCanvas = selectedBackground.id === 'steak-hook-bg';

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

  function loadSteakPreset() {
    setSelectedBackgroundId('steak-hook-bg');
    setItems(steakPresetItems);
    setSelectedItemId('steak-hook-copy-preset');
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
        <span className="status-pill">Local only</span>
      </div>
      <button className="utility-button" type="button" onClick={loadSteakPreset}>
        Load steakpagetest screenshot preset
      </button>

      <div className="hook-creator-layout">
        <div className="hook-controls">
          <div className="hook-control-group">
            <div className="section-heading is-compact">
              <div>
                <h4>Background</h4>
                <p className="muted">Scroll and choose a reel plate.</p>
              </div>
            </div>
            <div className="hook-choice-strip" aria-label="Hook background choices">
              {backgrounds.map((asset) => (
                <button
                  className={
                    asset.id === selectedBackground.id ? 'hook-choice is-active' : 'hook-choice'
                  }
                  type="button"
                  key={asset.id}
                  onClick={() => setSelectedBackgroundId(asset.id)}
                >
                  <span className="asset-preview" style={{ background: asset.previewTone }} />
                  <strong>{asset.title}</strong>
                  <small>{asset.tags.join(', ')}</small>
                </button>
              ))}
            </div>
          </div>

          <div className="hook-control-group">
            <div className="section-heading is-compact">
              <div>
                <h4>Assets</h4>
                <p className="muted">Add seeded objects or hook copy to the local image.</p>
              </div>
            </div>
            <div className="hook-asset-picker">
              {placeableAssets.map((asset) => (
                <button
                  className="hook-asset-button"
                  type="button"
                  key={asset.id}
                  onClick={() => addItem(asset)}
                >
                  <span
                    className="asset-preview is-small"
                    style={{ background: asset.previewTone }}
                  />
                  <span>
                    <strong>{asset.title}</strong>
                    <small>{asset.layerSuitability}</small>
                  </span>
                </button>
              ))}
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
        </div>

        <div className="hook-canvas-wrap">
          <div
            className="hook-canvas"
            ref={canvasRef}
            style={{ background: selectedBackground.previewTone }}
            onPointerMove={continuePointer}
            onPointerUp={endPointer}
            onPointerCancel={endPointer}
            onPointerLeave={endPointer}
          >
            {isSteakCanvas ? <SteakHookScene /> : null}
            {selectedBackground.imageUrl && !isSteakCanvas ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                className="hook-canvas-background-image"
                src={selectedBackground.imageUrl}
                alt={selectedBackground.title}
              />
            ) : null}
            <div className="hook-safe-area" />
            {items.length === 0 ? (
              <div className="hook-empty-state">Choose assets to place on this reel template.</div>
            ) : null}
            {!isSteakCanvas ? items.map((item) => (
              <button
                className={
                  item.id === selectedItemId
                    ? 'hook-canvas-item is-selected'
                    : 'hook-canvas-item'
                }
                type="button"
                key={item.id}
                style={{
                  left: `${item.x}%`,
                  top: `${item.y}%`,
                  width: `${item.size}%`,
                  background: item.asset.previewTone,
                }}
                onPointerDown={(event) => beginMove(event, item)}
                onPointerUp={endPointer}
                onPointerCancel={endPointer}
              >
                <span>{item.asset.title}</span>
                {item.id === selectedItemId ? (
                  <span
                    className="hook-resize-handle"
                    aria-hidden="true"
                    onPointerDown={(event) => beginResize(event, item)}
                    onPointerUp={endPointer}
                    onPointerCancel={endPointer}
                  />
                ) : null}
              </button>
            )) : null}
          </div>
        </div>
      </div>
    </section>
  );
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

function mapAssetLibraryItemOut(row: AssetLibraryItemOut): AssetLibraryItem {
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
    previewTone: textValue(metadata.preview_tone) ?? previewToneForAsset(row.id, row.asset_kind, title),
    imageUrl: proxiedDownloadUrl(row.download?.url) ?? textValue(metadata.image_url) ?? undefined,
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
    imageUrl: textValue(asset.metadata.image_url) ?? undefined,
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

function planAssetCount(plan: AssetPackPlanResponse | null): number | null {
  if (!plan) {
    return null;
  }
  return Object.values(plan.asset_mix).reduce((sum, value) => sum + value, 0);
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

function formatGeneratedRunOption(run: RunRecord): string {
  const title =
    textValue(hookCoverPayload(run)?.title) ??
    textValue(asRecord(run.input_params?.composition_manifest)?.title) ??
    `Output ${run.id.slice(0, 8)}`;
  return `${title} - ${run.status}`;
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
  return textValue(metadata?.image_url);
}

function isSteakHookCover(cover: Record<string, unknown>): boolean {
  const sourcePlan = asRecord(cover.source_plan);
  const manifest = asRecord(sourcePlan?.composition_manifest);
  const metadata = asRecord(manifest?.metadata);
  if (textValue(metadata?.template) === 'instagram_steak_hook') {
    return true;
  }
  const roles = asRecord(cover.roles) ?? {};
  return Object.values(roles).some((role) => {
    const roleRecord = asRecord(role);
    const roleMetadata = asRecord(roleRecord?.metadata);
    return stringList(roleMetadata?.tags).includes('steakpagetest');
  });
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

function buildAssetPackPlan(planner: AssetPackPlannerState) {
  const total = Number.isFinite(planner.totalAssetCount) ? Math.max(0, planner.totalAssetCount) : 0;
  const specs = [
    {
      category: 'Backgrounds',
      count: Math.max(1, Math.round(total * 0.25)),
      reason: 'Reusable plates give each reel a distinct setting without regenerating full videos.',
    },
    {
      category: 'Transparent objects',
      count: Math.max(1, Math.round(total * 0.25)),
      reason: 'Foreground PNGs make product, subject, and proof variants composable.',
    },
    {
      category: 'Motion clips',
      count: Math.max(1, Math.round(total * 0.17)),
      reason: 'Short videos carry pacing and proof moments for higher-retention formats.',
    },
    {
      category: 'Hooks',
      count: Math.max(1, Math.round(total * 0.17)),
      reason: 'Hook copy lets the same visual assets support multiple angles.',
    },
    {
      category: 'Audio beds',
      count: Math.max(1, Math.round(total * 0.08)),
      reason: 'A small audio set keeps rhythm consistent while preserving edit variety.',
    },
    {
      category: 'Reference outputs',
      count: Math.max(1, Math.round(total * 0.08)),
      reason: 'Final outputs anchor style and performance expectations for future generations.',
    },
  ];
  const formats = planner.targetReelTypes
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
    .slice(0, 5);
  const warnings = [total < 12 ? 'Pack is small; combination variety may be limited.' : null].filter(
    (item): item is string => item !== null,
  );
  const notes = [
    ...warnings,
    planner.styleConstraints.trim()
      ? 'Style constraints are recorded for generation.'
      : 'Style constraints are optional; the planner can use defaults.',
    planner.split.trim()
      ? 'Asset split is recorded for review.'
      : 'Asset split is optional; the planner can infer categories.',
  ];
  return {
    specs,
    formats: formats.length ? formats : ['proof reel', 'product demo'],
    mixSummary: `${total} assets for ${planner.niche || 'selected page'} at ${planner.qualityLevel} quality`,
    outputPotential: `Estimated ${Math.max(3, Math.round(total * 1.8))} candidate reels`,
    notes: notes.length ? notes : ['No bottlenecks detected in the current plan.'],
    warningCount: warnings.length,
  };
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
    scores: {
      selection: outputScore / 100,
      compatibility: 0.82,
      diversity: 0.76,
      performance: outputScore / 100,
    },
    planner_context: {
      niche: planner.niche,
      requested_asset_count: planner.totalAssetCount,
      requested_split: planner.split,
      target_reel_types: planner.targetReelTypes,
      style_constraints: planner.styleConstraints,
      quality_level: planner.qualityLevel,
    },
    metadata: selectedCombinationHasTag(
      [selectedBackground, selectedObject, selectedHook, selectedAudio, selectedVideo],
      'steakpagetest',
    )
      ? {
          template: 'instagram_steak_hook',
          page_slug: 'steakpagetest',
          reference: 'uploaded Instagram steak hook screenshot recreation',
        }
      : {},
  };
}

function selectedCombinationHasTag(
  assets: (AssetLibraryItem | null)[],
  tag: string,
): boolean {
  return assets.some((asset) => asset?.tags.includes(tag));
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
