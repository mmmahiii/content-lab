'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import type { FormEvent, ReactNode } from 'react';

const ORG_ID = '7d3d7599-820e-4c8d-9c74-3d3b6d6f2785';

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

type ArtifactTab = 'video' | 'cover' | 'captions' | 'plan' | 'qa' | 'runway' | 'timeline' | 'trace' | 'raw';

type WorkspaceWorkbenchTab = 'two_button_reel_path' | 'asset_pack_generation';

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
};

type AssetPackPlannerState = {
  niche: string;
  totalAssetCount: number;
  split: string;
  targetReelTypes: string;
  styleConstraints: string;
  qualityLevel: 'lean' | 'balanced' | 'premium';
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

function availableArtifactTabs(packageDetail: PackageDetail | null, run: RunRecord | null): ArtifactTab[] {
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

function artifactForTab(packageDetail: PackageDetail | null, tab: ArtifactTab): PackageArtifact | null {
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

function firstFailureMessages(packageDetail: PackageDetail | null, run: RunRecord | null): string[] {
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

function runwayUsageSummary(run: RunRecord | null): { rows: string[]; raw: Record<string, unknown> | null } {
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
  const generationRuns = useMemo(
    () => runs.filter((run) => workflowStage(run) === 'package_generation'),
    [runs],
  );
  const selectedPackageRun = useMemo(
    () => generationRuns.find((run) => run.id === selectedPackageRunId) ?? generationRuns[0] ?? null,
    [generationRuns, selectedPackageRunId],
  );
  selectedPackageRunRef.current = selectedPackageRun;
  const selectedPackageRunLoadKey = selectedPackageRun
    ? `${selectedPackageRun.id}:${selectedPackageRun.status}`
    : '';
  const selectedPackagePlan = useMemo(() => {
    const planRunId = selectedPackageRun ? packagePlanRunId(selectedPackageRun) : null;
    return planRunId ? runs.find((run) => run.id === planRunId) ?? null : null;
  }, [runs, selectedPackageRun]);
  const selectedPlanPayload = planRecord(selectedPlan);
  const selectedPackagePlanPayload = planRecord(selectedPackagePlan);
  const selectedArtifact =
    artifactForTab(packageDetail, artifactTab) ?? fallbackArtifactForTab(selectedPackageRun, artifactTab);
  const selectedDownload = selectedArtifact?.download ?? extraDownloadForTab(packageDetail, artifactTab);
  const artifactTabs = availableArtifactTabs(packageDetail, selectedPackageRun);
  const failureMessages = firstFailureMessages(packageDetail, selectedPackageRun);
  const hasActiveGeneration = generationRuns.some((run) =>
    ['queued', 'running'].includes(run.status),
  );

  async function loadPages() {
    setIsLoading(true);
    try {
      const response = await fetch(`/api/orgs/${ORG_ID}/pages`, { cache: 'no-store' });
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
      const response = await fetch(`/api/orgs/${ORG_ID}/policy/page/${pageId}`, { cache: 'no-store' });
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
      const response = await fetch(`/api/orgs/${ORG_ID}/pages/${pageId}/runs`, { cache: 'no-store' });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const nextRuns = (await response.json()) as RunRecord[];
      const nextPlanRuns = nextRuns.filter(isPlanAvailable);
      const nextPackageRuns = nextRuns.filter((run) => workflowStage(run) === 'package_generation');
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
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not load workflow queue.');
    }
  }

  async function loadPackage(run: RunRecord) {
    setPackageNotice('');
    try {
      const response = await fetch(`/api/orgs/${ORG_ID}/packages/${run.id}`, { cache: 'no-store' });
      if (!response.ok) {
        if (response.status === 404) {
          setPackageDetail((current) => (current?.run_id === run.id ? current : null));
          setPackageNotice(
            run.status === 'failed'
              ? 'Artifacts not written.'
              : 'Package still running.',
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
    const intervalId = window.setInterval(() => {
      void loadRuns(selectedPage.id);
    }, hasActiveGeneration ? 2500 : 4000);
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
      const response = await fetch(`/api/orgs/${ORG_ID}/pages`, {
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
      const response = await fetch(`/api/orgs/${ORG_ID}/pages/${selectedPage.id}`, {
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
      const response = await fetch(`/api/orgs/${ORG_ID}/policy/page/${selectedPage.id}`, {
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
      const response = await fetch(`/api/orgs/${ORG_ID}/pages/${selectedPage.id}/idea-plans`, {
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
        `/api/orgs/${ORG_ID}/pages/${selectedPage.id}/idea-plans/${selectedPlan.id}/generate-package`,
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
        `/api/orgs/${ORG_ID}/pages/${selectedPage.id}/idea-plans/${selectedPlan.id}/discard`,
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
          <button className="utility-button" type="button" onClick={() => void loadPages()} disabled={isLoading}>
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
            <button className="danger-button" type="button" onClick={deleteSelectedPage} disabled={isSaving}>
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
              onChange={(event) => setForm((current) => ({ ...current, displayName: event.target.value }))}
              placeholder="New brand page"
            />
          </label>
          <label className="field">
            Handle
            <input
              value={form.handle}
              onChange={(event) => setForm((current) => ({ ...current, handle: event.target.value }))}
              placeholder="@new.page"
            />
          </label>
          <div className="field-row">
            <label className="field">
              Platform
              <select
                value={form.platform}
                onChange={(event) => setForm((current) => ({ ...current, platform: event.target.value }))}
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
                <p>{selectedPage.handle ?? 'No handle'} · Updated {formatDate(selectedPage.updated_at)}</p>
              </div>
              <div className="hero-metrics" aria-label="Page workflow counts">
                <span>{planRuns.length} queued</span>
                <span>{generationRuns.length} packages</span>
                <span>{formatPolicySource(policy)}</span>
              </div>
            </header>

            <nav className="tabs workbench-mode-tabs" role="tablist" aria-label="Generation workspace">
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

                  {generationRuns.length ? (
                    <>
                      <label className="field">
                        Generated package
                        <select
                          value={selectedPackageRun?.id ?? ''}
                          onChange={(event) => setSelectedPackageRunId(event.target.value)}
                        >
                          {generationRuns.map((run) => {
                            const sourcePlanId = packagePlanRunId(run);
                            const sourcePlan = sourcePlanId
                              ? runs.find((candidate) => candidate.id === sourcePlanId)
                              : null;
                            return (
                              <option key={run.id} value={run.id}>
                                {sourcePlan ? planTitle(sourcePlan) : `Package ${run.id.slice(0, 8)}`} ·{' '}
                                {generationMode(run) ?? 'package'} · {run.status}
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
                        <PlanSummary plan={selectedPackagePlanPayload} emptyLabel="No package plan" compact />
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
                            ? runErrorMessage(selectedPackageRun) ?? 'Artifacts not written.'
                            : packageNotice || 'Package still running.'}
                        </div>
                      )}
                    </>
                  ) : (
                    <div className="empty-state">No packages yet</div>
                  )}
                </section>
              </>
            ) : (
              <section
                className="asset-pack-workspace"
                id="workbench-panel-asset-pack"
                role="tabpanel"
                aria-labelledby="workbench-tab-asset-pack"
                aria-label="Asset pack based generation"
              >
                <AssetPackGenerationWorkspace
                  selectedPage={selectedPage}
                  queueCombination={() => setMessage('Asset-led reel composition queued for review.')}
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
  const hasLocalOutputs = Boolean(fallbackArtifactForTab(run, 'video') || fallbackArtifactForTab(run, 'cover'));
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
        <span>{artifact?.name ?? (activeTab === 'raw' ? 'package_detail' : tabLabel(activeTab))}</span>
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
            {artifactText || artifactTextStatus || formatJson(packageDetail ?? run?.output_payload ?? run)}
          </pre>
        ) : (
          <StructuredArtifactContent value={structuredContent} />
        )
      ) : null}
    </div>
  );
}

function AssetPackGenerationWorkspace({
  selectedPage,
  queueCombination,
}: {
  selectedPage: PageRecord;
  queueCombination: () => void;
}) {
  const [assetKind, setAssetKind] = useState<AssetLibraryKind>('background');
  const [planner, setPlanner] = useState<AssetPackPlannerState>({
    niche: selectedPage.handle ?? selectedPage.display_name,
    totalAssetCount: 24,
    split: '6 backgrounds, 6 transparent objects, 4 clips, 4 hooks, 2 audio, 2 reference outputs',
    targetReelTypes: 'proof reel, listicle, product demo, objection handling',
    styleConstraints: 'High contrast captions, clean product cutouts, mobile-first safe areas',
    qualityLevel: 'balanced',
  });

  const filteredAssets = assetLibrarySeed.filter((asset) => asset.kind === assetKind);
  const plan = buildAssetPackPlan(planner);
  const selectedBackground = bestAsset('background');
  const selectedObject = bestAsset('object');
  const selectedHook = bestAsset('hook');
  const selectedAudio = bestAsset('audio');
  const selectedVideo = bestAsset('video');
  const outputScore = Math.round(
    [selectedBackground, selectedObject, selectedHook, selectedAudio, selectedVideo].reduce(
      (sum, asset) => sum + asset.performanceScore,
      0,
    ) / 5,
  );

  return (
    <>
      <section className="generation-surface">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Asset library</p>
            <h3>Reusable assets</h3>
          </div>
          <span className="status-pill">{assetLibrarySeed.length} assets</span>
        </div>

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

        <div className="asset-library-grid">
          {filteredAssets.map((asset) => (
            <article className="asset-card" key={asset.id}>
              <div className="asset-preview" style={{ background: asset.previewTone }}>
                <span>{asset.kind.replace('_', ' ')}</span>
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
          ))}
        </div>
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
                onChange={(event) => setPlanner((current) => ({ ...current, niche: event.target.value }))}
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
                onChange={(event) => setPlanner((current) => ({ ...current, split: event.target.value }))}
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
              {plan.warningCount ? `${plan.warningCount} warning` : 'Ready'}
            </span>
          </div>

          <div className="review-summary">
            <span>{plan.mixSummary}</span>
            <span>{plan.outputPotential}</span>
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
              <h4>Warnings / bottlenecks</h4>
              <ul>
                {plan.warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            </div>
          </div>

          <div className="review-actions">
            <button className="primary-button" type="button">
              Approve pack plan
            </button>
            <button className="danger-button" type="button">
              Stop plan
            </button>
          </div>
        </section>
      </div>

      <section className="output-surface">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Asset combinator</p>
            <h3>Reel combinations</h3>
          </div>
          <button className="primary-button" type="button" onClick={queueCombination}>
            Queue render
          </button>
        </div>

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
      </section>
    </>
  );
}

function bestAsset(kind: AssetLibraryKind): AssetLibraryItem {
  return [...assetLibrarySeed]
    .filter((asset) => asset.kind === kind)
    .sort((left, right) => right.performanceScore - left.performanceScore)[0];
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
  const warnings = [
    total < 12 ? 'Pack is small; combination variety may be limited.' : null,
    planner.styleConstraints.trim() ? null : 'No style constraints recorded.',
    planner.split.trim() ? null : 'No explicit split recorded; planner will infer categories.',
  ].filter((item): item is string => item !== null);
  return {
    specs,
    formats: formats.length ? formats : ['proof reel', 'product demo'],
    mixSummary: `${total} assets for ${planner.niche || 'selected page'} at ${planner.qualityLevel} quality`,
    outputPotential: `Estimated ${Math.max(3, Math.round(total * 1.8))} candidate reels`,
    warnings: warnings.length ? warnings : ['No bottlenecks detected in the current plan.'],
    warningCount: warnings.length,
  };
}

function CombinationSlot({ label, asset }: { label: string; asset: AssetLibraryItem }) {
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
          <li key={`${keyPrefix}-${index}`}>{renderArtifactValue(item, `${keyPrefix}-${index}`)}</li>
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
          Total {Object.values(policyDraft.mode_ratios).reduce((sum, value) => sum + value, 0).toFixed(2)}
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
