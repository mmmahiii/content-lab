export type HealthResponse = {
  status: string;
};

export type WorkflowKey = 'daily_reel_factory' | 'process_reel';

export type FlowTrigger = 'unknown' | 'manual' | 'reel_trigger';

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

export type JsonObject = Record<string, unknown>;

export type RunCreateRequest = {
  workflow_key: WorkflowKey;
  input_params: JsonObject;
  idempotency_key?: string | null;
  metadata: JsonObject;
};

export type ReelTriggerRequest = {
  input_params: JsonObject;
  idempotency_key?: string | null;
  metadata: JsonObject;
};

export type ReelReviewInfo = {
  approved_at: string;
  approved_by?: string | null;
};

export type ReelPostingInfo = {
  posted_at: string;
  posted_by?: string | null;
};

export type ReelResponse = {
  id: string;
  org_id: string;
  page_id: string;
  reel_family_id: string;
  origin: ReelOrigin;
  status: ReelStatus;
  variant_label: string | null;
  external_reel_id: string | null;
  metadata: JsonObject;
  approved_at: string | null;
  approved_by: string | null;
  posted_at: string | null;
  posted_by: string | null;
  created_at: string;
  updated_at: string;
};

export type RunResponse = {
  id: string;
  org_id: string;
  workflow_key: WorkflowKey;
  flow_trigger: FlowTrigger;
  status: string;
  idempotency_key: string | null;
  external_ref: string | null;
  input_params: JsonObject;
  output_payload: JsonObject | null;
  run_metadata: JsonObject;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  updated_at: string;
};

export type TaskSummaryResponse = {
  id: string;
  task_type: string;
  status: string;
  idempotency_key: string;
  payload: JsonObject;
  result: JsonObject | null;
  created_at: string;
  updated_at: string;
};

export type RunDetailResponse = RunResponse & {
  tasks: TaskSummaryResponse[];
  task_status_counts: Record<string, number>;
};

export type ApiValidationIssue = {
  loc?: Array<string | number>;
  msg?: string;
  type?: string;
};

export type ApiErrorDetail = string | ApiValidationIssue[] | JsonObject | null;

export type ApiErrorResponse = {
  detail?: ApiErrorDetail;
};
