import { Kbd } from '@/components/ui/kbd';

import type { Phase } from '../_lib/machine';

const HELP: Partial<Record<Phase['name'], Array<[string[], string]>>> = {
  seed: [[['Enter'], 'Make hooks for the topic']],
  hooks: [
    [['↓', '↑'], 'Next / previous hook'],
    [['Enter'], 'Use this hook'],
    [['S'], 'Surprise me'],
  ],
  choosing: [
    [['1', '2', '3'], 'Pick a card'],
    [['←', '→'], 'Move between cards'],
    [['Enter'], 'Pick the highlighted card'],
    [['S'], 'Surprise me'],
  ],
  playing: [[[], 'Watch: the next choice comes when this beat ends']],
  drop: [[['Esc'], 'Skip to the finish']],
  ship: [
    [['D'], 'Download MP4'],
    [['C'], 'Copy caption'],
    [['R'], 'Remix'],
  ],
};

/** Desktop side panel: the keys for the current step. */
export function KeyboardHelp({ phase }: { phase: Phase }) {
  const rows = HELP[phase.name] ?? [];
  return (
    <div className="space-y-4" data-testid="keyboard-help">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-fg-subtle">Keyboard</p>
      <ul className="space-y-3">
        {rows.map(([keys, label]) => (
          <li key={label} className="flex items-center gap-3 text-sm text-fg-muted">
            <span className="flex min-w-16 gap-1">
              {keys.map((k) => (
                <Kbd key={k}>{k}</Kbd>
              ))}
            </span>
            {label}
          </li>
        ))}
      </ul>
    </div>
  );
}
