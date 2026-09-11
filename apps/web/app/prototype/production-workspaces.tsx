'use client';

import { useEffect, useRef, useState } from 'react';
import Image from 'next/image';
import { zonedLocalToIso } from './publication-time';
import { buildPrototypeHandoff } from './prototype-handoff';
import {
  canEdit,
  canReview,
  money,
  representationFor,
  type Composition,
  type ContentItem,
  type PackageRecord,
  type WorkspaceProps,
  type Command,
} from './domain';
import { Badge, DownloadButton, EmptyState, Icon, StatusBadge } from './ui';
import { CompositionPreview, SceneEditor } from './scene-editor';

const tabs = [
  ['brief', 'Brief'],
  ['story', 'Hook & blueprint'],
  ['assets', 'Ingredients'],
  ['edit', 'Scene editor'],
  ['run', 'Execution'],
  ['review', 'Review'],
  ['publish', 'Publication'],
];
function useDraft(content: ContentItem, execute: WorkspaceProps['execute']) {
  const [draft, setDraft] = useState(content.draft);
  const dirty = useRef(false);
  const sequence = useRef(0);
  useEffect(() => {
    if (!dirty.current) setDraft(content.draft);
  }, [content.draft]);
  useEffect(() => {
    dirty.current = false;
    setDraft(content.draft);
  }, [content.id]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!dirty.current) return;
    const generation = sequence.current;
    const timeout = window.setTimeout(() => {
      void execute({ type: 'updateDraft', contentId: content.id, draft }).then((result) => {
        if (result.ok && sequence.current === generation) dirty.current = false;
      });
    }, 350);
    return () => window.clearTimeout(timeout);
  }, [draft, content.id, execute]);
  useEffect(() => {
    // Hash navigation is also used by sidebar anchors. Flush before the workspace unmounts.
    const flushOnNavigation = () => {
      if (dirty.current) void execute({ type: 'updateDraft', contentId: content.id, draft });
    };
    window.addEventListener('hashchange', flushOnNavigation);
    return () => window.removeEventListener('hashchange', flushOnNavigation);
  }, [content.id, draft, execute]);
  return {
    draft,
    update: (next: Composition) => {
      dirty.current = true;
      sequence.current++;
      setDraft(next);
    },
    flush: async () => {
      if (!dirty.current) return true;
      const generation = sequence.current;
      const result = await execute({ type: 'updateDraft', contentId: content.id, draft });
      if (result.ok && generation === sequence.current) dirty.current = false;
      return result.ok;
    },
  };
}
export function ContentWorkspace(
  props: WorkspaceProps & { content: ContentItem; tab: string; detail?: string },
) {
  const { state, content, execute, navigate, tab, detail } = props;
  const { draft, update, flush } = useDraft(content, execute);
  const [busy, setBusy] = useState(false);
  const page = state.pages.find((p) => p.id === content.pageId);
  const latestRevision = state.revisions.find((r) => r.id === content.currentRevisionId);
  const packageRecords = state.packages.filter(
    (p) => p.contentId === content.id && (tab !== 'review' || !detail || p.id === detail),
  );
  const [focus, setFocus] = useState<{ sceneId?: string; instanceId?: string }>({});
  useEffect(() => {
    if (tab === 'edit' && detail) {
      const [sceneId, instanceId] = detail.split('|');
      setFocus({ sceneId, instanceId: instanceId || undefined });
    }
  }, [tab, detail]);
  const perform = async (
    type: 'saveRevision' | 'createPreview' | 'renderRevision' | 'repairPlan' | 'newCandidate',
  ) => {
    setBusy(true);
    if (!(await flush())) {
      setBusy(false);
      return;
    }
    const result = await execute({ type, contentId: content.id });
    setBusy(false);
    if (result.ok && (type === 'renderRevision' || type === 'newCandidate'))
      navigate('content', content.id, 'run');
  };
  return (
    <div className="content-detail">
      <button className="text-button back-link" onClick={() => navigate('content')}>
        <Icon name="back" size={16} />
        Back to content
      </button>
      <header className="detail-heading">
        <div>
          <div className="row">
            <span className="page-tag">
              <i style={{ background: page?.color }} />
              {page?.name}
            </span>
            <StatusBadge status={content.stage} />
            <Badge>{latestRevision ? `Revision ${latestRevision.number}` : 'Working draft'}</Badge>
          </div>
          <h1>{draft.title}</h1>
          <p>
            {content.family === 'product'
              ? 'A layered object story'
              : content.family === 'graphic'
                ? 'A visual explanation'
                : 'A source-video composition'}{' '}
            · {(draft.totalFrames * draft.fps.denominator) / draft.fps.numerator}s ·{' '}
            {draft.canvas.width} × {draft.canvas.height}
          </p>
        </div>
        {tab !== 'edit' && (
          <div className="row">
            <button
              className="button secondary"
              disabled={!canEdit(state.role) || busy}
              onClick={() => void perform('saveRevision')}
            >
              Save revision
            </button>
            <button
              className="button primary"
              disabled={!canEdit(state.role) || busy}
              onClick={() => void perform('createPreview')}
            >
              <Icon name="spark" size={16} />
              Create preview
            </button>
          </div>
        )}
      </header>
      <nav className="detail-tabs" aria-label="Content workflow">
        {tabs.map(([key, label], index) => (
          <button
            key={key}
            className={tab === key ? 'active' : ''}
            onClick={async () => {
              if (await flush()) navigate('content', content.id, key);
            }}
          >
            <span>{String(index + 1).padStart(2, '0')}</span>
            {label}
          </button>
        ))}
      </nav>
      {tab === 'brief' && (
        <div className="detail-two-column">
          <section className="panel editorial-panel">
            <div className="section-heading">
              <div>
                <p className="eyebrow">THE STARTING POINT</p>
                <h2>Give this story a purpose.</h2>
              </div>
              <Badge>Draft autosaves locally</Badge>
            </div>
            <p className="muted">A clear idea makes every later decision easier.</p>
            <fieldset disabled={!canEdit(state.role)} className="form-stack">
              <label className="field">
                Working title
                <input
                  value={draft.title}
                  onChange={(e) => update({ ...draft, title: e.target.value })}
                />
              </label>
              <div className="form-grid">
                <label className="field">
                  Objective
                  <input
                    value={draft.brief.objective}
                    onChange={(e) =>
                      update({ ...draft, brief: { ...draft.brief, objective: e.target.value } })
                    }
                  />
                </label>
                <label className="field">
                  Tone
                  <input
                    value={draft.brief.tone}
                    onChange={(e) =>
                      update({ ...draft, brief: { ...draft.brief, tone: e.target.value } })
                    }
                  />
                </label>
              </div>
              <label className="field">
                What will the audience take away?
                <textarea
                  rows={3}
                  value={draft.brief.audienceValue}
                  onChange={(e) =>
                    update({ ...draft, brief: { ...draft.brief, audienceValue: e.target.value } })
                  }
                />
              </label>
              <div className="form-grid">
                <label className="field">
                  Claims to support
                  <textarea
                    rows={3}
                    value={draft.brief.claims}
                    onChange={(e) =>
                      update({ ...draft, brief: { ...draft.brief, claims: e.target.value } })
                    }
                  />
                </label>
                <label className="field">
                  Evidence and source notes
                  <textarea
                    rows={3}
                    value={draft.brief.evidence}
                    onChange={(e) =>
                      update({ ...draft, brief: { ...draft.brief, evidence: e.target.value } })
                    }
                  />
                </label>
              </div>
              <label className="field">
                The payoff
                <textarea
                  rows={2}
                  value={draft.brief.payoff}
                  onChange={(e) =>
                    update({ ...draft, brief: { ...draft.brief, payoff: e.target.value } })
                  }
                />
              </label>
              <label className="field">
                Production mode
                <select
                  value={draft.mode}
                  onChange={(e) =>
                    update({ ...draft, mode: e.target.value as Composition['mode'] })
                  }
                >
                  <option value="existing_assets">Existing assets · use what is ready</option>
                  <option value="hybrid">Hybrid · acquire only approved gaps</option>
                  <option value="template">Template · a repeatable structure</option>
                </select>
              </label>
              <label className="field">
                Publication copy
                <textarea
                  rows={3}
                  value={draft.caption}
                  onChange={(e) => update({ ...draft, caption: e.target.value })}
                />
              </label>
              <div className="form-grid">
                <label className="field">
                  Disclosures and attribution
                  <textarea
                    rows={2}
                    value={draft.disclosures}
                    onChange={(e) => update({ ...draft, disclosures: e.target.value })}
                  />
                </label>
                <label className="field">
                  Cover frame
                  <input
                    type="number"
                    min={0}
                    max={draft.totalFrames - 1}
                    value={draft.coverFrame}
                    onChange={(e) => update({ ...draft, coverFrame: Number(e.target.value) })}
                  />
                </label>
              </div>
            </fieldset>
            <div className="notice">
              Existing-assets mode never acquires media automatically. Missing capabilities become
              explicit decisions.
            </div>
            <div className="panel-actions">
              <button
                className="button primary"
                onClick={async () => {
                  if (await flush()) navigate('content', content.id, 'story');
                }}
              >
                Shape the story
                <Icon name="arrow" size={16} />
              </button>
            </div>
          </section>
          <aside className="preview-aside">
            <div className="portrait-card">
              <CompositionPreview composition={draft} state={state} />
              <span>Composition preview · editable</span>
            </div>
            <div className="panel compact-panel">
              <h3>Production notes</h3>
              <dl className="key-values">
                <dt>Page</dt>
                <dd>{page?.name}</dd>
                <dt>Format</dt>
                <dd>Vertical reel</dd>
                <dt>Policy</dt>
                <dd>{page?.policyOverride ? 'Page override' : 'Inherited from workspace'}</dd>
                <dt>Budget cap</dt>
                <dd>{money(page?.budgetMinor ?? 0)} · illustrative</dd>
              </dl>
            </div>
          </aside>
        </div>
      )}
      {tab === 'story' && (
        <div className="stack">
          <section className="panel">
            <div className="section-heading">
              <div>
                <p className="eyebrow">FIRST IMPRESSIONS</p>
                <h2>Find the opening that earns a moment.</h2>
              </div>
              <Badge>Hypotheses, not predictions</Badge>
            </div>
            <div className="hook-grid">
              {state.hooks.map((hook) => (
                <button
                  key={hook.id}
                  className={`hook-card ${draft.hookId === hook.id ? 'selected' : ''}`}
                  disabled={!canEdit(state.role)}
                  aria-pressed={draft.hookId === hook.id}
                  onClick={() => {
                    const next = structuredClone(draft);
                    next.hookId = hook.id;
                    const text = next.scenes[0]?.instances.find((i) => i.kind === 'text');
                    if (text) text.text = hook.text;
                    update(next);
                  }}
                >
                  <div className="hook-art" style={{ background: hook.color }}>
                    <small>OPENING FRAME</small>
                    <strong>{hook.text}</strong>
                    <span>0:00 — 0:03</span>
                  </div>
                  <div>
                    <h3>
                      {hook.name}
                      {draft.hookId === hook.id && <Icon name="check" size={17} />}
                    </h3>
                    <p>{hook.mechanism}</p>
                    <small>{hook.hypothesis}</small>
                  </div>
                </button>
              ))}
            </div>
          </section>
          <section className="panel">
            <p className="eyebrow">NARRATIVE STRUCTURE</p>
            <h2>A blueprint for the payoff.</h2>
            <div className="blueprint-grid">
              {state.blueprints.map((bp) => (
                <button
                  key={bp.id}
                  className={`blueprint-card ${draft.blueprintId === bp.id ? 'selected' : ''}`}
                  disabled={!canEdit(state.role)}
                  aria-pressed={draft.blueprintId === bp.id}
                  onClick={() => {
                    const next = structuredClone(draft);
                    next.blueprintId = bp.id;
                    next.scenes.forEach((s, i) => {
                      s.purpose = bp.segments[i % bp.segments.length];
                    });
                    update(next);
                  }}
                >
                  <Icon name="content" />
                  <h3>{bp.name}</h3>
                  <p>{bp.description}</p>
                  <div className="blueprint-beats">
                    {bp.segments.map((segment, i) => (
                      <span key={segment}>
                        {i + 1}. {segment}
                      </span>
                    ))}
                  </div>
                  <small>{bp.prerequisite}</small>
                </button>
              ))}
            </div>
            <h3 className="spaced">Your story beats</h3>
            <div className="form-grid">
              {draft.scenes.map((scene, index) => (
                <label className="field" key={scene.id}>
                  Scene {index + 1} · purpose
                  <input
                    disabled={!canEdit(state.role)}
                    value={scene.purpose}
                    onChange={(e) =>
                      update({
                        ...draft,
                        scenes: draft.scenes.map((s) =>
                          s.id === scene.id ? { ...s, purpose: e.target.value } : s,
                        ),
                      })
                    }
                  />
                </label>
              ))}
            </div>
            <div className="panel-actions">
              <button
                className="button primary"
                onClick={() => navigate('content', content.id, 'assets')}
              >
                Choose ingredients
                <Icon name="arrow" size={16} />
              </button>
            </div>
          </section>
        </div>
      )}
      {tab === 'assets' && (
        <section className="panel">
          <div className="section-heading">
            <div>
              <p className="eyebrow">THE INGREDIENTS</p>
              <h2>Make the most of what you have.</h2>
              <p className="muted">
                A mandatory ingredient must appear in the executable composition.
              </p>
            </div>
            <button className="button secondary" onClick={() => navigate('assets')}>
              Open registry
              <Icon name="arrow" size={15} />
            </button>
          </div>
          <div className="ingredient-list">
            {state.assets.map((asset) => {
              const rep = representationFor(state, asset.id);
              const selected = draft.selectedAssets.find((a) => a.assetId === asset.id);
              const used = draft.scenes.some((s) =>
                s.instances.some((i) => i.assetId === asset.id),
              );
              return (
                <div className="ingredient-row" key={asset.id}>
                  <div className="ingredient-thumb">
                    {rep?.mediaType === 'image' ? (
                      <Image src={rep.src} alt="" width={52} height={55} unoptimized />
                    ) : (
                      <Icon
                        name={rep?.mediaType === 'video' ? 'content' : 'operations'}
                        size={28}
                      />
                    )}
                  </div>
                  <div className="ingredient-info">
                    <strong>{asset.name}</strong>
                    <small>
                      {asset.kind} · {used ? 'Used in composition' : 'Not in composition'}
                    </small>
                  </div>
                  <StatusBadge status={rep?.readiness ?? 'missing'} />
                  <StatusBadge status={rep?.rights ?? 'review_required'} />
                  <label className="check-label">
                    <input
                      type="checkbox"
                      checked={!!selected}
                      disabled={!canEdit(state.role)}
                      onChange={(e) =>
                        update({
                          ...draft,
                          selectedAssets: e.target.checked
                            ? [...draft.selectedAssets, { assetId: asset.id, mandatory: false }]
                            : draft.selectedAssets.filter((a) => a.assetId !== asset.id),
                        })
                      }
                    />
                    Selected
                  </label>
                  <label className="check-label">
                    <input
                      type="checkbox"
                      checked={selected?.mandatory ?? false}
                      disabled={!selected || !canEdit(state.role)}
                      onChange={(e) =>
                        update({
                          ...draft,
                          selectedAssets: draft.selectedAssets.map((a) =>
                            a.assetId === asset.id ? { ...a, mandatory: e.target.checked } : a,
                          ),
                        })
                      }
                    />
                    Mandatory
                  </label>
                </div>
              );
            })}
          </div>
          <div className="notice amber">
            Selected and used are different. Add an object through the scene editor; the plan
            validator catches missing mandatory assets and ineligible representations.
          </div>
          <div className="panel-actions">
            <button className="button secondary" onClick={() => navigate('packs')}>
              Plan missing assets
            </button>
            <button
              className="button primary"
              onClick={async () => {
                if (await flush()) navigate('content', content.id, 'edit');
              }}
            >
              Open scene editor
              <Icon name="arrow" size={16} />
            </button>
          </div>
        </section>
      )}
      {tab === 'edit' && (
        <SceneEditor
          state={state}
          content={content}
          execute={execute}
          focusSceneId={focus.sceneId}
          focusInstanceId={focus.instanceId}
        />
      )}
      {tab === 'run' && (
        <>
          <section className="panel render-panel">
            <div>
              <p className="eyebrow">A DELIBERATE NEXT STEP</p>
              <h2>Preview first. Render when ready.</h2>
              <p>
                Rendering creates a frozen simulated output for review. No provider is contacted and
                no money is spent.
              </p>
            </div>
            <div className="row">
              <button
                className="button secondary"
                disabled={!canEdit(state.role) || busy}
                onClick={() => void perform('repairPlan')}
              >
                Repair plan
              </button>
              <button
                className="button secondary"
                disabled={!canEdit(state.role) || busy}
                onClick={() => void perform('newCandidate')}
              >
                New candidate · simulated
              </button>
              <button
                className="button primary"
                disabled={!canEdit(state.role) || busy}
                onClick={() => void perform('renderRevision')}
              >
                Render saved revision · simulated
              </button>
            </div>
          </section>
          <OperationsWorkspace {...props} contentId={content.id} />
        </>
      )}
      {tab === 'review' &&
        (packageRecords.length ? (
          <div className="stack">
            {detail && (
              <button
                className="text-button"
                onClick={() => navigate('content', content.id, 'review')}
              >
                Show all package revisions
              </button>
            )}
            {[...packageRecords].reverse().map((pack) => (
              <PackageReview
                key={pack.id}
                {...props}
                pack={pack}
                onFinding={(sceneId, instanceId) => {
                  setFocus({ sceneId, instanceId });
                  navigate('content', content.id, 'edit', `${sceneId ?? ''}|${instanceId ?? ''}`);
                }}
              />
            ))}
          </div>
        ) : (
          <EmptyState
            title="A review begins with an output"
            action={
              <button
                className="button primary"
                onClick={() => navigate('content', content.id, 'run')}
              >
                Prepare a simulated render
              </button>
            }
          >
            Save a revision, create a preview and simulate a render to produce a frozen package for
            review.
          </EmptyState>
        ))}
      {tab === 'publish' && <PublicationWorkspace {...props} contentId={content.id} />}
    </div>
  );
}

export function OperationsWorkspace({
  state,
  execute,
  navigate,
  contentId,
  selectedRunId,
}: WorkspaceProps & { contentId?: string; selectedRunId?: string }) {
  const [filter, setFilter] = useState('all');
  const runs = state.runs.filter(
    (r) =>
      (!contentId || r.contentId === contentId) &&
      (!selectedRunId || r.id === selectedRunId) &&
      (filter === 'all' || r.status === filter),
  );
  const [working, setWorking] = useState<string | null>(null);
  const act = async (command: Command, id: string) => {
    setWorking(id);
    const result = await execute(command);
    setWorking(null);
    if (result.ok && command.type === 'retryRun' && result.entityId) {
      if (selectedRunId) navigate('operations', result.entityId);
      setFilter('all');
    }
  };
  return (
    <div className="stack">
      <div className="notice">
        Execution and all amounts below are simulated. Estimates, reserved amounts, settled spend
        and uncertain liability remain separate.
      </div>
      <div className="section-heading">
        <h2>{contentId ? 'Execution history' : 'Production activity'}</h2>
        <label className="compact-select">
          <span className="sr-only">Filter runs</span>
          <select value={filter} onChange={(e) => setFilter(e.target.value)}>
            {['all', 'running', 'failed', 'outcome_unknown', 'succeeded', 'blocked'].map(
              (value) => (
                <option key={value} value={value}>
                  {value.replaceAll('_', ' ')}
                </option>
              ),
            )}
          </select>
        </label>
      </div>
      {runs.map((run) => {
        const c = state.contents.find((c) => c.id === run.contentId);
        const rev = state.revisions.find((r) => r.id === run.revisionId);
        return (
          <section
            className={`panel run-panel ${run.status === 'outcome_unknown' ? 'unknown-run' : ''}`}
            key={run.id}
          >
            <div className="section-heading">
              <div>
                <button
                  className="text-button run-title"
                  onClick={() => navigate('content', run.contentId, 'run')}
                >
                  {c?.draft.title ?? 'Content'}
                  <Icon name="arrow" size={15} />
                </button>
                <p className="muted small">
                  {rev ? `Revision ${rev.number}` : 'Pinned revision'} · Attempt {run.attempt} ·{' '}
                  {run.kind === 'candidate' ? 'Fresh candidate' : 'Simulated render'}
                </p>
              </div>
              <StatusBadge status={run.status} />
            </div>
            <div className="run-stages">
              {run.stages.map((stage, index) => (
                <div key={stage.name} className={`run-stage ${stage.status}`}>
                  <span>
                    {stage.status === 'succeeded' ? <Icon name="check" size={15} /> : index + 1}
                  </span>
                  <div>
                    <strong>{stage.name}</strong>
                    <small>{stage.detail}</small>
                  </div>
                </div>
              ))}
            </div>
            <div className="cost-grid">
              <div>
                <small>Estimate</small>
                <strong>{money(run.estimate)}</strong>
              </div>
              <div>
                <small>Reserved</small>
                <strong>{money(run.reserved)}</strong>
              </div>
              <div>
                <small>Settled</small>
                <strong>{money(run.spent)}</strong>
              </div>
              <div>
                <small>Uncertain liability</small>
                <strong>{money(run.uncertain)}</strong>
              </div>
            </div>
            {run.error && <div className="notice amber">{run.error}</div>}
            <div className="panel-actions">
              {run.status === 'outcome_unknown' ? (
                <>
                  <p className="muted small">
                    Reconcile the original submission before considering another attempt.
                  </p>
                  <button
                    className="button primary"
                    disabled={!canEdit(state.role) || working === run.id}
                    onClick={() => void act({ type: 'reconcileRun', runId: run.id }, run.id)}
                  >
                    Reconcile outcome · simulated
                  </button>
                </>
              ) : run.status === 'failed' ? (
                <>
                  <button
                    className="button secondary"
                    onClick={() => navigate('content', run.contentId, 'edit')}
                  >
                    Change creative revision
                  </button>
                  <button
                    className="button primary"
                    disabled={!canEdit(state.role) || working === run.id}
                    onClick={() => void act({ type: 'retryRun', runId: run.id }, run.id)}
                  >
                    Retry execution · simulated
                  </button>
                </>
              ) : run.status === 'succeeded' ? (
                <button
                  className="button secondary"
                  onClick={() =>
                    navigate(
                      'content',
                      run.contentId,
                      'review',
                      state.packages.find((p) => p.runId === run.id)?.id,
                    )
                  }
                >
                  Review this output
                  <Icon name="arrow" size={16} />
                </button>
              ) : run.status === 'blocked' ? (
                <button
                  className="button secondary"
                  onClick={() => navigate('content', run.contentId, 'assets')}
                >
                  Inspect constraints
                </button>
              ) : (
                <span className="muted small">
                  Progress resumes across refresh. No external work is running.
                </span>
              )}
            </div>
            <details className="diagnostics">
              <summary>Advanced diagnostics</summary>
              <pre>
                {JSON.stringify(
                  {
                    runId: run.id,
                    revisionId: run.revisionId,
                    simulated: true,
                    createdAt: run.createdAt,
                  },
                  null,
                  2,
                )}
              </pre>
            </details>
          </section>
        );
      })}
      {!runs.length && (
        <EmptyState
          title="Nothing in this queue"
          action={
            <button
              className="button secondary"
              onClick={() =>
                contentId ? navigate('content', contentId, 'edit') : navigate('content')
              }
            >
              Return to content
            </button>
          }
        >
          Runs appear here after you simulate an execution. Try another status filter if you
          expected an existing run.
        </EmptyState>
      )}
    </div>
  );
}

export function ReviewWorkspace(props: WorkspaceProps) {
  const [filter, setFilter] = useState('review');
  const packs = props.state.packages.filter((p) => filter === 'all' || p.status === filter);
  return (
    <div className="stack">
      <div className="section-heading">
        <p className="muted">Review the exact output, its ingredients and its publication copy.</p>
        <div className="filter-tabs">
          {['review', 'approved', 'rejected', 'all'].map((value) => (
            <button
              className={value === filter ? 'active' : ''}
              onClick={() => setFilter(value)}
              key={value}
            >
              {value === 'review' ? 'Needs review' : value[0].toUpperCase() + value.slice(1)}
            </button>
          ))}
        </div>
      </div>
      {packs.map((pack) => (
        <PackageReview
          {...props}
          pack={pack}
          key={pack.id}
          onFinding={(sceneId, instanceId) =>
            props.navigate(
              'content',
              pack.contentId,
              'edit',
              `${sceneId ?? ''}|${instanceId ?? ''}`,
            )
          }
        />
      ))}
      {!packs.length && (
        <EmptyState
          title="A clear review queue"
          action={
            <button className="button primary" onClick={() => props.navigate('content')}>
              Open content
            </button>
          }
        >
          There are no packages in this review state.
        </EmptyState>
      )}
    </div>
  );
}
function PackageReview({
  state,
  execute,
  navigate,
  pack,
  onFinding,
}: WorkspaceProps & {
  pack: PackageRecord;
  onFinding?: (sceneId?: string, instanceId?: string) => void;
}) {
  const revision = state.revisions.find((r) => r.id === pack.revisionId);
  const parent = state.revisions.find((r) => r.id === revision?.parentId);
  const content = state.contents.find((c) => c.id === pack.contentId);
  const [compare, setCompare] = useState(false);
  const [reason, setReason] = useState('');
  const [frame, setFrame] = useState(0);
  const [busy, setBusy] = useState(false);
  const hasFailure = pack.findings.some((f) => f.severity === 'fail');
  if (!revision)
    return <div className="notice red">Pinned revision unavailable. Approval is blocked.</div>;
  const act = async (command: Command) => {
    setBusy(true);
    await execute(command);
    setBusy(false);
  };
  const newerDraft =
    !!content && JSON.stringify(content.draft) !== JSON.stringify(revision.composition);
  return (
    <section className="panel package-review">
      <div className="section-heading">
        <div>
          <p className="eyebrow">EXACT PACKAGE REVIEW</p>
          <h2>{revision.composition.title}</h2>
          <p className="muted small">
            Revision {revision.number} · frozen composition preview · simulated output
          </p>
        </div>
        <StatusBadge status={pack.status} />
      </div>
      {newerDraft && (
        <div className="notice amber">
          A newer draft is available. This review and any approval apply only to revision{' '}
          {revision.number} and the copy shown below.
        </div>
      )}
      <div className="review-layout">
        <div className="review-media">
          <div className={`comparison-grid ${compare ? 'comparing' : ''}`}>
            {compare && (
              <div>
                <p className="eyebrow">
                  {parent ? `PARENT · REVISION ${parent.number}` : 'NO PARENT REVISION'}
                </p>
                {parent ? (
                  <CompositionPreview
                    composition={parent.composition}
                    state={state}
                    frame={Math.min(frame, parent.composition.totalFrames - 1)}
                  />
                ) : (
                  <div className="empty-state">This is the first saved revision.</div>
                )}
              </div>
            )}
            <div>
              <p className="eyebrow">REVIEWING · REVISION {revision.number}</p>
              <CompositionPreview composition={revision.composition} state={state} frame={frame} />
            </div>
          </div>
          <label className="review-scrub">
            Review frame · {frame} / {revision.composition.totalFrames - 1}
            <input
              type="range"
              aria-label={`Review frame for ${revision.composition.title}`}
              min={0}
              max={revision.composition.totalFrames - 1}
              value={frame}
              onChange={(e) => setFrame(Number(e.target.value))}
            />
          </label>
          <button className="button secondary" onClick={() => setCompare(!compare)}>
            {compare ? 'Show selected revision' : 'Compare with parent'}
          </button>
          <p className="muted small">
            Interactive frozen preview. An encoded final video is unavailable in this prototype.
          </p>
        </div>
        <div className="review-evidence">
          <h3>What needs your judgement</h3>
          <div className="findings-list">
            {pack.findings.map((finding) => (
              <button
                key={finding.id}
                className={`finding ${finding.severity}`}
                onClick={() => {
                  if (finding.frame !== undefined)
                    setFrame(Math.min(finding.frame, revision.composition.totalFrames - 1));
                  if (onFinding && finding.sceneId) onFinding(finding.sceneId, finding.instanceId);
                }}
              >
                <div className="row">
                  <StatusBadge status={finding.severity} />
                  <small>
                    {finding.evidence === 'local_check'
                      ? 'Local structural check'
                      : 'Simulated evidence'}
                  </small>
                </div>
                <strong>{finding.title}</strong>
                <p>{finding.detail}</p>
                {finding.sceneId && (
                  <span className="finding-link">
                    {onFinding
                      ? 'Inspect affected scene'
                      : `Scene ${revision.composition.scenes.findIndex((s) => s.id === finding.sceneId) + 1}`}{' '}
                    · frame {finding.frame ?? 0}
                    <Icon name="arrow" size={13} />
                  </span>
                )}
              </button>
            ))}
          </div>
          <div className="copy-review">
            <h3>Publication copy · pinned</h3>
            <p>{pack.copy}</p>
            <small>
              Disclosures:{' '}
              {pack.disclosures || 'No commercial relationship declared in this fixture.'}
            </small>
            <p className="muted small">
              Cover frame {pack.coverFrame}. Changing copy or cover creates a new package approval
              requirement.
            </p>
          </div>
          {pack.status === 'review' && (
            <>
              <label className="field">
                Review note / rejection reason
                <textarea
                  rows={2}
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder="What should change?"
                  disabled={!canReview(state.role)}
                />
              </label>
              <div className="row review-actions">
                <button
                  className="button secondary"
                  disabled={!canReview(state.role) || !reason.trim() || busy}
                  onClick={() => void act({ type: 'rejectPackage', packageId: pack.id, reason })}
                >
                  Request changes
                </button>
                <button
                  className="button primary"
                  disabled={!canReview(state.role) || hasFailure || busy}
                  onClick={() => void act({ type: 'approvePackage', packageId: pack.id })}
                >
                  <Icon name="check" size={16} />
                  Approve package
                </button>
              </div>
              {hasFailure && (
                <p className="notice red">Hard failures must be repaired before approval.</p>
              )}
              {!canReview(state.role) && (
                <p className="muted small">Owner or reviewer permission is required to approve.</p>
              )}
            </>
          )}
          {pack.status === 'approved' && (
            <div className="notice green">
              Revision {revision.number} approved by {pack.approvedBy}.{' '}
              <button
                className="text-button"
                onClick={() => navigate('content', pack.contentId, 'publish')}
              >
                Prepare publication
                <Icon name="arrow" size={15} />
              </button>
            </div>
          )}
          {pack.status === 'rejected' && (
            <div className="notice amber">
              Changes requested: {pack.rejectionReason}
              <button
                className="text-button"
                onClick={() => navigate('content', pack.contentId, 'edit')}
              >
                Open working draft
              </button>
            </div>
          )}
        </div>
      </div>
      <details className="diagnostics">
        <summary>Package manifest and timing evidence</summary>
        <p>
          Plan intervals are actual local values. Compiled and measured media evidence is
          unavailable until a real renderer is connected.
        </p>
        <pre>
          {JSON.stringify(
            {
              packageId: pack.id,
              revisionId: pack.revisionId,
              approvalId: pack.approvalId ?? null,
              encodedVideo: 'unavailable_in_prototype',
              timing: {
                plannedFrames: revision.composition.totalFrames,
                compiledFrames: null,
                measuredFrames: null,
              },
              artifacts: ['composition.json', 'copy', 'provenance', 'simulated_review'],
              simulated: true,
            },
            null,
            2,
          )}
        </pre>
      </details>
    </section>
  );
}

export function PublicationWorkspace({
  state,
  execute,
  navigate,
  contentId,
}: WorkspaceProps & { contentId?: string }) {
  const approved = state.packages.filter(
    (p) => p.status === 'approved' && (!contentId || p.contentId === contentId),
  );
  const publications = state.publications.filter((p) => !contentId || p.contentId === contentId);
  const [packageId, setPackageId] = useState(approved[0]?.id ?? '');
  const [account, setAccount] = useState('@object.stories');
  const [timezone, setTimezone] = useState('Europe/London');
  const [schedule, setSchedule] = useState('');
  const [postRef, setPostRef] = useState('');
  const [postedAt, setPostedAt] = useState('');
  const [postingId, setPostingId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [timeError, setTimeError] = useState('');
  const selectedPackage = approved.find((p) => p.id === packageId) ?? approved[0];
  const selectedRevision = state.revisions.find((r) => r.id === selectedPackage?.revisionId);
  const download =
    selectedPackage && selectedRevision ? buildPrototypeHandoff(state, selectedPackage) : null;
  return (
    <div className="stack">
      <div className="notice">
        Manual posting is the initial boundary. This prototype prepares downloadable records and
        simulated post confirmations; it cannot publish or encode a final video.
      </div>
      {approved.length ? (
        <section className="panel">
          <div className="section-heading">
            <div>
              <p className="eyebrow">READY FOR HANDOFF</p>
              <h2>A deliberate last look.</h2>
            </div>
            <Badge tone="green">
              {approved.length} approved {approved.length === 1 ? 'package' : 'packages'}
            </Badge>
          </div>
          <form
            className="publication-form"
            onSubmit={async (e) => {
              e.preventDefault();
              if (!selectedPackage) return;
              setTimeError('');
              let scheduledAt: string | undefined;
              try {
                scheduledAt = schedule ? zonedLocalToIso(schedule, timezone) : undefined;
              } catch (error) {
                setTimeError((error as Error).message);
                return;
              }
              setBusy(true);
              await execute({
                type: 'preparePublication',
                packageId: selectedPackage.id,
                account,
                timezone,
                scheduledAt,
              });
              setBusy(false);
            }}
          >
            <fieldset
              className="form-stack"
              disabled={state.role !== 'owner' && state.role !== 'reviewer'}
            >
              <div className="form-grid">
                <label className="field">
                  Approved package
                  <select
                    value={selectedPackage?.id ?? ''}
                    onChange={(e) => setPackageId(e.target.value)}
                  >
                    {approved.map((p) => (
                      <option key={p.id} value={p.id}>
                        {state.revisions.find((r) => r.id === p.revisionId)?.composition.title} ·{' '}
                        {p.id.slice(-8)}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  Destination account
                  <input value={account} onChange={(e) => setAccount(e.target.value)} required />
                </label>
                <label className="field">
                  Timezone
                  <select value={timezone} onChange={(e) => setTimezone(e.target.value)}>
                    <option>Europe/London</option>
                    <option>UTC</option>
                    <option>America/New_York</option>
                  </select>
                </label>
                <label className="field">
                  Optional schedule · {timezone} · simulation
                  <input
                    type="datetime-local"
                    value={schedule}
                    onChange={(e) => setSchedule(e.target.value)}
                  />
                </label>
              </div>
              <div className="copy-review">
                <h3>Approved copy</h3>
                <p>{selectedPackage?.copy}</p>
                <small>
                  Disclosures: {selectedPackage?.disclosures || 'None declared in this fixture.'}
                </small>
                <p className="muted small">
                  Copy is pinned to the approval. Edit the content draft and obtain a new approval
                  to change it.
                </p>
              </div>
              <div className="row">
                <button className="button primary" disabled={busy}>
                  Prepare manual handoff
                </button>
                <button
                  className="button secondary"
                  type="button"
                  disabled
                  title="No authorised publishing adapter is connected"
                >
                  Connect publisher · unavailable
                </button>
              </div>
            </fieldset>
          </form>
          {timeError && (
            <p className="notice red" role="alert">
              {timeError}
            </p>
          )}
          {download && (
            <div className="panel-actions">
              <p className="muted small">
                Bundle includes the actual edited plan and simulated package records. No
                final_video.mp4 is fabricated.
              </p>
              <DownloadButton
                data={download}
                filename={`prototype-handoff-${selectedPackage?.id}.json`}
              >
                Download prototype handoff
              </DownloadButton>
            </div>
          )}
        </section>
      ) : (
        <EmptyState
          title="Approval comes first"
          action={
            <button
              className="button primary"
              onClick={() =>
                contentId ? navigate('content', contentId, 'review') : navigate('review')
              }
            >
              Open review queue
            </button>
          }
        >
          Approve an exact output and its copy before preparing a publication.
        </EmptyState>
      )}
      <section className="panel">
        <div className="section-heading">
          <h2>Publication records</h2>
          <Badge>All records simulated</Badge>
        </div>
        {publications.map((publication) => {
          const pack = state.packages.find((p) => p.id === publication.packageId);
          const revision = state.revisions.find((r) => r.id === pack?.revisionId);
          return (
            <article className="publication-record" key={publication.id}>
              <div className="section-heading">
                <div>
                  <h3>{revision?.composition.title}</h3>
                  <p className="muted small">
                    {publication.account} · {publication.timezone} · approval{' '}
                    {publication.approvalId.slice(-8)}
                  </p>
                </div>
                <StatusBadge status={publication.status} />
              </div>
              {publication.scheduledAt && (
                <p className="muted small">
                  Simulated scheduled instant:{' '}
                  {new Date(publication.scheduledAt).toLocaleString('en-GB', {
                    timeZone: publication.timezone,
                  })}{' '}
                  ({publication.timezone}). No automatic submission.
                </p>
              )}
              {publication.status === 'published' ? (
                <>
                  <div className="notice green">
                    Recorded simulated external reference: {publication.externalReference}
                    <br />
                    Timestamp: {publication.postedAt}
                  </div>
                  <button className="text-button" onClick={() => navigate('learning')}>
                    View observations
                    <Icon name="arrow" size={15} />
                  </button>
                </>
              ) : postingId === publication.id ? (
                <form
                  className="form-stack"
                  onSubmit={async (e) => {
                    e.preventDefault();
                    setTimeError('');
                    let timestamp: string;
                    try {
                      timestamp = zonedLocalToIso(postedAt, publication.timezone);
                    } catch (error) {
                      setTimeError((error as Error).message);
                      return;
                    }
                    setBusy(true);
                    const result = await execute({
                      type: 'recordPost',
                      publicationId: publication.id,
                      externalReference: postRef,
                      postedAt: timestamp,
                    });
                    setBusy(false);
                    if (result.ok) {
                      setPostingId(null);
                      setPostRef('');
                      setPostedAt('');
                    }
                  }}
                >
                  <div className="form-grid">
                    <label className="field">
                      External post reference · example
                      <input
                        required
                        value={postRef}
                        onChange={(e) => setPostRef(e.target.value)}
                        placeholder="demo:post-1042"
                      />
                    </label>
                    <label className="field">
                      Actual post timestamp · simulation · {publication.timezone}
                      <input
                        type="datetime-local"
                        required
                        value={postedAt}
                        onChange={(e) => setPostedAt(e.target.value)}
                      />
                    </label>
                  </div>
                  {timeError && (
                    <p className="notice red" role="alert">
                      {timeError}
                    </p>
                  )}
                  <div className="row">
                    <button className="button primary" disabled={busy}>
                      Confirm simulated post
                    </button>
                    <button
                      type="button"
                      className="button ghost"
                      onClick={() => setPostingId(null)}
                    >
                      Cancel
                    </button>
                  </div>
                </form>
              ) : (
                <button
                  className="button secondary"
                  disabled={state.role !== 'owner' && state.role !== 'reviewer'}
                  onClick={() => setPostingId(publication.id)}
                >
                  Record manual post · simulated
                </button>
              )}
            </article>
          );
        })}
        {!publications.length && (
          <div className="inline-empty">
            <Icon name="publication" size={28} />
            <p>Prepared and confirmed publication records will appear here.</p>
            <small>Downloading a package never marks it as published.</small>
          </div>
        )}
      </section>
    </div>
  );
}
