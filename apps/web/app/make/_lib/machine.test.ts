import { describe, expect, it } from 'vitest';

import { hooks } from './fixtures.test-data';
import { completedSegments, initialState, reducer, type QuickReelEvent, type QuickReelState } from './machine';

const seed: QuickReelEvent = {
  type: 'SEED',
  seed: { orgId: 'o', pageId: 'p', topic: 'crispy potatoes', surprise: false },
};
const run = (events: QuickReelEvent[], from: QuickReelState = initialState) => events.reduce(reducer, from);
const loaded = run([seed, { type: 'HOOKS_LOADED', hooks, source: 'fallback' }]);

describe('Quick Reel flow', () => {
  it('goes seed → hooks → hook → structure → beat → energy → rest → ending → drop → ship', () => {
    const phases: string[] = [];
    const events: QuickReelEvent[] = [
      { type: 'FOCUS_HOOK', index: 1 },
      { type: 'CHOOSE_HOOK' },
      { type: 'SEGMENT_ENDED', segment: 'hook' },
      { type: 'CHOOSE', moment: 'structure', optionId: 'mistake_fix' },
      { type: 'SEGMENT_ENDED', segment: 'firstBeat' },
      { type: 'CHOOSE', moment: 'energy', optionId: 'dramatic' },
      { type: 'SEGMENT_ENDED', segment: 'restBeats' },
      { type: 'CHOOSE', moment: 'ending', optionId: 'reveal' },
      { type: 'SEGMENT_ENDED', segment: 'ending' },
      { type: 'DROP_ENDED' },
    ];
    let state = loaded;
    for (const event of events) {
      state = reducer(state, event);
      const p = state.phase;
      phases.push(p.name === 'playing' ? `play:${p.segment}` : p.name === 'choosing' ? `choose:${p.moment}` : p.name);
    }
    expect(phases).toEqual([
      'hooks',
      'play:hook',
      'choose:structure',
      'play:firstBeat',
      'choose:energy',
      'play:restBeats',
      'choose:ending',
      'play:ending',
      'drop',
      'ship',
    ]);
    expect(state.hookIndex).toBe(1);
    expect(state.selection).toEqual({ structure: 'mistake_fix', energy: 'dramatic', ending: 'reveal' });
    expect(state.dropCount).toBe(1);
  });

  it('clamps hook focus and ignores events from the wrong step', () => {
    expect(reducer(loaded, { type: 'FOCUS_HOOK', index: 9 }).focusedHook).toBe(2);
    expect(reducer(loaded, { type: 'FOCUS_HOOK', index: -3 }).focusedHook).toBe(0);
    expect(reducer(loaded, { type: 'CHOOSE', moment: 'energy', optionId: 'x' })).toBe(loaded);
    const playing = reducer(loaded, { type: 'CHOOSE_HOOK' });
    // A stale "segment ended" for another segment changes nothing.
    expect(reducer(playing, { type: 'SEGMENT_ENDED', segment: 'restBeats' })).toBe(playing);
    // Cannot choose a hook before any exist.
    expect(reducer(run([seed]), { type: 'CHOOSE_HOOK' }).phase.name).toBe('hooks');
  });

  it('Surprise me jumps straight to the drop with a full selection', () => {
    const state = reducer(loaded, {
      type: 'SURPRISE',
      hookIndex: 2,
      selection: { structure: 'secret_reveal', energy: 'punchy', ending: 'save_it' },
    });
    expect(state.phase.name).toBe('drop');
    expect(state.hookIndex).toBe(2);
    expect(state.selection.ending).toBe('save_it');
  });

  it('Remix keeps the hook, swaps the choices and replays the drop', () => {
    const ship = run([
      { type: 'SURPRISE', hookIndex: 0, selection: { structure: 'breakdown', energy: 'chill', ending: 'reveal' } },
      { type: 'DROP_ENDED' },
    ], loaded);
    const remixed = reducer(ship, { type: 'REMIX', selection: { structure: 'mistake_fix', energy: 'punchy', ending: 'part_two' } });
    expect(remixed.phase.name).toBe('drop');
    expect(remixed.hookIndex).toBe(0);
    expect(remixed.dropCount).toBe(ship.dropCount + 1);
  });

  it('Change one thing reopens one choice, then plays through to the drop without pausing', () => {
    const ship = run([
      { type: 'SURPRISE', hookIndex: 0, selection: { structure: 'breakdown', energy: 'chill', ending: 'reveal' } },
      { type: 'DROP_ENDED' },
    ], loaded);
    let state = reducer(ship, { type: 'CHANGE_ONE', moment: 'energy' });
    expect(state.phase).toEqual({ name: 'choosing', moment: 'energy' });
    state = reducer(state, { type: 'CHOOSE', moment: 'energy', optionId: 'dramatic' });
    expect(state.phase).toEqual({ name: 'playing', segment: 'restBeats' });
    state = reducer(state, { type: 'SEGMENT_ENDED', segment: 'restBeats' });
    expect(state.phase).toEqual({ name: 'playing', segment: 'ending' });
    state = reducer(state, { type: 'SEGMENT_ENDED', segment: 'ending' });
    expect(state.phase.name).toBe('drop');
    expect(state.selection).toEqual({ structure: 'breakdown', energy: 'dramatic', ending: 'reveal' });
    expect(reducer(state, { type: 'DROP_ENDED' }).mode).toBe('build');
  });

  it('records failures and restarts cleanly', () => {
    const failed = reducer(run([seed]), { type: 'FAILED', message: 'API down' });
    expect(failed.error).toBe('API down');
    expect(reducer(failed, { type: 'RESTART' })).toEqual(initialState);
  });

  it('counts finished story bars per step', () => {
    expect(completedSegments({ name: 'hooks' })).toBe(0);
    expect(completedSegments({ name: 'playing', segment: 'hook' })).toBe(0);
    expect(completedSegments({ name: 'choosing', moment: 'structure' })).toBe(1);
    expect(completedSegments({ name: 'playing', segment: 'restBeats' })).toBe(2);
    expect(completedSegments({ name: 'choosing', moment: 'ending' })).toBe(3);
    expect(completedSegments({ name: 'ship' })).toBe(4);
  });
});
