import type { BranchSet, ChoiceOption, Moment, Selection } from './types';
import { MOMENTS } from './types';

export type PartialSelection = Partial<Selection>;

export function optionsFor(branches: BranchSet, moment: Moment): ChoiceOption[] {
  return branches[moment];
}

export function optionLabel(branches: BranchSet, moment: Moment, optionId: string): string {
  return optionsFor(branches, moment).find((o) => o.option_id === optionId)?.label ?? optionId;
}

/** Fill unchosen moments from the defaults (the API's `default_selection`). */
export function fillSelection(partial: PartialSelection, defaults: Selection): Selection {
  return {
    structure: partial.structure ?? defaults.structure,
    energy: partial.energy ?? defaults.energy,
    ending: partial.ending ?? defaults.ending,
  };
}

export function selectionKey(hookIndex: number, selection: Selection): string {
  return `${hookIndex}|${selection.structure}|${selection.energy}|${selection.ending}`;
}

export function sameSelection(a: Selection, b: Selection): boolean {
  return MOMENTS.every((m) => a[m] === b[m]);
}

export type Random = () => number;

const pick = <T>(items: readonly T[], random: Random): T =>
  items[Math.min(items.length - 1, Math.floor(random() * items.length))];

/**
 * Random choices, keeping any moments already chosen. Used by "Surprise me" (skip the
 * remaining choices) and Remix (`avoid` = current selection: guarantees a different reel).
 */
export function randomSelection(
  branches: BranchSet,
  random: Random,
  opts: { keep?: PartialSelection; avoid?: Selection } = {},
): Selection {
  const keep = opts.keep ?? {};
  const roll = (): Selection => ({
    structure: keep.structure ?? pick(branches.structure, random).option_id,
    energy: keep.energy ?? pick(branches.energy, random).option_id,
    ending: keep.ending ?? pick(branches.ending, random).option_id,
  });
  let next = roll();
  for (let attempt = 0; opts.avoid && sameSelection(next, opts.avoid) && attempt < 12; attempt++) {
    next = roll();
  }
  if (opts.avoid && sameSelection(next, opts.avoid)) {
    // Deterministic fallback: move the first free moment to its next option.
    const moment = MOMENTS.find((m) => keep[m] === undefined && branches[m].length > 1);
    if (moment) {
      const ids = branches[moment].map((o) => o.option_id);
      next = { ...next, [moment]: ids[(ids.indexOf(next[moment]) + 1) % ids.length] };
    }
  }
  return next;
}

/** Every full selection for a branch set (3 x 3 x 3 = 27 at most). */
export function allSelections(branches: BranchSet): Selection[] {
  const out: Selection[] = [];
  for (const s of branches.structure)
    for (const e of branches.energy)
      for (const end of branches.ending)
        out.push({ structure: s.option_id, energy: e.option_id, ending: end.option_id });
  return out;
}

/** The selection each card at a choice moment previews (other moments: chosen or default). */
export function cardSelections(
  branches: BranchSet,
  moment: Moment,
  chosen: PartialSelection,
  defaults: Selection,
): Selection[] {
  const base = fillSelection(chosen, defaults);
  return optionsFor(branches, moment).map((option) => ({ ...base, [moment]: option.option_id }));
}
