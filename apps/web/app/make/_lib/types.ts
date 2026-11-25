/**
 * Shapes of the API responses Quick Reel uses (snake_case, as FastAPI returns them).
 * Source of truth: packages/creative/src/content_lab_creative/generation/{hooks,branches}.py
 * and apps/api/src/content_lab_api/schemas/{pages,assets,asset_packs,reels}.py.
 */
import type { Energy, PipelineOverlayCue } from '@content-lab/reel-templates';

export type Moment = 'structure' | 'energy' | 'ending';
export const MOMENTS: readonly Moment[] = ['structure', 'energy', 'ending'];

export interface Org {
  id: string;
  name: string;
  slug: string;
}

export interface PagePersona {
  label?: string | null;
  audience?: string | null;
  content_pillars?: string[];
  primary_call_to_action?: string | null;
}

export interface Page {
  id: string;
  org_id: string;
  platform: string;
  display_name: string;
  handle: string | null;
  metadata: {
    niche?: string | null;
    persona?: PagePersona | null;
    constraints?: { allow_direct_cta?: boolean } | null;
    [key: string]: unknown;
  };
}

export interface HookCandidate {
  mechanism: string;
  overlay_text: string;
  spoken_line: string;
  visual_direction: string;
  payoff_promise: string;
}

export interface HookGenerationResult {
  hooks: HookCandidate[];
  source: 'llm' | 'fallback';
  niche: string;
  fallback_reason?: string | null;
}

export interface ContinuationBeat {
  narration: string;
  overlay_text: string;
  shot_direction: string;
  seconds: number;
}

interface OptionBase {
  option_id: string;
  label: string;
  teaser: string;
}

export interface StructureOption extends OptionBase {
  beats: ContinuationBeat[];
}

export interface EnergyOption extends OptionBase {
  pace: Energy;
  duration_scale: number;
  music_mood: string;
}

export interface EndingOption extends OptionBase {
  style: string;
  beat: ContinuationBeat;
}

export interface BranchSet {
  structure: StructureOption[];
  energy: EnergyOption[];
  ending: EndingOption[];
}

export type ChoiceOption = StructureOption | EnergyOption | EndingOption;

export interface Selection {
  structure: string;
  energy: string;
  ending: string;
}

export interface ComposedScene {
  scene_id: string;
  purpose: string;
  start_seconds: number;
  end_seconds: number;
  narration: string;
  overlay_text: string;
  overlay_role: string;
  shot_guidance: string;
}

export interface ComposedReel {
  selection: Selection;
  duration_seconds: number;
  pace: Energy;
  music_mood: string;
  ending_style: string;
  overlay_timeline: PipelineOverlayCue[];
  spoken_script: Array<{
    start_seconds: number;
    end_seconds: number;
    narration: string;
    shot_direction?: string | null;
  }>;
  scenes: ComposedScene[];
}

export interface BranchGenerationResult {
  hook: HookCandidate;
  moments: Moment[];
  branches: BranchSet;
  default_selection: Selection;
  preview: ComposedReel;
  source: 'llm' | 'fallback';
  niche: string;
}

export interface AssetPack {
  id: string;
  name: string;
  niche: string;
  status: string;
  actual_asset_count: number;
}

export interface AssetLibraryItem {
  id: string;
  asset_class: string;
  asset_kind: string | null;
  media_type: string | null;
  tags: string[];
  has_transparency: boolean | null;
  ready_status: string;
  metadata: Record<string, unknown>;
}

export interface ReelOut {
  id: string;
  page_id: string;
  reel_family_id: string;
  status: string;
  variant_label: string | null;
}

export type RenderStatus = 'queued' | 'rendering' | 'done' | 'failed' | 'cancelled';

export interface RenderJobView {
  renderId: string;
  status: RenderStatus;
  progress: number;
  error: string | null;
  durationSeconds: number;
  width: number;
  height: number;
  fps: number;
  overlayTraceStatus: 'pass' | 'fail' | null;
  videoUrl: string | null;
  traceUrl: string | null;
}
