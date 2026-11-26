'use client';

import { X } from 'lucide-react';
import { useCallback, useEffect, useMemo, useReducer, useRef, useState, useSyncExternalStore } from 'react';

import { Button } from '@/components/ui/button';
import { PhoneFrame } from '@/components/ui/phone-frame';
import { useToast } from '@/components/ui/toast';

import { createApi, type QuickReelApi } from '../_lib/api';
import { buildCaption } from '../_lib/caption';
import { isTypingTarget, keyAction } from '../_lib/keyboard';
import { initialState, reducer, type Segment } from '../_lib/machine';
import { cardSelections, fillSelection, optionLabel, randomSelection } from '../_lib/selection';
import { QuickReelSession } from '../_lib/session';
import { cardTimeline, reelTimeline } from '../_lib/timelines';
import { MOMENTS, type Moment, type Org, type Page, type Selection } from '../_lib/types';
import { NO_VISUALS, packsForPage, pageVisuals, type PageVisuals } from '../_lib/visuals';
import { BuildStage } from './BuildStage';
import type { ChoiceCard } from './ChoiceSheet';
import { DropScreen } from './DropScreen';
import { HookReel } from './HookReel';
import { KeyboardHelp } from './KeyboardHelp';
import { SeedScreen } from './SeedScreen';
import { ShipScreen, type ReviewState } from './ShipScreen';
import { useRender } from './useRender';

const noopSubscribe = () => () => {};
const zero = () => 0;

function useWorkspace(api: QuickReelApi) {
  const [orgs, setOrgs] = useState<Org[]>([]);
  const [orgId, setOrgId] = useState<string | null>(null);
  const [pages, setPages] = useState<Page[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let live = true;
    setError(null);
    api
      .listOrgs()
      .then((list) => {
        if (!live) return;
        setOrgs(list);
        setOrgId((current) => current ?? list[0]?.id ?? null);
        if (list.length === 0) setError('No orgs found. Seed an org in the database first.');
      })
      .catch((e: Error) => live && setError(e.message));
    return () => {
      live = false;
    };
  }, [api, attempt]);

  useEffect(() => {
    if (!orgId) return;
    let live = true;
    setPages(null);
    api
      .listPages(orgId)
      .then((list) => live && setPages(list))
      .catch((e: Error) => live && setError(e.message));
    return () => {
      live = false;
    };
  }, [api, orgId, attempt]);

  return { orgs, orgId, setOrgId, pages, error, retry: () => setAttempt((n) => n + 1) };
}

/** The page's asset-pack images (niche match), or none: the gradient backdrop. */
function usePageVisuals(api: QuickReelApi, orgId: string | null, page: Page | null): PageVisuals {
  const [visuals, setVisuals] = useState<PageVisuals>(NO_VISUALS);
  useEffect(() => {
    setVisuals(NO_VISUALS);
    if (!orgId || !page) return;
    let live = true;
    (async () => {
      const packs = packsForPage(page, await api.listAssetPacks(orgId));
      for (const pack of packs) {
        const found = pageVisuals(orgId, pack, await api.listPackAssets(orgId, pack.id));
        if (found.visuals.length > 0) return found;
      }
      return NO_VISUALS;
    })()
      .then((found) => live && setVisuals(found))
      .catch(() => live && setVisuals(NO_VISUALS));
    return () => {
      live = false;
    };
  }, [api, orgId, page]);
  return visuals;
}

export default function QuickReelApp() {
  const api = useMemo(() => createApi(), []);
  const notify = useToast();
  const workspace = useWorkspace(api);
  const [pageId, setPageId] = useState<string | null>(null);
  const page = workspace.pages?.find((p) => p.id === pageId) ?? null;
  const pageVisualsState = usePageVisuals(api, workspace.orgId, page);
  const [state, dispatch] = useReducer(reducer, initialState);
  const [session, setSession] = useState<QuickReelSession | null>(null);
  const [focusedCard, setFocusedCard] = useState(0);
  const [review, setReview] = useState<ReviewState>({ status: 'idle' });
  const render = useRender(api);
  const reviewRequestId = useRef<string | null>(null);
  useSyncExternalStore(session?.subscribe ?? noopSubscribe, session?.getVersion ?? zero, zero);

  // Pick the first page once pages load (one tap fewer); keep the user's choice after.
  useEffect(() => {
    if (workspace.pages && !workspace.pages.some((p) => p.id === pageId)) {
      setPageId(workspace.pages[0]?.id ?? null);
    }
  }, [workspace.pages, pageId]);

  const visuals = pageVisualsState.visuals;
  const hookIndex = state.hookIndex;
  const branches = hookIndex !== null ? session?.peekBranches(hookIndex) : undefined;
  const defaults = branches?.default_selection;
  const fullSelection: Selection | undefined = defaults ? fillSelection(state.selection, defaults) : undefined;
  const composed = hookIndex !== null ? session?.activeReel(hookIndex, state.selection) : undefined;
  // Voice + music per reel (keyed by hook + choices); undefined = not fetched yet, null = none.
  const [soundtracks, setSoundtracks] = useState<Record<string, string | null>>({});
  const soundtrackKey =
    hookIndex !== null && fullSelection ? `${hookIndex}:${JSON.stringify(fullSelection)}` : null;
  const soundtrackSrc = soundtrackKey ? soundtracks[soundtrackKey] : undefined;
  const finalTimeline = useMemo(() => {
    if (!composed) return null;
    const timeline = reelTimeline(composed, visuals);
    return soundtrackSrc ? { ...timeline, audio: { src: soundtrackSrc } } : timeline;
  }, [composed, visuals, soundtrackSrc]);

  const fail = useCallback((e: unknown) => {
    dispatch({ type: 'FAILED', message: e instanceof Error ? e.message : String(e) });
  }, []);

  const surprise = useCallback(
    async (s: QuickReelSession, index: number, keep: Partial<Selection>) => {
      const result = await s.branches(index);
      const selection = randomSelection(result.branches, Math.random, { keep });
      await s.compose(index, selection);
      dispatch({ type: 'SURPRISE', hookIndex: index, selection });
    },
    [],
  );

  const start = useCallback(
    (topic: string, isSurprise: boolean) => {
      if (!workspace.orgId || !page) return;
      const s = new QuickReelSession(api, {
        orgId: workspace.orgId,
        pageId: page.id,
        topic,
        assetLabels: pageVisualsState.labels,
      });
      setSession(s);
      setReview({ status: 'idle' });
      render.reset();
      dispatch({
        type: 'SEED',
        seed: { orgId: workspace.orgId, pageId: page.id, topic, surprise: isSurprise },
      });
      s.hooks()
        .then(async (result) => {
          dispatch({ type: 'HOOKS_LOADED', hooks: result.hooks, source: result.source });
          if (isSurprise) {
            await surprise(s, Math.floor(Math.random() * result.hooks.length), {});
          }
        })
        .catch(fail);
    },
    [api, workspace.orgId, page, pageVisualsState.labels, render, surprise, fail],
  );

  // Once a hook is chosen, compose every combination in the background (no LLM, cheap).
  useEffect(() => {
    if (session && hookIndex !== null) void session.prefetchAll(hookIndex, {}).catch(() => undefined);
  }, [session, hookIndex]);

  // The reel is final at the drop: fetch its soundtrack (voice + music), then render the MP4
  // with it, so Download is ready by Ship. A failed soundtrack renders silent, with a notice.
  // Keyed by the string soundtrackKey only: branches/selection objects change identity on
  // every render, and depending on them re-ran (and cancelled) the request in a loop.
  const soundtrackInputs = useRef({ seed: state.seed, branches, fullSelection });
  soundtrackInputs.current = { seed: state.seed, branches, fullSelection };
  const soundtrackRequested = useRef(new Set<string>());
  useEffect(() => {
    if (state.phase.name !== 'drop' || !soundtrackKey || soundtrackSrc !== undefined) return;
    if (soundtrackRequested.current.has(soundtrackKey)) return;
    const { seed, branches: currentBranches, fullSelection: selection } = soundtrackInputs.current;
    if (!seed || !currentBranches || !selection) return;
    soundtrackRequested.current.add(soundtrackKey);
    api
      .soundtrack(seed.orgId, seed.pageId, {
        hook: currentBranches.hook,
        branches: currentBranches.branches,
        selection,
      })
      .then((result) => setSoundtracks((prev) => ({ ...prev, [soundtrackKey]: result.src })))
      .catch((e) => {
        notify(`No soundtrack: ${e instanceof Error ? e.message : String(e)}`, 'danger');
        setSoundtracks((prev) => ({ ...prev, [soundtrackKey]: null }));
      });
  }, [api, state.phase.name, soundtrackKey, soundtrackSrc, notify]);

  const { start: startRender } = render;
  useEffect(() => {
    if (state.phase.name === 'drop' && finalTimeline && soundtrackSrc !== undefined) {
      void startRender(finalTimeline);
    }
  }, [state.phase.name, state.dropCount, finalTimeline, soundtrackSrc, startRender]);

  useEffect(() => {
    setFocusedCard(0);
  }, [state.phase]);

  // A new reel (remix / change) needs its own review send.
  useEffect(() => {
    setReview({ status: 'idle' });
    reviewRequestId.current = null;
  }, [state.dropCount]);

  const choose = useCallback(
    (moment: Moment, optionId: string) => {
      if (!session || hookIndex === null || !defaults) return;
      const next = fillSelection({ ...state.selection, [moment]: optionId }, defaults);
      // Normally already composed (pre-fetched); if not, playback holds until it is.
      session
        .compose(hookIndex, next)
        .then(() => dispatch({ type: 'CHOOSE', moment, optionId }))
        .catch(fail);
    },
    [session, hookIndex, defaults, state.selection, fail],
  );

  const cards: ChoiceCard[] = useMemo(() => {
    if (state.phase.name !== 'choosing' || !session || hookIndex === null || !branches || !defaults) return [];
    const moment = state.phase.moment;
    const chosen = state.mode === 'change' ? {} : state.selection;
    const base = state.mode === 'change' ? fillSelection(state.selection, defaults) : defaults;
    return cardSelections(branches.branches, moment, chosen, base).map((selection, i) => {
      const reel = session.peekCompose(hookIndex, selection);
      return {
        option: branches.branches[moment][i],
        timeline: reel ? cardTimeline(reel, moment, visuals) : undefined,
      };
    });
    // session.version changes re-render this component; include it so previews appear.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.phase, state.mode, state.selection, session, session?.version, hookIndex, branches, defaults, visuals]);

  const caption = useMemo(() => {
    if (!composed || hookIndex === null || !state.hooks) return '';
    return buildCaption({ hook: state.hooks[hookIndex], composed, page, topic: state.seed?.topic ?? '' });
  }, [composed, hookIndex, state.hooks, page, state.seed?.topic]);

  const copyCaption = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(caption);
      notify('Caption copied', 'success');
    } catch {
      notify('Could not copy: select the caption text instead', 'danger');
    }
  }, [caption, notify]);

  const sendToReview = useCallback(async () => {
    if (!session || hookIndex === null || !branches || !fullSelection || !state.seed) return;
    reviewRequestId.current ??= crypto.randomUUID();
    setReview({ status: 'sending' });
    const job = render.job;
    try {
      const reel = await api.sendToReview(state.seed.orgId, state.seed.pageId, {
        hook: branches.hook,
        branches: branches.branches,
        selection: fullSelection,
        topic: state.seed.topic,
        caption,
        visuals: pageVisualsState.assets,
        generation_source: branches.source,
        client_request_id: reviewRequestId.current,
        render:
          job?.status === 'done' && job.overlayTraceStatus
            ? {
                render_id: job.renderId,
                duration_seconds: job.durationSeconds,
                width: job.width,
                height: job.height,
                fps: job.fps,
                overlay_trace_status: job.overlayTraceStatus,
              }
            : null,
      });
      setReview({ status: 'sent', reelId: reel.id });
      notify('Sent to review', 'success');
    } catch (e) {
      setReview({ status: 'failed', message: e instanceof Error ? e.message : String(e) });
    }
  }, [api, session, hookIndex, branches, fullSelection, state.seed, caption, pageVisualsState.assets, render.job, notify]);

  const remix = useCallback(async () => {
    if (!session || hookIndex === null || !branches || !fullSelection) return;
    const selection = randomSelection(branches.branches, Math.random, { avoid: fullSelection });
    try {
      await session.compose(hookIndex, selection);
      dispatch({ type: 'REMIX', selection });
    } catch (e) {
      notify(e instanceof Error ? e.message : String(e), 'danger');
    }
  }, [session, hookIndex, branches, fullSelection, notify]);

  const surpriseNow = useCallback(() => {
    if (!session || !state.hooks) return;
    const index = hookIndex ?? state.focusedHook;
    const keep = state.phase.name === 'choosing' && state.mode === 'build' ? state.selection : {};
    surprise(session, index, keep).catch(fail);
  }, [session, state.hooks, hookIndex, state.focusedHook, state.phase.name, state.mode, state.selection, surprise, fail]);

  const downloadLink = useRef<() => void>(() => {});
  downloadLink.current = () => {
    const job = render.job;
    if (job?.status === 'done' && job.videoUrl) window.location.assign(`${job.videoUrl}?download=1`);
  };

  // Desktop keyboard: arrows, 1/2/3, Enter (and a few ship shortcuts).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey || isTypingTarget(e.target)) return;
      const action = keyAction(state.phase, e.key);
      if (!action) return;
      e.preventDefault();
      switch (action.type) {
        case 'nextHook':
          return dispatch({ type: 'FOCUS_HOOK', index: state.focusedHook + 1 });
        case 'prevHook':
          return dispatch({ type: 'FOCUS_HOOK', index: state.focusedHook - 1 });
        case 'chooseHook':
          return dispatch({ type: 'CHOOSE_HOOK' });
        case 'chooseCard':
        case 'chooseFocusedCard': {
          if (state.phase.name !== 'choosing') return;
          const index = action.type === 'chooseCard' ? action.index : focusedCard;
          const card = cards[index];
          if (card) choose(state.phase.moment, card.option.option_id);
          return;
        }
        case 'moveCard':
          return setFocusedCard((i) => (cards.length ? (i + action.delta + cards.length) % cards.length : 0));
        case 'surprise':
          return surpriseNow();
        case 'skipDrop':
          return dispatch({ type: 'DROP_ENDED' });
        case 'download':
          return downloadLink.current();
        case 'copyCaption':
          return void copyCaption();
        case 'remix':
          return void remix();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [state.phase, state.focusedHook, focusedCard, cards, choose, surpriseNow, copyCaption, remix]);

  const restart = () => {
    render.reset();
    setSession(null);
    dispatch({ type: 'RESTART' });
  };

  const phase = state.phase;
  const hook = hookIndex !== null ? state.hooks?.[hookIndex] : undefined;
  const choiceLabels = Object.fromEntries(
    MOMENTS.map((m) => [m, branches && fullSelection ? optionLabel(branches.branches, m, fullSelection[m]) : '']),
  ) as Record<Moment, string>;

  let screen: React.ReactNode = null;
  if (phase.name === 'seed') {
    screen = (
      <SeedScreen
        orgs={workspace.orgs}
        orgId={workspace.orgId}
        onOrg={workspace.setOrgId}
        pages={workspace.pages}
        pageId={pageId}
        onPage={setPageId}
        visuals={visuals}
        packName={pageVisualsState.packName}
        loadError={workspace.error}
        onRetry={workspace.retry}
        onStart={start}
      />
    );
  } else if (phase.name === 'hooks') {
    screen = (
      <HookReel
        topic={state.seed?.topic ?? ''}
        hooks={state.hooks}
        focused={state.focusedHook}
        visuals={visuals}
        source={state.hookSource}
        surprising={Boolean(state.seed?.surprise) && !state.error}
        error={state.error}
        onFocus={(index) => dispatch({ type: 'FOCUS_HOOK', index })}
        onChoose={(index) => dispatch({ type: 'CHOOSE_HOOK', index })}
        onSurprise={surpriseNow}
        onRetry={() => state.seed && start(state.seed.topic, state.seed.surprise)}
      />
    );
  } else if ((phase.name === 'playing' || phase.name === 'choosing') && hook) {
    screen = (
      <BuildStage
        phase={phase}
        composed={composed}
        hook={hook}
        visuals={visuals}
        onSegmentEnded={(segment: Segment) => dispatch({ type: 'SEGMENT_ENDED', segment })}
        choice={
          phase.name === 'choosing'
            ? {
                cards,
                focused: focusedCard,
                current: state.mode === 'change' ? fullSelection?.[phase.moment] : undefined,
                onChoose: (optionId) => choose(phase.moment, optionId),
                onFocus: setFocusedCard,
                onSurprise: surpriseNow,
              }
            : null
        }
      />
    );
  } else if (phase.name === 'drop' && finalTimeline) {
    screen = (
      <DropScreen timeline={finalTimeline} dropCount={state.dropCount} onEnded={() => dispatch({ type: 'DROP_ENDED' })} />
    );
  } else if (phase.name === 'ship' && finalTimeline) {
    screen = (
      <ShipScreen
        timeline={finalTimeline}
        caption={caption}
        pageName={page?.display_name ?? 'the page'}
        render={render.job}
        renderError={render.error}
        review={review}
        choiceLabels={choiceLabels}
        onDownload={() => notify('Downloading MP4', 'neutral')}
        onRetryRender={() => void render.start(finalTimeline)}
        onCopyCaption={() => void copyCaption()}
        onSendToReview={() => void sendToReview()}
        onRemix={() => void remix()}
        onChangeOne={(moment) => dispatch({ type: 'CHANGE_ONE', moment })}
        onRestart={restart}
      />
    );
  }

  return (
    <PhoneFrame aside={<KeyboardHelp phase={phase} />}>
      {screen}
      {phase.name !== 'seed' && phase.name !== 'drop' ? (
        <Button
          variant="glass"
          size="icon"
          className="absolute left-3 top-[max(1.5rem,calc(env(safe-area-inset-top)+0.75rem))] z-30 h-9 w-9"
          aria-label="Exit to start"
          onClick={restart}
        >
          <X className="h-4 w-4" />
        </Button>
      ) : null}
    </PhoneFrame>
  );
}
