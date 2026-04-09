export type UUID = string;
export type ISODateTimeString = string;
export type ISODateString = ISODateTimeString;

export type JsonPrimitive = boolean | number | string | null;
export type JsonValue = JsonPrimitive | JsonObject | JsonArray;

export interface JsonObject {
  [key: string]: JsonValue | undefined;
}

export type JsonArray = JsonValue[];

export interface HealthResponse {
  status: string;
}

export type PageOwnership = 'owned' | 'competitor';
export type PageKind = PageOwnership;
export type PersonaExtensionValue = string | string[];

export interface PersonaProfileInput {
  label: string;
  audience: string;
  brand_tone?: string[];
  content_pillars: string[];
  differentiators?: string[];
  primary_call_to_action?: string | null;
  extensions?: Record<string, PersonaExtensionValue>;
}

export interface PersonaProfile {
  label: string;
  audience: string;
  brand_tone: string[];
  content_pillars: string[];
  differentiators: string[];
  primary_call_to_action: string | null;
  extensions: Record<string, PersonaExtensionValue>;
}

export interface PageConstraintsInput {
  banned_topics?: string[];
  blocked_phrases?: string[];
  required_disclosures?: string[];
  prohibited_claims?: string[];
  preferred_languages?: string[];
  allow_direct_cta?: boolean;
  max_script_words?: number | null;
  max_hashtags?: number | null;
}

export interface PageConstraints {
  banned_topics: string[];
  blocked_phrases: string[];
  required_disclosures: string[];
  prohibited_claims: string[];
  preferred_languages: string[];
  allow_direct_cta: boolean;
  max_script_words: number | null;
  max_hashtags: number | null;
}

export interface PageMetadataInput {
  persona?: PersonaProfileInput | null;
  constraints?: PageConstraintsInput;
  [key: string]: JsonValue | PageConstraintsInput | PersonaProfileInput | null | undefined;
}

export interface PageMetadata {
  persona: PersonaProfile | null;
  constraints: PageConstraints;
  [key: string]: JsonValue | PageConstraints | PersonaProfile | null | undefined;
}

export interface PageCreate {
  platform: string;
  display_name: string;
  external_page_id?: string | null;
  handle?: string | null;
  ownership?: PageOwnership;
  metadata?: PageMetadataInput;
}

export interface PageUpdate {
  display_name?: string;
  external_page_id?: string | null;
  handle?: string | null;
  ownership?: PageOwnership;
  metadata?: PageMetadataInput;
}

export interface PageOut {
  id: UUID;
  org_id: UUID;
  platform: string;
  display_name: string;
  external_page_id: string | null;
  handle: string | null;
  ownership: PageOwnership;
  metadata: PageMetadata;
  created_at: ISODateTimeString;
  updated_at: ISODateTimeString;
}

export type PolicyScopeType = 'global' | 'page' | 'niche';

export interface PolicyModeRatios {
  exploit: number;
  explore: number;
  mutation: number;
  chaos: number;
}

export interface PolicyBudgetGuardrails {
  per_run_usd_limit: number;
  daily_usd_limit: number;
  monthly_usd_limit: number;
}

export interface PolicySimilarityThresholds {
  warn_at: number;
  block_at: number;
}

export interface PolicyThresholds {
  similarity: PolicySimilarityThresholds;
  min_quality_score: number;
}

export interface PolicyStateDocument {
  mode_ratios: PolicyModeRatios;
  budget: PolicyBudgetGuardrails;
  thresholds: PolicyThresholds;
}

export interface PolicyStateUpdate {
  mode_ratios?: PolicyModeRatios;
  budget?: PolicyBudgetGuardrails;
  thresholds?: PolicyThresholds;
}

export interface PolicyStateOut {
  id: UUID;
  org_id: UUID;
  scope_type: PolicyScopeType;
  scope_id: string | null;
  state: PolicyStateDocument;
  updated_at: ISODateTimeString;
}

export type ReelOrigin = 'generated' | 'observed';

export type GeneratedReelStatus =
  | 'draft'
  | 'planning'
  | 'generating'
  | 'editing'
  | 'qa'
  | 'qa_failed'
  | 'ready'
  | 'posted'
  | 'archived';

export type ObservedReelStatus = 'active' | 'removed' | 'unavailable';
export type ReelStatus = GeneratedReelStatus | ObservedReelStatus;

export interface ReelReviewInfo {
  approved_at: ISODateTimeString;
  approved_by: string | null;
}

export interface ReelPostingInfo {
  posted_at: ISODateTimeString;
  posted_by: string | null;
}

export interface ReelMetadata {
  review?: ReelReviewInfo;
  posting?: ReelPostingInfo;
  [key: string]: JsonValue | ReelPostingInfo | ReelReviewInfo | undefined;
}

export type ReelFamilyMode = 'exploit' | 'explore' | 'mutation' | 'chaos';

export interface ReelVariantSummary {
  id: UUID;
  origin: ReelOrigin;
  status: ReelStatus;
  variant_label: string | null;
  external_reel_id: string | null;
  created_at: ISODateTimeString;
  updated_at: ISODateTimeString;
}

export interface ReelFamilyCreate {
  name: string;
  mode?: ReelFamilyMode;
  metadata?: JsonObject;
}

export interface ReelFamilyOut {
  id: UUID;
  org_id: UUID;
  page_id: UUID;
  name: string;
  mode: ReelFamilyMode;
  metadata: JsonObject;
  variant_count: number;
  variants: ReelVariantSummary[];
  created_at: ISODateTimeString;
  updated_at: ISODateTimeString;
}

export interface ReelCreate {
  origin?: 'generated';
  status?: GeneratedReelStatus;
  variant_label: string;
  external_reel_id?: string | null;
  metadata?: JsonObject;
}

export interface ReelOut {
  id: UUID;
  org_id: UUID;
  page_id: UUID;
  reel_family_id: UUID;
  origin: ReelOrigin;
  status: ReelStatus;
  variant_label: string | null;
  external_reel_id: string | null;
  metadata: ReelMetadata;
  approved_at: ISODateTimeString | null;
  approved_by: string | null;
  posted_at: ISODateTimeString | null;
  posted_by: string | null;
  created_at: ISODateTimeString;
  updated_at: ISODateTimeString;
}

export type WorkflowKey = 'daily_reel_factory' | 'process_reel';
export type FlowTrigger = 'unknown' | 'manual' | 'reel_trigger';
export type RunStatus = 'pending' | 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled';
export type TaskStatus =
  | 'pending'
  | 'queued'
  | 'running'
  | 'retrying'
  | 'succeeded'
  | 'failed'
  | 'skipped'
  | 'cancelled';

export interface RunCreate {
  workflow_key: WorkflowKey;
  input_params?: JsonObject;
  idempotency_key?: string | null;
  metadata?: JsonObject;
}

export interface ReelTriggerCreate {
  input_params?: JsonObject;
  idempotency_key?: string | null;
  metadata?: JsonObject;
}

export interface TaskSummaryOut {
  id: UUID;
  task_type: string;
  status: TaskStatus;
  idempotency_key: string;
  payload: JsonObject;
  result: JsonObject | null;
  created_at: ISODateTimeString;
  updated_at: ISODateTimeString;
}

export interface RunMetadata extends JsonObject {
  submitted_via?: string;
  flow_trigger?: FlowTrigger;
  actor?: JsonObject;
  request?: JsonObject;
  client?: JsonObject;
  target?: JsonObject;
  orchestration?: JsonObject;
}

export interface RunOut {
  id: UUID;
  org_id: UUID;
  workflow_key: WorkflowKey;
  flow_trigger: FlowTrigger;
  status: RunStatus;
  idempotency_key: string | null;
  external_ref: string | null;
  input_params: JsonObject;
  output_payload: JsonObject | null;
  run_metadata: RunMetadata;
  started_at: ISODateTimeString | null;
  finished_at: ISODateTimeString | null;
  created_at: ISODateTimeString;
  updated_at: ISODateTimeString;
}

export interface RunDetailOut extends RunOut {
  tasks: TaskSummaryOut[];
  task_status_counts: Partial<Record<TaskStatus, number>>;
}

export interface SignedDownloadOut {
  storage_uri: string;
  url: string;
  expires_at: ISODateTimeString;
}

export interface PackageArtifactOut {
  name: string;
  storage_uri: string;
  kind: string | null;
  content_type: string | null;
  metadata: JsonObject;
  download: SignedDownloadOut;
}

export type PackageManifestMetadata = JsonObject;
export type PackageProvenance = JsonObject;

export interface PackageDetailOut {
  run_id: UUID;
  org_id: UUID;
  status: RunStatus;
  workflow_key: WorkflowKey;
  reel_id: UUID | null;
  package_root_uri: string | null;
  manifest_uri: string | null;
  manifest_metadata: PackageManifestMetadata;
  manifest_download: SignedDownloadOut | null;
  provenance: PackageProvenance;
  provenance_uri: string | null;
  provenance_download: SignedDownloadOut | null;
  artifacts: PackageArtifactOut[];
  created_at: ISODateTimeString;
  updated_at: ISODateTimeString;
}

export type RunCreateRequest = {
  workflow_key: WorkflowKey;
  input_params: JsonObject;
  metadata: JsonObject;
  idempotency_key?: string | null;
};

export type ReelTriggerRequest = {
  input_params: JsonObject;
  metadata: JsonObject;
  idempotency_key?: string | null;
};

export type ReelResponse = ReelOut;
export type RunResponse = RunOut;
export type TaskSummaryResponse = TaskSummaryOut;
export type RunDetailResponse = RunDetailOut;

export interface ApiValidationIssue {
  loc?: Array<string | number>;
  msg?: string;
  type?: string;
}

export type ApiErrorDetail = string | ApiValidationIssue[] | JsonObject | null;

export interface ApiErrorResponse {
  detail?: ApiErrorDetail;
}
