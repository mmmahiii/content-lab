import { describe, expect, it } from 'vitest';

import { isTypingTarget, keyAction } from './keyboard';

describe('keyboard map', () => {
  it('uses arrows and Enter in the hook reel', () => {
    expect(keyAction({ name: 'hooks' }, 'ArrowDown')).toEqual({ type: 'nextHook' });
    expect(keyAction({ name: 'hooks' }, 'ArrowUp')).toEqual({ type: 'prevHook' });
    expect(keyAction({ name: 'hooks' }, 'Enter')).toEqual({ type: 'chooseHook' });
  });

  it('uses 1/2/3 and Enter at a cliffhanger', () => {
    const phase = { name: 'choosing', moment: 'energy' } as const;
    expect(keyAction(phase, '2')).toEqual({ type: 'chooseCard', index: 1 });
    expect(keyAction(phase, 'Enter')).toEqual({ type: 'chooseFocusedCard' });
    expect(keyAction(phase, 'ArrowRight')).toEqual({ type: 'moveCard', delta: 1 });
    expect(keyAction(phase, '4')).toBeNull();
  });

  it('does nothing while a segment plays or the user is typing', () => {
    expect(keyAction({ name: 'playing', segment: 'hook' }, 'Enter')).toBeNull();
    expect(keyAction({ name: 'seed' }, 'ArrowDown')).toBeNull();
    expect(isTypingTarget({ tagName: 'INPUT', isContentEditable: false } as unknown as EventTarget)).toBe(true);
    expect(isTypingTarget({ tagName: 'DIV', isContentEditable: false } as unknown as EventTarget)).toBe(false);
    expect(isTypingTarget(null)).toBe(false);
  });
});
