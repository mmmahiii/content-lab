export type UUID = string;
export type ISODateString = string;

export type JsonPrimitive = boolean | number | string | null;
export type JsonValue = JsonPrimitive | JsonObject | JsonValue[];
export type JsonObject = {
  [key: string]: JsonValue | undefined;
};

export type HealthResponse = {
  status: string;
};

export type PersonaExtensionValue = string | string[];

export type PersonaProfile = {
  label: string;
  audience: string;
  brand_tone: string[];
  content_pillars: string[];
  differentiators: string[];
  primary_call_to_action?: string | null;
  extensions: Record<string, PersonaExtensionValue>;
};

export type PageConstraints = {
  banned_topics: string[];
  blocked_phrases: string[];
  required_disclosures: string[];
  prohibited_claims: string[];
  preferred_languages: string[];
  allow_direct_cta: boolean;
  max_script_words?: number | null;
  max_hashtags?: number | null;
};

export type PageMetadata = {
  persona?: PersonaProfile | null;
  constraints: PageConstraints;
} & Record<string, unknown>;

export type PageOwnership = 'owned' | 'competitor';

export type PageOut = {
  id: UUID;
  org_id: UUID;
  platform: string;
  display_name: string;
  external_page_id: string | null;
  handle: string | null;
  ownership: PageOwnership;
  metadata: PageMetadata;
  created_at: ISODateString;
  updated_at: ISODateString;
};

export type PolicyScopeType = 'global' | 'page' | 'niche';

export type PolicyModeRatios = {
  exploit: number;
  explore: number;
  mutation: number;
  chaos: number;
};

export type PolicyBudgetGuardrails = {
  per_run_usd_limit: number;
  daily_usd_limit: number;
  monthly_usd_limit: number;
};

export type PolicySimilarityThresholds = {
  warn_at: number;
  block_at: number;
};

export type PolicyThresholds = {
  similarity: PolicySimilarityThresholds;
  min_quality_score: number;
};

export type PolicyStateDocument = {
  mode_ratios: PolicyModeRatios;
  budget: PolicyBudgetGuardrails;
  thresholds: PolicyThresholds;
};

export type PolicyStateOut = {
  id: UUID;
  org_id: UUID;
  scope_type: PolicyScopeType;
  scope_id?: string | null;
  state: PolicyStateDocument;
  updated_at: ISODateString;
};

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

export type ReelOut = {
  id: UUID;
  org_id: UUID;
  page_id: UUID;
  reel_family_id: UUID;
  origin: ReelOrigin;
  status: ReelStatus;
  variant_label: string | null;
  external_reel_id: string | null;
  metadata: Record<string, unknown>;
  approved_at?: ISODateString | null;
  approved_by?: string | null;
  posted_at?: ISODateString | null;
  posted_by?: string | null;
  created_at: ISODateString;
  updated_at: ISODateString;
};

export type WorkflowKey = 'daily_reel_factory' | 'process_reel';
export type FlowTrigger = 'unknown' | 'manual' | 'reel_trigger';

export type TaskSummaryOut = {
  id: UUID;
  task_type: string;
  status: string;
  idempotency_key: string;
  payload: Record<string, unknown>;
  result: Record<string, unknown> | null;
  created_at: ISODateString;
  updated_at: ISODateString;
};

export type RunOut = {
  id: UUID;
  org_id: UUID;
  workflow_key: WorkflowKey;
  flow_trigger: FlowTrigger;
  status: string;
  idempotency_key: string | null;
  external_ref: string | null;
  input_params: Record<string, unknown>;
  output_payload: Record<string, unknown> | null;
  run_metadata: Record<string, unknown>;
  started_at: ISODateString | null;
  finished_at: ISODateString | null;
  created_at: ISODateString;
  updated_at: ISODateString;
};

export type RunDetailOut = RunOut & {
  tasks: TaskSummaryOut[];
  task_status_counts: Record<string, number>;
};

export type SignedDownloadOut = {
  storage_uri: string;
  url: string;
  expires_at: ISODateString;
};

export type PackageArtifactOut = {
  name: string;
  storage_uri: string;
  kind?: string | null;
  content_type?: string | null;
  metadata: Record<string, unknown>;
  download: SignedDownloadOut;
};

export type PackageDetailOut = {
  run_id: UUID;
  org_id: UUID;
  status: string;
  workflow_key: WorkflowKey;
  reel_id?: UUID | null;
  package_root_uri?: string | null;
  manifest_uri?: string | null;
  manifest_metadata: Record<string, unknown>;
  manifest_download?: SignedDownloadOut | null;
  provenance: Record<string, unknown>;
  provenance_uri?: string | null;
  provenance_download?: SignedDownloadOut | null;
  artifacts: PackageArtifactOut[];
  created_at: ISODateString;
  updated_at: ISODateString;
};
