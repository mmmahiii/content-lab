import type { QuickReelApi } from './api';
import { allSelections, cardSelections, fillSelection, selectionKey } from './selection';
import type {
  BranchGenerationResult,
  ComposedReel,
  HookCandidate,
  HookGenerationResult,
  Moment,
  Selection,
} from './types';
import { MOMENTS } from './types';

export interface SessionContext {
  orgId: string;
  pageId: string;
  topic: string;
  assetLabels: string[];
}

/**
 * Pre-fetching for one Quick Reel: hooks, then branches for every hook, then composed
 * timelines for every card the viewer could tap next, so a tap plays instantly.
 *
 * Results are memoised as promises (one request per key) and mirrored into plain maps so
 * the UI can read them synchronously (`peek*`) and re-render on `subscribe`.
 */
export class QuickReelSession {
  private hookResult: Promise<HookGenerationResult> | null = null;
  private branchPromises = new Map<number, Promise<BranchGenerationResult>>();
  private branchValues = new Map<number, BranchGenerationResult>();
  private composePromises = new Map<string, Promise<ComposedReel>>();
  private composeValues = new Map<string, ComposedReel>();
  private listeners = new Set<() => void>();
  private queue: Array<() => void> = [];
  private inFlight = 0;
  private hooksValue: HookCandidate[] | null = null;
  version = 0;

  constructor(
    private readonly api: QuickReelApi,
    readonly context: SessionContext,
    private readonly maxConcurrentCompose = 4,
  ) {}

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  getVersion = (): number => this.version;

  private changed() {
    this.version += 1;
    this.listeners.forEach((listener) => listener());
  }

  hooks(): Promise<HookGenerationResult> {
    this.hookResult ??= this.api
      .hooks(this.context.orgId, this.context.pageId, {
        topic: this.context.topic,
        asset_labels: this.context.assetLabels,
      })
      .then((result) => {
        this.hooksValue = result.hooks;
        // Start every hook's branches right away: whichever one is picked is ready.
        result.hooks.forEach((_, i) => void this.branches(i).catch(() => undefined));
        return result;
      });
    return this.hookResult;
  }

  private hook(index: number): HookCandidate {
    const hook = this.hooksValue?.[index];
    if (!hook) throw new Error(`Hook ${index} is not loaded`);
    return hook;
  }

  branches(index: number): Promise<BranchGenerationResult> {
    let promise = this.branchPromises.get(index);
    if (!promise) {
      promise = this.api
        .branches(this.context.orgId, this.context.pageId, {
          hook: this.hook(index),
          topic: this.context.topic,
          asset_labels: this.context.assetLabels,
        })
        .then((result) => {
          this.branchValues.set(index, result);
          // The API already composed the default selection: seed the cache with it.
          const key = selectionKey(index, result.default_selection);
          this.composeValues.set(key, result.preview);
          this.composePromises.set(key, Promise.resolve(result.preview));
          this.changed();
          // The hook and the structure cards are the first things shown after a pick.
          void this.compose(index, this.defaults(index)!).catch(() => undefined);
          void this.prefetchMoment(index, 'structure', {});
          return result;
        });
      promise.catch(() => this.branchPromises.delete(index));
      this.branchPromises.set(index, promise);
    }
    return promise;
  }

  peekBranches(index: number): BranchGenerationResult | undefined {
    return this.branchValues.get(index);
  }

  private schedule<T>(task: () => Promise<T>): Promise<T> {
    return new Promise<T>((resolve, reject) => {
      const run = () => {
        this.inFlight += 1;
        task()
          .then(resolve, reject)
          .finally(() => {
            this.inFlight -= 1;
            this.queue.shift()?.();
          });
      };
      if (this.inFlight < this.maxConcurrentCompose) run();
      else this.queue.push(run);
    });
  }

  compose(index: number, selection: Selection): Promise<ComposedReel> {
    const key = selectionKey(index, selection);
    let promise = this.composePromises.get(key);
    if (!promise) {
      promise = this.branches(index).then((result) =>
        this.schedule(() =>
          this.api.compose(this.context.orgId, this.context.pageId, {
            hook: result.hook,
            branches: result.branches,
            selection,
          }),
        ),
      );
      promise.then(
        (composed) => {
          this.composeValues.set(key, composed);
          this.changed();
        },
        () => this.composePromises.delete(key),
      );
      this.composePromises.set(key, promise);
    }
    return promise;
  }

  peekCompose(index: number, selection: Selection): ComposedReel | undefined {
    return this.composeValues.get(selectionKey(index, selection));
  }

  /** Compose every card shown at `moment` (given the choices so far). */
  async prefetchMoment(index: number, moment: Moment, chosen: Partial<Selection>): Promise<void> {
    const result = await this.branches(index);
    await Promise.allSettled(
      cardSelections(result.branches, moment, chosen, this.defaults(index)!).map((selection) =>
        this.compose(index, selection),
      ),
    );
  }

  /** Compose the next moments' cards first, then every remaining combination (for Remix). */
  async prefetchAll(index: number, chosen: Partial<Selection>): Promise<void> {
    const result = await this.branches(index);
    const upcoming = MOMENTS.filter((m) => chosen[m] === undefined);
    for (const moment of upcoming) void this.prefetchMoment(index, moment, chosen);
    await Promise.allSettled(allSelections(result.branches).map((s) => this.compose(index, s)));
  }

  /**
   * Defaults for unchosen moments: the API's default selection, except energy starts on the
   * punchy option when there is one, because the hook reel previews hooks in punchy and the
   * chosen hook should keep the look the viewer stopped on.
   */
  defaults(index: number): Selection | undefined {
    const result = this.branchValues.get(index);
    if (!result) return undefined;
    const punchy = result.branches.energy.find((option) => option.pace === 'punchy');
    return { ...result.default_selection, energy: punchy?.option_id ?? result.default_selection.energy };
  }

  /** The composed reel the main player should show for the choices so far, if ready. */
  activeReel(index: number, chosen: Partial<Selection>): ComposedReel | undefined {
    const defaults = this.defaults(index);
    return defaults ? this.peekCompose(index, fillSelection(chosen, defaults)) : undefined;
  }
}
