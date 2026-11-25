import type { HookCandidate, Moment, Selection } from './types';
import type { PartialSelection } from './selection';

/**
 * Quick Reel flow as a pure reducer.
 *
 *   seed ─▶ hooks (swipe) ─▶ play hook ─▶ choose structure ─▶ play first beat
 *        ─▶ choose energy ─▶ play rest of story ─▶ choose ending ─▶ play ending
 *        ─▶ drop (full replay, no UI) ─▶ ship
 *
 * "Surprise me" jumps to the drop with random remaining choices; Remix re-rolls the
 * choices (same hook) and replays the drop; "Change one thing" reopens one choice, then
 * plays on to the end with the other choices kept.
 */

export type Segment = 'hook' | 'firstBeat' | 'restBeats' | 'ending';
export const SEGMENTS: readonly Segment[] = ['hook', 'firstBeat', 'restBeats', 'ending'];

/** The segment a choice moment unlocks, and the moment a segment ends on. */
export const SEGMENT_AFTER: Record<Moment, Segment> = {
  structure: 'firstBeat',
  energy: 'restBeats',
  ending: 'ending',
};
export const MOMENT_AFTER: Record<Segment, Moment | null> = {
  hook: 'structure',
  firstBeat: 'energy',
  restBeats: 'ending',
  ending: null,
};

export type Phase =
  | { name: 'seed' }
  | { name: 'hooks' }
  | { name: 'playing'; segment: Segment }
  | { name: 'choosing'; moment: Moment }
  | { name: 'drop' }
  | { name: 'ship' };

export interface SeedInput {
  orgId: string;
  pageId: string;
  topic: string;
  surprise: boolean;
}

export interface QuickReelState {
  phase: Phase;
  seed: SeedInput | null;
  hooks: HookCandidate[] | null;
  hookSource: 'llm' | 'fallback' | null;
  /** The hook shown in the hook reel. */
  focusedHook: number;
  /** The hook the reel is built on (set when chosen). */
  hookIndex: number | null;
  selection: PartialSelection;
  /** `change`: after re-choosing one moment, play through to the end without pausing. */
  mode: 'build' | 'change';
  error: string | null;
  /** Bumps on every drop so the player restarts from frame 0. */
  dropCount: number;
}

export const initialState: QuickReelState = {
  phase: { name: 'seed' },
  seed: null,
  hooks: null,
  hookSource: null,
  focusedHook: 0,
  hookIndex: null,
  selection: {},
  mode: 'build',
  error: null,
  dropCount: 0,
};

export type QuickReelEvent =
  | { type: 'SEED'; seed: SeedInput }
  | { type: 'HOOKS_LOADED'; hooks: HookCandidate[]; source: 'llm' | 'fallback' }
  | { type: 'FAILED'; message: string }
  | { type: 'FOCUS_HOOK'; index: number }
  | { type: 'CHOOSE_HOOK'; index?: number }
  | { type: 'SEGMENT_ENDED'; segment: Segment }
  | { type: 'CHOOSE'; moment: Moment; optionId: string }
  | { type: 'SURPRISE'; hookIndex: number; selection: Selection }
  | { type: 'DROP_ENDED' }
  | { type: 'REMIX'; selection: Selection }
  | { type: 'CHANGE_ONE'; moment: Moment }
  | { type: 'RESTART' };

export function reducer(state: QuickReelState, event: QuickReelEvent): QuickReelState {
  switch (event.type) {
    case 'SEED':
      return {
        ...initialState,
        seed: event.seed,
        phase: { name: 'hooks' },
      };
    case 'HOOKS_LOADED':
      if (state.phase.name !== 'hooks' || event.hooks.length === 0) return state;
      return { ...state, hooks: event.hooks, hookSource: event.source, focusedHook: 0, error: null };
    case 'FAILED':
      return { ...state, error: event.message };
    case 'FOCUS_HOOK': {
      if (state.phase.name !== 'hooks' || !state.hooks) return state;
      const index = Math.max(0, Math.min(state.hooks.length - 1, event.index));
      return { ...state, focusedHook: index };
    }
    case 'CHOOSE_HOOK': {
      if (state.phase.name !== 'hooks' || !state.hooks) return state;
      const index = event.index ?? state.focusedHook;
      if (index < 0 || index >= state.hooks.length) return state;
      return {
        ...state,
        hookIndex: index,
        focusedHook: index,
        selection: {},
        mode: 'build',
        phase: { name: 'playing', segment: 'hook' },
      };
    }
    case 'SEGMENT_ENDED': {
      if (state.phase.name !== 'playing' || state.phase.segment !== event.segment) return state;
      const moment = MOMENT_AFTER[event.segment];
      if (moment === null) return { ...state, phase: { name: 'drop' }, dropCount: state.dropCount + 1 };
      if (state.mode === 'change' && state.selection[moment] !== undefined) {
        return { ...state, phase: { name: 'playing', segment: SEGMENT_AFTER[moment] } };
      }
      return { ...state, phase: { name: 'choosing', moment } };
    }
    case 'CHOOSE':
      if (state.phase.name !== 'choosing' || state.phase.moment !== event.moment) return state;
      return {
        ...state,
        selection: { ...state.selection, [event.moment]: event.optionId },
        phase: { name: 'playing', segment: SEGMENT_AFTER[event.moment] },
      };
    case 'SURPRISE':
      if (!state.hooks || state.phase.name === 'seed') return state;
      return {
        ...state,
        hookIndex: event.hookIndex,
        focusedHook: event.hookIndex,
        selection: { ...event.selection },
        phase: { name: 'drop' },
        dropCount: state.dropCount + 1,
      };
    case 'DROP_ENDED':
      if (state.phase.name !== 'drop') return state;
      return { ...state, phase: { name: 'ship' }, mode: 'build' };
    case 'REMIX':
      if (state.phase.name !== 'ship') return state;
      return {
        ...state,
        selection: { ...event.selection },
        phase: { name: 'drop' },
        dropCount: state.dropCount + 1,
      };
    case 'CHANGE_ONE':
      if (state.phase.name !== 'ship') return state;
      return { ...state, mode: 'change', phase: { name: 'choosing', moment: event.moment } };
    case 'RESTART':
      return { ...initialState };
  }
}

/** Progress of each story bar (hook, first beat, rest, ending) for the current phase. */
export function completedSegments(phase: Phase): number {
  switch (phase.name) {
    case 'seed':
    case 'hooks':
      return 0;
    case 'playing':
      return SEGMENTS.indexOf(phase.segment);
    case 'choosing':
      return SEGMENTS.indexOf(
        (Object.keys(MOMENT_AFTER) as Segment[]).find((s) => MOMENT_AFTER[s] === phase.moment)!,
      ) + 1;
    case 'drop':
    case 'ship':
      return SEGMENTS.length;
  }
}
