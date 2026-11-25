import type { Phase } from './machine';

export type KeyAction =
  | { type: 'nextHook' }
  | { type: 'prevHook' }
  | { type: 'chooseHook' }
  | { type: 'chooseCard'; index: number }
  | { type: 'chooseFocusedCard' }
  | { type: 'moveCard'; delta: number }
  | { type: 'surprise' }
  | { type: 'skipDrop' }
  | { type: 'download' }
  | { type: 'copyCaption' }
  | { type: 'remix' };

/** Desktop keyboard map (arrows, 1/2/3, Enter). Returns null for keys we do not handle. */
export function keyAction(phase: Phase, key: string): KeyAction | null {
  switch (phase.name) {
    case 'hooks':
      if (key === 'ArrowDown' || key === 'j') return { type: 'nextHook' };
      if (key === 'ArrowUp' || key === 'k') return { type: 'prevHook' };
      if (key === 'Enter' || key === ' ') return { type: 'chooseHook' };
      if (key === 's') return { type: 'surprise' };
      return null;
    case 'choosing':
      if (['1', '2', '3'].includes(key)) return { type: 'chooseCard', index: Number(key) - 1 };
      if (key === 'Enter' || key === ' ') return { type: 'chooseFocusedCard' };
      if (key === 'ArrowLeft' || key === 'ArrowUp') return { type: 'moveCard', delta: -1 };
      if (key === 'ArrowRight' || key === 'ArrowDown') return { type: 'moveCard', delta: 1 };
      if (key === 's') return { type: 'surprise' };
      return null;
    case 'drop':
      if (key === 'Escape' || key === 'Enter') return { type: 'skipDrop' };
      return null;
    case 'ship':
      if (key === 'd') return { type: 'download' };
      if (key === 'c') return { type: 'copyCaption' };
      if (key === 'r') return { type: 'remix' };
      return null;
    default:
      return null;
  }
}

/** Ignore shortcuts while the user is typing. */
export function isTypingTarget(target: EventTarget | null): boolean {
  if (!target || typeof (target as HTMLElement).tagName !== 'string') return false;
  const el = target as HTMLElement;
  return el.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName);
}
