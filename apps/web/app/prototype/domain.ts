/** Prototype domain. These are UI contracts, not claims about existing API support. */
export type Role = 'owner' | 'editor' | 'reviewer' | 'viewer';
export type Scenario = 'portfolio' | 'empty' | 'unavailable' | 'loading';
export type Family = 'graphic' | 'product' | 'video';
export type ProductionMode = 'existing_assets' | 'hybrid' | 'template';
export interface Money { minor: number; currency: 'GBP' }
export interface PageProfile {
  id: string; name: string; handle: string; purpose: string; audience: string;
  voice: string; topics: string[]; color: string; locale: string; format: string;
  disclosures: string; budgetMinor: number; policyOverride: boolean;
}
export interface Idea {
  id: string; pageId: string; title: string; summary: string; evidence: string;
  freshness: 'fresh' | 'expiring' | 'expired'; fit: string;
  status: 'suggested' | 'held' | 'rejected' | 'drafted'; family: Family;
}
export type AssetKind = 'product' | 'environment' | 'footage' | 'music' | 'voice' | 'graphic';
export interface Asset {
  id: string; name: string; kind: AssetKind; tags: string[]; currentVersionId: string;
  usageCount: number; origin: 'demo' | 'uploaded' | 'generated' | 'derived';
}
export interface AssetVersion { id: string; assetId: string; number: number; parentId?: string; description: string }
export interface Representation {
  id: string; assetVersionId: string; mediaType: 'image' | 'video' | 'audio' | 'text';
  src: string; width: number; height: number; durationFrames?: number;
  readiness: 'ready' | 'quarantined' | 'processing' | 'failed' | 'withdrawn';
  rights: 'eligible' | 'review_required' | 'restricted'; rightsNote: string;
  capabilities: string[]; derivedFromId?: string;
}
export interface AssetSelection { assetId: string; mandatory: boolean }
export interface Hook { id: string; name: string; text: string; mechanism: string; hypothesis: string; color: string }
export interface Blueprint { id: string; name: string; description: string; segments: string[]; prerequisite: string }
export interface Brief { objective: string; audienceValue: string; tone: string; claims: string; evidence: string; payoff: string }
export interface SceneInstance {
  id: string; name: string; assetId?: string; assetVersionId?: string; representationId?: string;
  kind: 'image' | 'video' | 'text' | 'shape'; text?: string; color: string;
  x: number; y: number; width: number; height: number; rotation: number; opacity: number;
  startFrame: number; endFrame: number; sourceInFrame: number; layer: number;
  relation: 'independent' | 'on_surface' | 'behind' | 'overlay'; targetInstanceId?: string;
  protectedProperties: string[];
}
export interface AudioEvent { id: string; representationId: string; role: 'voice' | 'music'; startFrame: number; endFrame: number; gain: number }
export interface Scene {
  id: string; name: string; purpose: string; startFrame: number; endFrame: number;
  background: string; instances: SceneInstance[]; audio: AudioEvent[];
}
export interface Composition {
  title: string; brief: Brief; hookId: string; blueprintId: string; mode: ProductionMode;
  fps: { numerator: number; denominator: number }; canvas: { width: number; height: number };
  totalFrames: number; scenes: Scene[]; selectedAssets: AssetSelection[];
  caption: string; disclosures: string; coverFrame: number;
}
export interface ContentItem {
  id: string; pageId: string; family: Family; draft: Composition; currentRevisionId?: string;
  updatedAt: string; stage: 'draft' | 'blocked' | 'in_progress' | 'review' | 'approved' | 'published';
}
export interface Revision {
  id: string; contentId: string; number: number; parentId?: string; createdAt: string;
  composition: Composition; previewCreated: boolean;
}
export interface Finding {
  id: string; category: 'timing' | 'assets' | 'text' | 'rights' | 'identity' | 'editorial' | 'package';
  severity: 'fail' | 'warning' | 'pass' | 'not_evaluated'; title: string; detail: string;
  evidence: 'local_check' | 'simulated'; sceneId?: string; instanceId?: string; frame?: number;
}
export interface RunStage { name: string; status: 'pending' | 'running' | 'succeeded' | 'failed'; detail: string }
export interface Run {
  id: string; contentId: string; revisionId: string;
  status: 'queued' | 'running' | 'succeeded' | 'failed' | 'outcome_unknown' | 'blocked';
  kind: 'render' | 'candidate'; stages: RunStage[]; attempt: number;
  estimate: Money; reserved: Money; spent: Money; uncertain: Money;
  error?: string; completesAt?: number; createdAt: string;
}
export interface PackageRecord {
  id: string; contentId: string; revisionId: string; runId: string;
  status: 'review' | 'approved' | 'rejected'; findings: Finding[];
  approvedBy?: Role; approvedAt?: string; approvalId?: string; rejectionReason?: string;
  /** Frozen composition is reached via revisionId; no encoded media is fabricated. */
  copy: string; disclosures: string; coverFrame: number;
}
export interface Publication {
  id: string; packageId: string; contentId: string; approvalId: string;
  account: string; timezone: string; scheduledAt?: string;
  status: 'prepared' | 'scheduled' | 'published'; externalReference?: string; postedAt?: string;
  simulated: true;
}
export interface PackItem {
  id: string; name: string; kind: AssetKind; reason: string;
  route: 'reuse' | 'transform' | 'upload' | 'generate'; cost: Money;
  status: 'planned' | 'ready' | 'processing' | 'failed' | 'missing'; assetId?: string; error?: string;
}
export interface AssetPack {
  id: string; name: string; pageId: string; requestedCount: number; mix: string; style: string;
  budget: Money; status: 'planned' | 'authorised' | 'partial' | 'ready'; items: PackItem[];
}
export interface MetricObservation {
  id: string; publicationId: string; views: number | null; retention: number | null;
  maturity: 'maturing' | 'mature' | 'unavailable'; window: string; source: string;
}
export interface Experiment {
  id: string; name: string; contentIds: string[]; metric: string; windowDays: number;
  stoppingRule: string; status: 'planned' | 'observing'; conclusion: string;
}
export interface LearningSuggestion {
  id: string; title: string; reason: string; pageId: string;
  status: 'proposed' | 'accepted' | 'dismissed'; change: string;
}
export interface WorkspaceState {
  schemaVersion: 1; scenario: Scenario; role: Role; pages: PageProfile[]; ideas: Idea[];
  assets: Asset[]; assetVersions: AssetVersion[]; representations: Representation[];
  hooks: Hook[]; blueprints: Blueprint[]; contents: ContentItem[]; revisions: Revision[];
  runs: Run[]; packages: PackageRecord[]; publications: Publication[]; packs: AssetPack[];
  metrics: MetricObservation[]; experiments: Experiment[]; suggestions: LearningSuggestion[];
  recoveryNotice?: string;
}
export type Command =
  | { type: 'setRole'; role: Role }
  | { type: 'savePage'; page: PageProfile }
  | { type: 'createIdea'; idea: Omit<Idea, 'id' | 'status'> }
  | { type: 'setIdeaStatus'; ideaId: string; status: Idea['status'] }
  | { type: 'createContent'; pageId: string; title?: string; family?: Family; ideaId?: string; assetIds?: string[]; packId?: string }
  | { type: 'updateDraft'; contentId: string; draft: Composition }
  | { type: 'saveRevision' | 'createPreview' | 'renderRevision' | 'repairPlan' | 'newCandidate'; contentId: string }
  | { type: 'retryRun' | 'reconcileRun'; runId: string }
  | { type: 'approvePackage'; packageId: string }
  | { type: 'rejectPackage'; packageId: string; reason: string }
  | { type: 'preparePublication'; packageId: string; account: string; timezone: string; scheduledAt?: string }
  | { type: 'recordPost'; publicationId: string; externalReference: string; postedAt: string }
  | { type: 'planPack'; name: string; pageId: string; count: number; mix: string; style: string; budgetMinor: number }
  | { type: 'authorizePack' | 'fulfillPack'; packId: string }
  | { type: 'retryPackItem'; packId: string; itemId: string }
  | { type: 'registerAsset'; name: string; kind: AssetKind; mediaType: Representation['mediaType']; rightsNote: string }
  | { type: 'reviewAsset'; representationId: string; eligible: boolean }
  | { type: 'createExperiment'; name: string; contentIds: string[]; metric: string; windowDays: number; stoppingRule: string }
  | { type: 'reviewSuggestion'; suggestionId: string; decision: 'accepted' | 'dismissed' }
  | { type: 'recordMetrics'; publicationId: string; views: number; retention: number | null };
export type CommandResult =
  | { ok: true; state: WorkspaceState; message: string; entityId?: string }
  | { ok: false; kind: 'validation' | 'blocked' | 'permission' | 'failed'; message: string; fields?: Record<string, string> };
export interface OperatorService {
  load(): Promise<WorkspaceState>;
  execute(command: Command): Promise<CommandResult>;
  reset(scenario?: Scenario): Promise<WorkspaceState>;
  subscribe(listener: (state: WorkspaceState) => void): () => void;
  dispose(): void;
}
export interface WorkspaceProps {
  state: WorkspaceState;
  execute: (command: Command) => Promise<CommandResult>;
  navigate: (view: string, id?: string, tab?: string, detail?: string) => void;
}
export function money(value: Money | number): string {
  return new Intl.NumberFormat('en-GB', { style: 'currency', currency: typeof value === 'number' ? 'GBP' : value.currency }).format((typeof value === 'number' ? value : value.minor) / 100);
}
export function representationFor(state: WorkspaceState, assetId: string): Representation | undefined {
  const asset = state.assets.find(a => a.id === assetId);
  return state.representations.find(r => r.assetVersionId === asset?.currentVersionId);
}
export function canEdit(role: Role): boolean { return role === 'owner' || role === 'editor'; }
export function canReview(role: Role): boolean { return role === 'owner' || role === 'reviewer'; }
