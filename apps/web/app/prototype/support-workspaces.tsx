'use client';

import {
  cloneElement,
  useEffect,
  useId,
  useState,
  type FormEvent,
  type ReactElement,
  type ReactNode,
} from 'react';
import {
  canEdit,
  canReview,
  money,
  representationFor,
  type Asset,
  type AssetKind,
  type AssetPack,
  type CommandResult,
  type Idea,
  type PageProfile,
  type Representation,
  type WorkspaceProps,
} from './domain';
import './support-workspaces.css';

function human(value: string): string {
  return value.replaceAll('_', ' ');
}
function Feedback({ result }: { result: CommandResult | null }) {
  if (!result) return null;
  return (
    <div
      className={`notice support-feedback ${result.ok ? 'support-success' : 'support-error'}`}
      role={result.ok ? 'status' : 'alert'}
    >
      {result.message}
      {!result.ok && result.fields && (
        <ul>
          {Object.entries(result.fields).map(([key, value]) => (
            <li key={key}>
              {human(key)}: {value}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  const id = useId();
  return (
    <div className="field support-field">
      <label htmlFor={id}>{label}</label>
      {cloneElement(children as ReactElement<{ id: string; 'aria-describedby'?: string }>, {
        id,
        'aria-describedby': hint ? `${id}-hint` : undefined,
      })}
      {hint && (
        <small id={`${id}-hint`} className="muted">
          {hint}
        </small>
      )}
    </div>
  );
}
function PermissionNote({
  allowed,
  action = 'make changes',
}: {
  allowed: boolean;
  action?: string;
}) {
  return allowed ? null : (
    <p className="support-permission">
      <span aria-hidden="true">◈</span> Your current role can inspect this workspace. Switch to an
      authorised role to {action}.
    </p>
  );
}
function Count({ value, label }: { value: ReactNode; label: string }) {
  return (
    <div className="support-count">
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}
function PageSelect({
  state,
  value,
  onChange,
  label = 'Page',
}: Pick<WorkspaceProps, 'state'> & {
  value: string;
  onChange: (id: string) => void;
  label?: string;
}) {
  return (
    <Field label={label}>
      <select value={value} onChange={(e) => onChange(e.target.value)} required>
        <option value="">Choose a page</option>
        {state.pages.map((page) => (
          <option key={page.id} value={page.id}>
            {page.name}
          </option>
        ))}
      </select>
    </Field>
  );
}
function useFirstPage(state: WorkspaceProps['state']) {
  const [pageId, setPageId] = useState(state.pages[0]?.id ?? '');
  useEffect(() => {
    if (!state.pages.some((p) => p.id === pageId)) setPageId(state.pages[0]?.id ?? '');
  }, [state.pages, pageId]);
  return [pageId, setPageId] as const;
}

const EMPTY_PAGE: PageProfile = {
  id: '',
  name: '',
  handle: '',
  purpose: '',
  audience: '',
  voice: '',
  topics: [],
  color: '#8c528a',
  locale: 'en-GB',
  format: '9:16',
  disclosures: '',
  budgetMinor: 2500,
  policyOverride: false,
};

export function PagesWorkspace({ state, execute, navigate }: WorkspaceProps) {
  const editable = canEdit(state.role);
  const [editing, setEditing] = useState<PageProfile | null>(null);
  const [result, setResult] = useState<CommandResult | null>(null);
  const [pending, setPending] = useState(false);
  const [topics, setTopics] = useState('');
  function open(page: PageProfile) {
    setEditing({ ...page });
    setTopics(page.topics.join(', '));
    setResult(null);
  }
  async function save(event: FormEvent) {
    event.preventDefault();
    if (!editing) return;
    setPending(true);
    const response = await execute({
      type: 'savePage',
      page: {
        ...editing,
        name: editing.name.trim(),
        topics: topics
          .split(',')
          .map((t) => t.trim())
          .filter(Boolean),
      },
    });
    setResult(response);
    setPending(false);
    if (response.ok) {
      const saved =
        response.state.pages.find((p) => p.id === response.entityId) ??
        response.state.pages.find((p) => p.name === editing.name.trim());
      if (saved) setEditing(saved);
    }
  }
  const update = <K extends keyof PageProfile>(key: K, value: PageProfile[K]) =>
    setEditing((current) => (current ? { ...current, [key]: value } : current));
  return (
    <div className="support-workspace stack">
      <div className="support-summary-row">
        <div className="support-summary-copy">
          <span className="eyebrow">A distinct point of view</span>
          <h2>Build brands people recognise.</h2>
          <p className="muted">
            Give every page a purpose, an audience and clear production limits.
          </p>
        </div>
        <button
          className="button primary"
          disabled={!editable}
          onClick={() => open({ ...EMPTY_PAGE })}
        >
          ＋ New page
        </button>
      </div>
      <PermissionNote allowed={editable} action="create or edit a page" />
      <div className={editing ? 'support-master-detail' : ''}>
        <div className="support-page-grid">
          {state.pages.map((page) => {
            const items = state.contents.filter((item) => item.pageId === page.id);
            return (
              <article
                className={`panel support-page-card ${editing?.id === page.id ? 'support-selected' : ''}`}
                key={page.id}
              >
                <div className="support-brand-strip" style={{ background: page.color }}>
                  <div className="support-brand-monogram">
                    {page.name
                      .split(' ')
                      .map((w) => w[0])
                      .join('')
                      .slice(0, 2)}
                  </div>
                  <span>
                    {page.locale} <span aria-hidden="true">·</span> {page.format}
                  </span>
                </div>
                <div className="support-card-body">
                  <div className="row">
                    <h3>{page.name}</h3>
                    <span className="badge">
                      {page.policyOverride ? 'Page policy' : 'Inherited policy'}
                    </span>
                  </div>
                  <p className="support-handle">{page.handle || 'Handle not set'}</p>
                  <p>{page.purpose}</p>
                  <div className="support-tags">
                    {page.topics.slice(0, 3).map((topic) => (
                      <span className="support-tag" key={topic}>
                        {topic}
                      </span>
                    ))}
                  </div>
                  <div className="support-card-stat-row">
                    <Count value={items.length} label="Content items" />
                    <Count value={money(page.budgetMinor)} label="Production budget" />
                  </div>
                  <div className="support-card-actions">
                    <button className="button secondary" onClick={() => open(page)}>
                      {editable ? 'Edit brand' : 'View brand'}
                    </button>
                    <button className="button ghost" onClick={() => navigate('ideas')}>
                      Find ideas <span aria-hidden="true">↗</span>
                    </button>
                  </div>
                </div>
              </article>
            );
          })}
          {!state.pages.length && (
            <div className="panel empty-state support-empty">
              <span className="support-empty-icon" aria-hidden="true">
                ◧
              </span>
              <h3>Your first page starts here</h3>
              <p className="muted">
                Define the audience and purpose before building your first piece of content.
              </p>
              <button
                className="button primary"
                disabled={!editable}
                onClick={() => open({ ...EMPTY_PAGE })}
              >
                Create a page
              </button>
            </div>
          )}
        </div>
        {editing && (
          <section className="panel support-editor-panel">
            <div className="section-heading">
              <div>
                <span className="eyebrow">Brand profile</span>
                <h3>{editing.id ? editing.name : 'Create a page'}</h3>
              </div>
              <button
                className="button ghost"
                aria-label="Close page editor"
                onClick={() => setEditing(null)}
              >
                ✕
              </button>
            </div>
            <form onSubmit={(e) => void save(e)} className="stack">
              <fieldset disabled={!editable || pending} className="support-fieldset stack">
                <div className="form-grid">
                  <Field label="Page name">
                    <input
                      required
                      value={editing.name}
                      onChange={(e) => update('name', e.target.value)}
                      placeholder="Object Stories"
                    />
                  </Field>
                  <Field label="Handle">
                    <input
                      value={editing.handle}
                      onChange={(e) => update('handle', e.target.value)}
                      placeholder="@objectstories"
                    />
                  </Field>
                </div>
                <Field label="Purpose">
                  <textarea
                    required
                    rows={2}
                    value={editing.purpose}
                    onChange={(e) => update('purpose', e.target.value)}
                    placeholder="What is this page here to do?"
                  />
                </Field>
                <Field label="Audience">
                  <input
                    required
                    value={editing.audience}
                    onChange={(e) => update('audience', e.target.value)}
                    placeholder="Who will find this useful?"
                  />
                </Field>
                <Field label="Voice and tone">
                  <input
                    required
                    value={editing.voice}
                    onChange={(e) => update('voice', e.target.value)}
                    placeholder="Curious, warm, specific"
                  />
                </Field>
                <Field label="Content pillars" hint="Separate topics with commas.">
                  <input
                    required
                    value={topics}
                    onChange={(e) => setTopics(e.target.value)}
                    placeholder="Everyday design, making, materials"
                  />
                </Field>
                <div className="form-grid">
                  <Field label="Locale">
                    <select
                      value={editing.locale}
                      onChange={(e) => update('locale', e.target.value)}
                    >
                      <option value="en-GB">English · United Kingdom</option>
                      <option value="en-US">English · United States</option>
                      <option value="fr-FR">French · France</option>
                      <option value="ar-EG">Arabic · Egypt</option>
                    </select>
                  </Field>
                  <Field label="Primary format">
                    <select
                      value={editing.format}
                      onChange={(e) => update('format', e.target.value)}
                    >
                      <option value="9:16">Vertical · 9:16</option>
                      <option value="1:1">Square · 1:1</option>
                      <option value="16:9">Landscape · 16:9</option>
                    </select>
                  </Field>
                </div>
                <Field label="Brand colour">
                  <div className="support-color-field">
                    <input
                      type="color"
                      value={editing.color}
                      onChange={(e) => update('color', e.target.value)}
                    />
                    <span>{editing.color.toUpperCase()}</span>
                  </div>
                </Field>
                <Field label="Required disclosures">
                  <textarea
                    rows={2}
                    value={editing.disclosures}
                    onChange={(e) => update('disclosures', e.target.value)}
                    placeholder="Affiliate links, gifted products, synthetic media…"
                  />
                </Field>
                <div className="support-policy-box">
                  <div className="row">
                    <strong>Effective production policy</strong>
                    <span className="badge">
                      {editing.policyOverride ? 'Page override' : 'Organisation → page'}
                    </span>
                  </div>
                  <p className="muted">
                    {editing.policyOverride
                      ? 'This page has its own production budget across runs.'
                      : 'This page inherits the organisation’s default £25.00 page production budget. Required rights and QA checks still apply.'}
                  </p>
                  <label className="support-checkbox">
                    <input
                      type="checkbox"
                      checked={editing.policyOverride}
                      onChange={(e) => {
                        update('policyOverride', e.target.checked);
                        if (!e.target.checked) update('budgetMinor', 2500);
                      }}
                    />
                    Set a page-specific budget
                  </label>
                  <Field label="Page production budget (£)">
                    <input
                      type="number"
                      min="1"
                      max="1000"
                      step="0.01"
                      required
                      disabled={!editing.policyOverride}
                      value={(editing.policyOverride ? editing.budgetMinor : 2500) / 100}
                      onChange={(e) =>
                        update('budgetMinor', Math.round(Number(e.target.value) * 100))
                      }
                    />
                  </Field>
                </div>
                <button type="submit" className="button primary">
                  {pending ? 'Saving profile…' : editing.id ? 'Save brand profile' : 'Create page'}
                </button>
              </fieldset>
              <Feedback result={result} />
            </form>
          </section>
        )}
      </div>
    </div>
  );
}

function NewIdeaForm({
  state,
  execute,
  close,
}: Pick<WorkspaceProps, 'state' | 'execute'> & { close: () => void }) {
  const [idea, setIdea] = useState<Omit<Idea, 'id' | 'status'>>({
    pageId: state.pages[0]?.id ?? '',
    title: '',
    summary: '',
    evidence: '',
    fit: '',
    freshness: 'fresh',
    family: 'product',
  });
  const [pending, setPending] = useState(false);
  const [result, setResult] = useState<CommandResult | null>(null);
  return (
    <section className="panel" aria-label="New idea">
      <div className="section-heading">
        <h3>Give the next idea a place.</h3>
        <button className="button ghost" onClick={close}>
          Close idea form
        </button>
      </div>
      <form
        className="stack"
        onSubmit={async (e) => {
          e.preventDefault();
          setPending(true);
          const response = await execute({ type: 'createIdea', idea });
          setResult(response);
          setPending(false);
          if (response.ok) close();
        }}
      >
        <fieldset className="form-grid" disabled={!canEdit(state.role) || pending}>
          <PageSelect
            state={state}
            value={idea.pageId}
            onChange={(pageId) => setIdea({ ...idea, pageId })}
            label="Idea page"
          />
          <Field label="Idea title">
            <input
              required
              value={idea.title}
              onChange={(e) => setIdea({ ...idea, title: e.target.value })}
            />
          </Field>
          <Field label="Premise">
            <textarea
              required
              value={idea.summary}
              onChange={(e) => setIdea({ ...idea, summary: e.target.value })}
            />
          </Field>
          <Field
            label="Evidence and source note"
            hint="State what you observed, or label it as a creative hypothesis."
          >
            <textarea
              required
              value={idea.evidence}
              onChange={(e) => setIdea({ ...idea, evidence: e.target.value })}
            />
          </Field>
          <Field label="Why this page">
            <input
              required
              value={idea.fit}
              onChange={(e) => setIdea({ ...idea, fit: e.target.value })}
            />
          </Field>
          <Field label="Evidence freshness">
            <select
              value={idea.freshness}
              onChange={(e) => setIdea({ ...idea, freshness: e.target.value as Idea['freshness'] })}
            >
              <option value="fresh">Current</option>
              <option value="expiring">Expiring soon</option>
              <option value="expired">Expired · briefing blocked</option>
            </select>
          </Field>
          <Field label="Production family">
            <select
              value={idea.family}
              onChange={(e) => setIdea({ ...idea, family: e.target.value as Idea['family'] })}
            >
              <option value="product">Layered product story</option>
              <option value="graphic">Graphic explainer</option>
              <option value="video">Narrated source video</option>
            </select>
          </Field>
        </fieldset>
        <button
          className="button primary"
          disabled={pending || !idea.pageId || !canEdit(state.role)}
        >
          {pending ? 'Saving idea…' : 'Save idea'}
        </button>
        <Feedback result={result} />
      </form>
    </section>
  );
}
export function IdeasWorkspace({ state, execute, navigate }: WorkspaceProps) {
  const [creating, setCreating] = useState(false);
  const editable = canEdit(state.role);
  const [pageFilter, setPageFilter] = useState('all');
  const [status, setStatus] = useState('suggested');
  const [query, setQuery] = useState('');
  const [pendingId, setPendingId] = useState('');
  const [result, setResult] = useState<CommandResult | null>(null);
  const ideas = state.ideas.filter(
    (idea) =>
      (pageFilter === 'all' || idea.pageId === pageFilter) &&
      (status === 'all' || idea.status === status) &&
      `${idea.title} ${idea.summary}`.toLowerCase().includes(query.toLowerCase()),
  );
  async function decide(ideaId: string, decision: 'held' | 'rejected' | 'suggested') {
    setPendingId(ideaId);
    setResult(await execute({ type: 'setIdeaStatus', ideaId, status: decision }));
    setPendingId('');
  }
  async function createBrief(ideaId: string) {
    const idea = state.ideas.find((i) => i.id === ideaId);
    if (!idea) return;
    setPendingId(ideaId);
    const response = await execute({
      type: 'createContent',
      pageId: idea.pageId,
      title: idea.title,
      family: idea.family,
      ideaId,
    });
    setPendingId('');
    setResult(response);
    if (response.ok && response.entityId) navigate('content', response.entityId, 'brief');
  }
  return (
    <div className="support-workspace stack">
      <div className="support-summary-row">
        <div>
          <span className="eyebrow">From signal to story</span>
          <h2>Ideas with a reason to exist.</h2>
          <p className="muted">
            Review the evidence, page fit and freshness before committing to a brief.
          </p>
        </div>
        <div className="support-mini-stat">
          <strong>{state.ideas.filter((i) => i.status === 'suggested').length}</strong>
          <span>to consider</span>
          <button
            className="button primary"
            disabled={!canEdit(state.role)}
            onClick={() => setCreating(true)}
          >
            New idea
          </button>
        </div>
      </div>
      {creating && (
        <NewIdeaForm
          state={state}
          execute={execute}
          close={() => {
            setCreating(false);
            setStatus('suggested');
            setPageFilter('all');
            setQuery('');
          }}
        />
      )}
      <div className="panel support-toolbar">
        <Field label="Search ideas">
          <input
            type="search"
            placeholder="Search topics or ideas…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </Field>
        <Field label="Filter by page">
          <select value={pageFilter} onChange={(e) => setPageFilter(e.target.value)}>
            <option value="all">All pages</option>
            {state.pages.map((page) => (
              <option key={page.id} value={page.id}>
                {page.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Idea status">
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="suggested">Suggested</option>
            <option value="held">On hold</option>
            <option value="drafted">Brief created</option>
            <option value="rejected">Rejected</option>
            <option value="all">All statuses</option>
          </select>
        </Field>
      </div>
      <PermissionNote allowed={editable} action="make editorial decisions" />
      <Feedback result={result} />
      <div className="support-idea-grid">
        {ideas.map((idea, index) => (
          <article className="panel support-idea-card" key={idea.id}>
            <div className={`support-idea-art support-idea-art-${idea.family}`} aria-hidden="true">
              <span className="support-idea-number">{String(index + 1).padStart(2, '0')}</span>
              <span className="support-idea-symbol">
                {idea.family === 'product' ? '◒' : idea.family === 'video' ? '▶' : '✳'}
              </span>
              <span className="support-idea-family">{human(idea.family)} story</span>
            </div>
            <div className="support-card-body">
              <div className="row">
                <span className="eyebrow">
                  {state.pages.find((p) => p.id === idea.pageId)?.name ?? 'Unassigned page'}
                </span>
                <span className={`badge support-status-${idea.freshness}`}>
                  {idea.freshness === 'fresh'
                    ? 'Current signal'
                    : idea.freshness === 'expiring'
                      ? 'Window closing'
                      : 'Evidence expired'}
                </span>
              </div>
              <h3>{idea.title}</h3>
              <p>{idea.summary}</p>
              <div className="support-evidence">
                <span className="support-detail-label">Why now · illustrative evidence</span>
                <p>{idea.evidence}</p>
              </div>
              <p className="support-fit">
                <strong>Page fit</strong> {idea.fit}
              </p>
              {idea.freshness === 'expired' && (
                <p className="support-warning">
                  Refresh the evidence before creating a brief. This opportunity is blocked.
                </p>
              )}
              <div className="support-card-actions">
                <button
                  className="button primary"
                  disabled={
                    !editable ||
                    pendingId === idea.id ||
                    idea.freshness === 'expired' ||
                    idea.status === 'drafted'
                  }
                  onClick={() => void createBrief(idea.id)}
                >
                  {pendingId === idea.id
                    ? 'Working…'
                    : idea.status === 'drafted'
                      ? 'Brief created'
                      : 'Create brief'}
                </button>
                {idea.status === 'held' || idea.status === 'rejected' ? (
                  <button
                    className="button ghost"
                    disabled={!editable || pendingId === idea.id}
                    onClick={() => void decide(idea.id, 'suggested')}
                  >
                    Reconsider
                  </button>
                ) : (
                  <>
                    <button
                      className="button ghost"
                      disabled={!editable || pendingId === idea.id || idea.status === 'drafted'}
                      onClick={() => void decide(idea.id, 'held')}
                    >
                      Hold
                    </button>
                    <button
                      className="button ghost"
                      disabled={!editable || pendingId === idea.id || idea.status === 'drafted'}
                      onClick={() => void decide(idea.id, 'rejected')}
                    >
                      Reject
                    </button>
                  </>
                )}
              </div>
            </div>
          </article>
        ))}
      </div>
      {!ideas.length && (
        <div className="panel empty-state support-empty">
          <span className="support-empty-icon" aria-hidden="true">
            ✳
          </span>
          <h3>
            {state.ideas.length
              ? 'No ideas match these filters'
              : 'Your next idea has room to grow'}
          </h3>
          <p className="muted">
            {state.ideas.length
              ? 'Try another page or include all statuses.'
              : 'Start with a page and its audience. You can create content directly from approved library assets.'}
          </p>
          <button
            className="button secondary"
            onClick={() => {
              if (state.ideas.length) {
                setQuery('');
                setPageFilter('all');
                setStatus('all');
              } else navigate(state.pages.length ? 'assets' : 'pages');
            }}
          >
            {state.ideas.length
              ? 'Clear filters'
              : state.pages.length
                ? 'Explore the Asset Registry'
                : 'Set up a page'}
          </button>
        </div>
      )}
    </div>
  );
}

function AssetPreview({
  representation,
  name,
  large = false,
}: {
  representation?: Representation;
  name: string;
  large?: boolean;
}) {
  if (!representation || !representation.src)
    return (
      <div className="support-media-placeholder">
        <span aria-hidden="true">◇</span>
        <span>Preview unavailable</span>
      </div>
    );
  if (representation.mediaType === 'audio')
    return (
      <div className="support-audio-preview">
        <div className="support-waveform" aria-hidden="true">
          ▂ ▅ ▃ █ ▆ ▂ ▄ ▇ ▃ ▅ ▂ █ ▃ ▅ ▂
        </div>
        {large ? (
          <audio controls src={representation.src} aria-label={`${name} preview`} />
        ) : (
          <span>{name}</span>
        )}
      </div>
    );
  if (representation.mediaType === 'video')
    return large ? (
      <video controls preload="metadata" src={representation.src} aria-label={`${name} preview`} />
    ) : (
      <div className="support-video-thumb">
        <video preload="metadata" muted src={representation.src} />
        <span aria-hidden="true">▶</span>
      </div>
    );
  if (representation.mediaType === 'text')
    return (
      <div className="support-media-placeholder">
        <span aria-hidden="true">Aa</span>
        <span>Text representation</span>
      </div>
    );
  // Local prototype assets are intentionally shown without a remote image optimisation dependency.
  // eslint-disable-next-line @next/next/no-img-element
  return <img src={representation.src} alt={name} loading="lazy" />;
}

function AssetDetail({
  asset,
  state,
  execute,
  close,
}: Pick<WorkspaceProps, 'state' | 'execute'> & { asset: Asset; close: () => void }) {
  const rep = representationFor(state, asset.id);
  const versions = state.assetVersions.filter((v) => v.assetId === asset.id);
  const [result, setResult] = useState<CommandResult | null>(null);
  const [pending, setPending] = useState(false);
  useEffect(() => {
    setResult(null);
  }, [asset.id]);
  async function review(eligible: boolean) {
    if (!rep) return;
    setPending(true);
    setResult(await execute({ type: 'reviewAsset', representationId: rep.id, eligible }));
    setPending(false);
  }
  return (
    <section className="panel support-asset-detail">
      <div className="section-heading">
        <div>
          <span className="eyebrow">Asset record</span>
          <h3>{asset.name}</h3>
        </div>
        <button className="button ghost" onClick={close} aria-label="Close asset detail">
          ✕
        </button>
      </div>
      <div className="support-detail-media">
        <AssetPreview representation={rep} name={asset.name} large />
      </div>
      <div className="support-detail-meta">
        <div>
          <span className="support-detail-label">Readiness</span>
          <span className={`badge support-status-${rep?.readiness}`}>
            {human(rep?.readiness ?? 'unavailable')}
          </span>
        </div>
        <div>
          <span className="support-detail-label">Rights</span>
          <span className={`badge support-status-${rep?.rights}`}>
            {human(rep?.rights ?? 'not evaluated')}
          </span>
        </div>
        <div>
          <span className="support-detail-label">Used in content</span>
          <strong>
            {asset.usageCount} {asset.usageCount === 1 ? 'time' : 'times'}
          </strong>
        </div>
        <div>
          <span className="support-detail-label">Acquisition</span>
          <strong>{human(asset.origin)}</strong>
        </div>
      </div>
      <div className="support-evidence">
        <span className="support-detail-label">Rights and source record</span>
        <p>{rep?.rightsNote || 'No rights evidence has been captured.'}</p>
      </div>
      <div>
        <span className="support-detail-label">Eligible capabilities</span>
        <div className="support-tags">
          {rep?.capabilities.length ? (
            rep.capabilities.map((cap) => (
              <span className="support-tag" key={cap}>
                {human(cap)}
              </span>
            ))
          ) : (
            <span className="muted">No capabilities evaluated yet.</span>
          )}
        </div>
      </div>
      <div className="support-representation">
        <div className="row">
          <strong>Current representation</strong>
          <span className="badge">{rep?.mediaType ?? 'Unavailable'}</span>
        </div>
        <p className="muted">
          {rep && rep.width > 0
            ? `${rep.width} × ${rep.height} pixels`
            : rep?.mediaType === 'audio'
              ? 'Audio preview'
              : 'Dimensions unavailable'}
          {rep?.durationFrames ? ` · ${rep.durationFrames} source frames` : ''}
        </p>
        {rep?.derivedFromId && (
          <p className="muted">
            Derived from{' '}
            {state.representations.find((r) => r.id === rep.derivedFromId)?.id ?? rep.derivedFromId}
          </p>
        )}
      </div>
      <div>
        <span className="support-detail-label">Version history and lineage</span>
        <ol className="support-version-list">
          {versions.map((version) => (
            <li key={version.id}>
              <span className="support-version-dot">{version.number}</span>
              <div>
                <strong>
                  Version {version.number}
                  {version.id === asset.currentVersionId ? ' · current' : ''}
                </strong>
                <p>{version.description}</p>
                {version.parentId && (
                  <small className="muted">
                    Derived from version{' '}
                    {state.assetVersions.find((v) => v.id === version.parentId)?.number ??
                      version.parentId}
                  </small>
                )}
              </div>
            </li>
          ))}
        </ol>
      </div>
      {rep?.rights === 'review_required' && (
        <div className="support-policy-box">
          <strong>Rights review required</strong>
          <p className="muted">
            Review the source record. This simulated decision changes eligibility within the
            prototype.
          </p>
          <PermissionNote allowed={canReview(state.role)} action="review asset rights" />
          <div className="support-card-actions">
            <button
              className="button primary"
              disabled={!canReview(state.role) || pending}
              onClick={() => void review(true)}
            >
              Mark eligible
            </button>
            <button
              className="button secondary"
              disabled={!canReview(state.role) || pending}
              onClick={() => void review(false)}
            >
              Restrict use
            </button>
          </div>
        </div>
      )}
      <Feedback result={result} />
      <details className="support-diagnostics">
        <summary>Technical references</summary>
        <p>Asset: {asset.id}</p>
        <p>Version: {asset.currentVersionId}</p>
        <p>Representation: {rep?.id ?? 'Unavailable'}</p>
      </details>
    </section>
  );
}

function RegisterAssetForm({
  execute,
  close,
}: Pick<WorkspaceProps, 'execute'> & { close: () => void }) {
  const [name, setName] = useState('');
  const [kind, setKind] = useState<AssetKind>('product');
  const [mediaType, setMediaType] = useState<Representation['mediaType']>('image');
  const [rights, setRights] = useState('');
  const [pending, setPending] = useState(false);
  const [result, setResult] = useState<CommandResult | null>(null);
  async function submit(event: FormEvent) {
    event.preventDefault();
    setPending(true);
    const response = await execute({
      type: 'registerAsset',
      name,
      kind,
      mediaType,
      rightsNote: rights,
    });
    setResult(response);
    setPending(false);
    if (response.ok) {
      setName('');
      setRights('');
    }
  }
  return (
    <section className="panel support-registration">
      <div className="section-heading">
        <div>
          <span className="eyebrow">Simulated intake</span>
          <h3>Register an asset</h3>
        </div>
        <button className="button ghost" onClick={close} aria-label="Close asset registration">
          ✕
        </button>
      </div>
      <p className="muted">
        Create a sample registry record to try intake and rights review. A local sample represents
        the file; no media is uploaded or generated.
      </p>
      <form className="stack" onSubmit={(e) => void submit(e)}>
        <div className="form-grid">
          <Field label="Asset name">
            <input
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Ceramic mug · side view"
            />
          </Field>
          <Field label="Asset kind">
            <select value={kind} onChange={(e) => setKind(e.target.value as AssetKind)}>
              {(['product', 'environment', 'footage', 'music', 'voice', 'graphic'] as const).map(
                (value) => (
                  <option key={value} value={value}>
                    {human(value)}
                  </option>
                ),
              )}
            </select>
          </Field>
          <Field label="Representation type">
            <select
              value={mediaType}
              onChange={(e) => setMediaType(e.target.value as Representation['mediaType'])}
            >
              <option value="image">Image</option>
              <option value="video">Video</option>
              <option value="audio">Audio</option>
              <option value="text">Text</option>
            </select>
          </Field>
          <Field label="Source and rights evidence">
            <input
              required
              value={rights}
              onChange={(e) => setRights(e.target.value)}
              placeholder="Owned photograph, captured 9 September…"
            />
          </Field>
        </div>
        <div className="row">
          <span className="muted">New assets enter review before they can be selected.</span>
          <button className="button primary" disabled={pending} type="submit">
            {pending ? 'Registering…' : 'Register sample asset'}
          </button>
        </div>
        <Feedback result={result} />
      </form>
    </section>
  );
}

export function AssetsWorkspace({ state, execute, navigate }: WorkspaceProps) {
  const editable = canEdit(state.role);
  const [query, setQuery] = useState('');
  const [kind, setKind] = useState('all');
  const [readiness, setReadiness] = useState('all');
  const [activeId, setActiveId] = useState('');
  const [selected, setSelected] = useState<string[]>([]);
  const [registering, setRegistering] = useState(false);
  const [pageId, setPageId] = useFirstPage(state);
  const [result, setResult] = useState<CommandResult | null>(null);
  const [pending, setPending] = useState(false);
  const eligible = (asset: Asset) => {
    const rep = representationFor(state, asset.id);
    return rep?.readiness === 'ready' && rep.rights === 'eligible';
  };
  const assets = state.assets.filter(
    (asset) =>
      `${asset.name} ${asset.tags.join(' ')}`.toLowerCase().includes(query.toLowerCase()) &&
      (kind === 'all' || asset.kind === kind) &&
      (readiness === 'all' || (readiness === 'eligible' ? eligible(asset) : !eligible(asset))),
  );
  const active = state.assets.find((asset) => asset.id === activeId);
  const selectedEligible = selected.filter((id) => {
    const asset = state.assets.find((a) => a.id === id);
    return asset && eligible(asset);
  });
  async function create() {
    setPending(true);
    const response = await execute({ type: 'createContent', pageId, assetIds: selectedEligible });
    setResult(response);
    setPending(false);
    if (response.ok && response.entityId) navigate('content', response.entityId, 'brief');
  }
  return (
    <div className="support-workspace stack">
      <div className="support-summary-row">
        <div>
          <span className="eyebrow">Reusable by design</span>
          <h2>Your production library.</h2>
          <p className="muted">
            Find the right representation, understand its rights and carry its history into every
            story.
          </p>
        </div>
        <button
          className="button primary"
          disabled={!editable}
          onClick={() => setRegistering((value) => !value)}
        >
          ＋ Register asset
        </button>
      </div>
      <div className="support-library-stats">
        <Count value={state.assets.length} label="Registered assets" />
        <Count value={state.assets.filter(eligible).length} label="Ready and eligible" />
        <Count
          value={state.assets.filter((asset) => !eligible(asset)).length}
          label="Need attention"
        />
      </div>
      <PermissionNote allowed={editable} action="register assets or start content" />
      {registering && editable && (
        <RegisterAssetForm execute={execute} close={() => setRegistering(false)} />
      )}
      <div className="panel support-toolbar">
        <Field label="Search the Asset Registry">
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search assets or tags…"
          />
        </Field>
        <Field label="Asset type">
          <select value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="all">All types</option>
            {['product', 'environment', 'footage', 'music', 'voice', 'graphic'].map((value) => (
              <option key={value} value={value}>
                {human(value)}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Eligibility">
          <select value={readiness} onChange={(e) => setReadiness(e.target.value)}>
            <option value="all">All assets</option>
            <option value="eligible">Ready and eligible</option>
            <option value="attention">Need attention</option>
          </select>
        </Field>
      </div>
      <Feedback result={result} />
      <div className={active ? 'support-registry-layout' : ''}>
        <div className="support-asset-grid">
          {assets.map((asset) => {
            const rep = representationFor(state, asset.id);
            const isEligible = eligible(asset);
            return (
              <article
                key={asset.id}
                className={`panel support-asset-card ${selected.includes(asset.id) ? 'support-selected' : ''}`}
              >
                <div className="support-asset-image">
                  <button
                    className="support-open-asset"
                    onClick={() => setActiveId(asset.id)}
                    aria-label={`Inspect ${asset.name}`}
                  >
                    <AssetPreview representation={rep} name={asset.name} />
                  </button>
                  <label
                    className="support-asset-check"
                    title={
                      isEligible
                        ? 'Select for new content'
                        : 'Only ready assets with eligible rights can be selected'
                    }
                  >
                    <input
                      aria-label={`Select ${asset.name} for content`}
                      type="checkbox"
                      checked={selected.includes(asset.id)}
                      disabled={!editable || !isEligible}
                      onChange={(e) =>
                        setSelected((current) =>
                          e.target.checked
                            ? [...current, asset.id]
                            : current.filter((id) => id !== asset.id),
                        )
                      }
                    />
                  </label>
                  <span className="support-media-type">{human(asset.kind)}</span>
                </div>
                <div className="support-card-body">
                  <button className="support-title-button" onClick={() => setActiveId(asset.id)}>
                    {asset.name}
                  </button>
                  <p className="support-asset-meta">
                    Version{' '}
                    {state.assetVersions.find((v) => v.id === asset.currentVersionId)?.number ??
                      '?'}{' '}
                    <span aria-hidden="true">·</span> Used {asset.usageCount} times
                  </p>
                  <div className="support-tags">
                    <span
                      className={`badge ${isEligible ? 'support-status-ready' : 'support-status-review_required'}`}
                    >
                      {isEligible
                        ? 'Ready to use'
                        : rep?.rights === 'eligible'
                          ? human(rep.readiness)
                          : human(rep?.rights ?? 'unavailable')}
                    </span>
                    {asset.tags.slice(0, 2).map((tag) => (
                      <span className="support-tag" key={tag}>
                        {tag}
                      </span>
                    ))}
                  </div>
                </div>
              </article>
            );
          })}
          {!assets.length && (
            <div className="panel empty-state support-empty">
              <h3>
                {state.assets.length
                  ? 'No assets match your search'
                  : 'A library waiting to be built'}
              </h3>
              <p className="muted">
                {state.assets.length
                  ? 'Try another asset type or eligibility filter.'
                  : 'Register a sample asset or plan a pack around your next story.'}
              </p>
              <button
                className="button secondary"
                onClick={() => {
                  if (state.assets.length) {
                    setQuery('');
                    setKind('all');
                    setReadiness('all');
                  } else navigate('packs');
                }}
              >
                {state.assets.length ? 'Clear filters' : 'Plan an asset pack'}
              </button>
            </div>
          )}
        </div>
        {active && (
          <AssetDetail
            asset={active}
            state={state}
            execute={execute}
            close={() => setActiveId('')}
          />
        )}
      </div>
      {selected.length > 0 && (
        <div className="panel support-selection-tray">
          <div>
            <span className="eyebrow">Selected ingredients</span>
            <strong>
              {selectedEligible.length} ready {selectedEligible.length === 1 ? 'asset' : 'assets'}
            </strong>
            <small className="muted">
              Mark essential objects as mandatory in the content editor.
            </small>
          </div>
          <PageSelect state={state} value={pageId} onChange={setPageId} label="Create for page" />
          <button className="button ghost" onClick={() => setSelected([])}>
            Clear
          </button>
          <button
            className="button primary"
            disabled={!editable || !pageId || !selectedEligible.length || pending}
            onClick={() => void create()}
          >
            {pending ? 'Creating…' : 'Create from selected assets'}
          </button>
        </div>
      )}
    </div>
  );
}

function PackDetail({ pack, state, execute, navigate }: WorkspaceProps & { pack: AssetPack }) {
  const editable = canEdit(state.role);
  const [result, setResult] = useState<CommandResult | null>(null);
  const [pending, setPending] = useState('');
  useEffect(() => setResult(null), [pack.id]);
  const ready = pack.items.filter(
    (item) =>
      item.status === 'ready' &&
      item.assetId &&
      representationFor(state, item.assetId)?.readiness === 'ready' &&
      representationFor(state, item.assetId)?.rights === 'eligible',
  );
  const total = pack.items.reduce((sum, item) => sum + item.cost.minor, 0);
  async function act(type: 'authorizePack' | 'fulfillPack' | 'retryPackItem', itemId?: string) {
    setPending(itemId ?? type);
    setResult(
      await execute(
        type === 'retryPackItem'
          ? { type, packId: pack.id, itemId: itemId! }
          : { type, packId: pack.id },
      ),
    );
    setPending('');
  }
  async function createFromPack() {
    setPending('create');
    const response = await execute({
      type: 'createContent',
      pageId: pack.pageId,
      packId: pack.id,
      assetIds: ready.map((i) => i.assetId!),
    });
    setResult(response);
    setPending('');
    if (response.ok && response.entityId) navigate('content', response.entityId, 'brief');
  }
  return (
    <section className="panel support-pack-detail">
      <div className="section-heading">
        <div>
          <span className="eyebrow">
            {state.pages.find((p) => p.id === pack.pageId)?.name ?? 'Page'} · Asset pack
          </span>
          <h3>{pack.name}</h3>
          <p className="muted">
            {pack.style} · {pack.mix}
          </p>
        </div>
        <span className={`badge support-status-${pack.status}`}>{human(pack.status)}</span>
      </div>
      <div className="support-pack-progress">
        <div className="row">
          <strong>
            {ready.length} of {pack.requestedCount} requested assets usable
          </strong>
          <span>{Math.round((ready.length / Math.max(1, pack.requestedCount)) * 100)}%</span>
        </div>
        <progress
          max={pack.requestedCount}
          value={ready.length}
          aria-label="Usable asset pack fulfilment"
        />
      </div>
      <div className="support-pack-costs">
        <Count value={money(total)} label="Planned acquisition" />
        <Count value={money(pack.budget)} label="Authorisation ceiling" />
        <Count
          value={pack.items.filter((i) => i.route === 'reuse').length}
          label="Reuse opportunities"
        />
      </div>
      {pack.status === 'partial' && (
        <div className="notice support-warning">
          <strong>A useful partial pack.</strong> Some items are unavailable. Use the eligible
          subset for a supported composition, or repair the gaps below. Missing objects are never
          silently included.
        </div>
      )}
      {total > pack.budget.minor && (
        <div className="notice support-error">
          The planned scope exceeds this pack’s budget. Plan a smaller pack before authorising
          acquisition.
        </div>
      )}
      <div className="support-pack-items">
        {pack.items.map((item) => (
          <article className="support-pack-item" key={item.id}>
            <div className={`support-item-icon support-item-${item.kind}`} aria-hidden="true">
              {item.kind === 'music' || item.kind === 'voice'
                ? '♫'
                : item.kind === 'footage'
                  ? '▶'
                  : item.kind === 'environment'
                    ? '◫'
                    : '◇'}
            </div>
            <div className="support-pack-item-copy">
              <div className="row">
                <strong>{item.name}</strong>
                <span className={`badge support-status-${item.status}`}>{human(item.status)}</span>
              </div>
              <p>{item.reason}</p>
              <div className="support-tags">
                <span className="support-tag">{human(item.route)}</span>
                <span className="muted">{money(item.cost)} estimated</span>
              </div>
              {item.error && <p className="support-error-text">{item.error}</p>}
              {(item.status === 'failed' || item.status === 'missing') && (
                <button
                  className="button secondary support-small-button"
                  disabled={!editable || !!pending || pack.status === 'planned'}
                  onClick={() => void act('retryPackItem', item.id)}
                >
                  {pending === item.id ? 'Retrying…' : `Retry acquisition · ${money(item.cost)}`}
                </button>
              )}
            </div>
          </article>
        ))}
      </div>
      <PermissionNote allowed={editable} action="authorise or fulfil the acquisition scope" />
      <div className="support-pack-footer">
        <div className="support-card-actions">
          {pack.status === 'planned' ? (
            <button
              className="button primary"
              disabled={!editable || !!pending || total > pack.budget.minor}
              onClick={() => void act('authorizePack')}
            >
              {pending === 'authorizePack'
                ? 'Authorising…'
                : `Authorise acquisition · ${money(total)}`}
            </button>
          ) : pack.status === 'authorised' ? (
            <button
              className="button primary"
              disabled={!editable || !!pending}
              onClick={() => void act('fulfillPack')}
            >
              {pending === 'fulfillPack' ? 'Starting fulfilment…' : 'Fulfil authorised pack'}
            </button>
          ) : (
            <button
              className="button secondary"
              disabled={!editable || !!pending || pack.items.every((i) => i.status === 'ready')}
              onClick={() => void act('fulfillPack')}
            >
              Fulfil remaining scope
            </button>
          )}
          <button
            className="button secondary"
            disabled={!editable || !!pending || !ready.length}
            onClick={() => void createFromPack()}
          >
            {pending === 'create' ? 'Creating…' : `Create from ${ready.length} ready assets`}
          </button>
        </div>
        <p className="muted">
          Authorisation, acquisition and content creation are separate decisions. All provider
          activity and costs are simulated.
        </p>
      </div>
      <Feedback result={result} />
    </section>
  );
}

export function PacksWorkspace({ state, execute, navigate }: WorkspaceProps) {
  const editable = canEdit(state.role);
  const [pageId, setPageId] = useFirstPage(state);
  const [name, setName] = useState('The everyday ritual');
  const [count, setCount] = useState(5);
  const [mix, setMix] = useState('2 product, 2 environment, 1 music');
  const [style, setStyle] = useState('Warm, tactile, natural light');
  const [budget, setBudget] = useState(12);
  const [activeId, setActiveId] = useState(state.packs[0]?.id ?? '');
  const [result, setResult] = useState<CommandResult | null>(null);
  const [pending, setPending] = useState(false);
  const active = state.packs.find((pack) => pack.id === activeId) ?? state.packs[0];
  async function plan(event: FormEvent) {
    event.preventDefault();
    setPending(true);
    const response = await execute({
      type: 'planPack',
      name,
      pageId,
      count,
      mix,
      style,
      budgetMinor: Math.round(budget * 100),
    });
    setResult(response);
    setPending(false);
    if (response.ok && response.entityId) setActiveId(response.entityId);
  }
  return (
    <div className="support-workspace stack">
      <div className="support-summary-row">
        <div>
          <span className="eyebrow">Make the missing pieces</span>
          <h2>Plan a pack. Keep it useful.</h2>
          <p className="muted">
            Reuse what works, see the gaps and approve a clear acquisition scope.
          </p>
        </div>
        <div className="support-mini-stat">
          <strong>{state.packs.length}</strong>
          <span>saved packs</span>
        </div>
      </div>
      <div className="support-pack-layout">
        <div className="stack">
          <section className="panel support-pack-form">
            <div className="section-heading">
              <div>
                <span className="eyebrow">01 · Define the scope</span>
                <h3>Plan a new asset pack</h3>
              </div>
            </div>
            <form className="stack" onSubmit={(e) => void plan(e)}>
              <fieldset className="support-fieldset stack" disabled={!editable || pending}>
                <Field label="Pack name">
                  <input
                    required
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="The everyday ritual"
                  />
                </Field>
                <PageSelect state={state} value={pageId} onChange={setPageId} />
                <div className="form-grid">
                  <Field label="Requested asset count">
                    <input
                      type="number"
                      min="1"
                      max="20"
                      required
                      value={count}
                      onChange={(e) => setCount(Number(e.target.value))}
                    />
                  </Field>
                  <Field label="Budget ceiling (£)">
                    <input
                      type="number"
                      min="0.01"
                      max="1000"
                      step="0.01"
                      required
                      value={budget}
                      onChange={(e) => setBudget(Number(e.target.value))}
                    />
                  </Field>
                </div>
                <Field label="Asset mix" hint="Describe the kinds and quantities you need.">
                  <input required value={mix} onChange={(e) => setMix(e.target.value)} />
                </Field>
                <Field label="Visual style and purpose">
                  <textarea
                    rows={3}
                    required
                    value={style}
                    onChange={(e) => setStyle(e.target.value)}
                  />
                </Field>
                <div className="support-evidence">
                  <span className="support-detail-label">Acquisition order</span>
                  <p>
                    Eligible reuse → suitable transformation → supplied media → new generation. Each
                    proposed item explains its route.
                  </p>
                </div>
                <button className="button primary" type="submit" disabled={!pageId}>
                  {pending ? 'Planning pack…' : 'Plan pack · no acquisition yet'}
                </button>
              </fieldset>
              <PermissionNote allowed={editable} action="plan an asset pack" />
              {!state.pages.length && (
                <button
                  type="button"
                  className="button secondary"
                  onClick={() => navigate('pages')}
                >
                  Create a page first
                </button>
              )}
              <Feedback result={result} />
            </form>
          </section>
          <section className="panel support-saved-packs">
            <span className="eyebrow">Saved packs</span>
            {state.packs.length ? (
              state.packs.map((pack) => (
                <button
                  className={`support-saved-pack ${active?.id === pack.id ? 'support-active' : ''}`}
                  key={pack.id}
                  onClick={() => setActiveId(pack.id)}
                >
                  <span>
                    <strong>{pack.name}</strong>
                    <small>
                      {pack.items.filter((item) => item.status === 'ready').length}/
                      {pack.requestedCount} ready · {human(pack.status)}
                    </small>
                  </span>
                  <span aria-hidden="true">↗</span>
                </button>
              ))
            ) : (
              <p className="muted">Your first plan will appear here.</p>
            )}
          </section>
        </div>
        {active ? (
          <PackDetail pack={active} state={state} execute={execute} navigate={navigate} />
        ) : (
          <div className="panel empty-state support-empty">
            <span className="support-empty-icon" aria-hidden="true">
              ◈
            </span>
            <h3>See the plan before the spend</h3>
            <p className="muted">
              Define a pack to review proposed items, acquisition routes, estimated costs and
              reusable assets here.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

function ExperimentForm({
  state,
  execute,
  close,
}: Pick<WorkspaceProps, 'state' | 'execute'> & { close: () => void }) {
  const [name, setName] = useState('');
  const [pageId, setPageId] = useFirstPage(state);
  const [contentIds, setContentIds] = useState<string[]>([]);
  const [metric, setMetric] = useState('3-second retention');
  const [days, setDays] = useState(7);
  const [rule, setRule] = useState(
    'Observe all variants for 7 days; do not declare a winner before each reaches 1,000 views.',
  );
  const [result, setResult] = useState<CommandResult | null>(null);
  const [pending, setPending] = useState(false);
  const pageContents = state.contents.filter((content) => content.pageId === pageId);
  async function submit(event: FormEvent) {
    event.preventDefault();
    setPending(true);
    const response = await execute({
      type: 'createExperiment',
      name,
      contentIds,
      metric,
      windowDays: days,
      stoppingRule: rule,
    });
    setResult(response);
    setPending(false);
    if (response.ok) {
      setName('');
      setContentIds([]);
    }
  }
  return (
    <section className="panel support-experiment-form">
      <div className="section-heading">
        <div>
          <span className="eyebrow">Predeclare your test</span>
          <h3>New experiment</h3>
        </div>
        <button className="button ghost" onClick={close} aria-label="Close experiment form">
          ✕
        </button>
      </div>
      <form className="stack" onSubmit={(e) => void submit(e)}>
        <Field label="Experiment name">
          <input
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Does showing the result first improve retention?"
          />
        </Field>
        <div className="form-grid">
          <Field label="Primary metric">
            <select value={metric} onChange={(e) => setMetric(e.target.value)}>
              <option>3-second retention</option>
              <option>Completion rate</option>
              <option>Views</option>
              <option>Saves per 1,000 views</option>
            </select>
          </Field>
          <Field label="Observation window (days)">
            <input
              type="number"
              min="1"
              max="90"
              required
              value={days}
              onChange={(e) => setDays(Number(e.target.value))}
            />
          </Field>
        </div>
        <PageSelect
          state={state}
          value={pageId}
          onChange={(id) => {
            setPageId(id);
            setContentIds([]);
          }}
          label="Experiment page"
        />
        <fieldset className="support-content-options">
          <legend>Content variants to compare</legend>
          {pageContents.map((content) => (
            <label className="support-checkbox" key={content.id}>
              <input
                type="checkbox"
                checked={contentIds.includes(content.id)}
                onChange={(e) =>
                  setContentIds((current) =>
                    e.target.checked
                      ? [...current, content.id]
                      : current.filter((id) => id !== content.id),
                  )
                }
              />
              <span>
                {content.draft.title}
                <small className="muted">
                  {state.pages.find((p) => p.id === content.pageId)?.name} · {human(content.stage)}
                </small>
              </span>
            </label>
          ))}
          {!pageContents.length && (
            <p className="muted">
              This page has no content yet. Create at least two variants to compare.
            </p>
          )}
        </fieldset>
        <Field label="Stopping rule and minimum evidence">
          <textarea required rows={3} value={rule} onChange={(e) => setRule(e.target.value)} />
        </Field>
        <p className="muted">
          Select at least two variants from the same page. Declare the decision rule before
          observing results. These experiments illustrate a workflow; they do not establish causal
          evidence.
        </p>
        <button
          className="button primary"
          disabled={pending || contentIds.length < 2}
          type="submit"
        >
          {pending ? 'Saving experiment…' : 'Create experiment'}
        </button>
        <Feedback result={result} />
      </form>
    </section>
  );
}

function MetricsForm({ state, execute }: Pick<WorkspaceProps, 'state' | 'execute'>) {
  const publications = state.publications.filter((p) => p.status === 'published');
  const [publicationId, setPublicationId] = useState(publications[0]?.id ?? '');
  const [views, setViews] = useState('');
  const [retention, setRetention] = useState('');
  const [pending, setPending] = useState(false);
  const [result, setResult] = useState<CommandResult | null>(null);
  useEffect(() => {
    const published = state.publications.filter((p) => p.status === 'published');
    if (!published.some((p) => p.id === publicationId)) setPublicationId(published[0]?.id ?? '');
  }, [state.publications, publicationId]);
  async function submit(event: FormEvent) {
    event.preventDefault();
    setPending(true);
    setResult(
      await execute({
        type: 'recordMetrics',
        publicationId,
        views: Number(views),
        retention: retention === '' ? null : Number(retention),
      }),
    );
    setPending(false);
  }
  return (
    <section className="panel support-metrics-form">
      <div className="section-heading">
        <div>
          <span className="eyebrow">Manual observation</span>
          <h3>Record sample metrics</h3>
        </div>
        <span className="badge">Simulated publication</span>
      </div>
      {publications.length ? (
        <form className="stack" onSubmit={(e) => void submit(e)}>
          <fieldset className="support-fieldset stack" disabled={!canEdit(state.role) || pending}>
            <Field label="Published content">
              <select
                required
                value={publicationId}
                onChange={(e) => setPublicationId(e.target.value)}
              >
                {publications.map((p) => (
                  <option key={p.id} value={p.id}>
                    {state.contents.find((c) => c.id === p.contentId)?.draft.title ??
                      p.externalReference ??
                      p.id}
                  </option>
                ))}
              </select>
            </Field>
            <div className="form-grid">
              <Field label="Views" hint="Enter 0 only if zero views were observed.">
                <input
                  required
                  type="number"
                  min="0"
                  step="1"
                  value={views}
                  onChange={(e) => setViews(e.target.value)}
                  placeholder="e.g. 1240"
                />
              </Field>
              <Field label="Retention (%)" hint="Leave blank when unavailable.">
                <input
                  type="number"
                  min="0"
                  max="100"
                  step="0.1"
                  value={retention}
                  onChange={(e) => setRetention(e.target.value)}
                  placeholder="Unavailable"
                />
              </Field>
            </div>
            <button className="button primary" type="submit">
              {pending ? 'Recording…' : 'Record sample observation'}
            </button>
          </fieldset>
          <PermissionNote allowed={canEdit(state.role)} action="record metrics" />
          <Feedback result={result} />
        </form>
      ) : (
        <div className="support-inline-empty">
          <p>No confirmed manual posts yet.</p>
          <p className="muted">
            Approve a package, prepare publication and record a sample post reference to attach
            metrics.
          </p>
        </div>
      )}
    </section>
  );
}

export function LearningWorkspace({ state, execute, navigate }: WorkspaceProps) {
  const [tab, setTab] = useState<'outcomes' | 'experiments' | 'suggestions'>('outcomes');
  const [creating, setCreating] = useState(false);
  const [result, setResult] = useState<CommandResult | null>(null);
  const [pendingId, setPendingId] = useState('');
  const editable = canEdit(state.role);
  async function reviewSuggestion(suggestionId: string, decision: 'accepted' | 'dismissed') {
    setPendingId(suggestionId);
    setResult(await execute({ type: 'reviewSuggestion', suggestionId, decision }));
    setPendingId('');
  }
  return (
    <div className="support-workspace stack">
      <div className="support-summary-row">
        <div>
          <span className="eyebrow">Curiosity, with evidence</span>
          <h2>Learn what deserves another try.</h2>
          <p className="muted">
            Keep observations, confidence and decisions separate. Every number here is illustrative.
          </p>
        </div>
        <button
          className="button primary"
          disabled={!editable}
          onClick={() => {
            setCreating(true);
            setTab('experiments');
          }}
        >
          ＋ New experiment
        </button>
      </div>
      <div className="support-learning-stats">
        <Count
          value={state.publications.filter((p) => p.status === 'published').length}
          label="Simulated posts"
        />
        <Count
          value={state.metrics.filter((m) => m.maturity === 'mature').length}
          label="Mature observation windows"
        />
        <Count value={state.experiments.length} label="Experiments" />
        <Count
          value={state.suggestions.filter((s) => s.status === 'proposed').length}
          label="Policy proposals"
        />
      </div>
      <div className="support-tabs" role="tablist" aria-label="Learning workspaces">
        {(['outcomes', 'experiments', 'suggestions'] as const).map((value) => (
          <button
            key={value}
            role="tab"
            aria-selected={tab === value}
            className={tab === value ? 'support-active' : ''}
            onClick={() => setTab(value)}
          >
            {value === 'outcomes'
              ? 'Observed outcomes'
              : value === 'experiments'
                ? 'Experiments'
                : 'Learning proposals'}
          </button>
        ))}
      </div>
      <Feedback result={result} />
      {tab === 'outcomes' && (
        <div className="stack">
          <section className="panel support-outcomes">
            <div className="section-heading">
              <div>
                <h3>Performance observations</h3>
                <p className="muted">
                  Unavailable values stay unavailable. Early results stay provisional.
                </p>
              </div>
              <span className="badge">Fixture data</span>
            </div>
            {state.metrics.length ? (
              <div className="support-table-wrap">
                <table className="support-table">
                  <thead>
                    <tr>
                      <th>Content / source</th>
                      <th>Views</th>
                      <th>Retention</th>
                      <th>Observation window</th>
                      <th>Confidence</th>
                    </tr>
                  </thead>
                  <tbody>
                    {state.metrics.map((observation) => {
                      const publication = state.publications.find(
                        (p) => p.id === observation.publicationId,
                      );
                      const content = state.contents.find((c) => c.id === publication?.contentId);
                      return (
                        <tr key={observation.id}>
                          <td>
                            <button
                              className="support-title-button"
                              disabled={!content}
                              onClick={() => content && navigate('content', content.id)}
                            >
                              {content?.draft.title ?? 'Unlinked observation'}
                            </button>
                            <small>{observation.source}</small>
                          </td>
                          <td>
                            {observation.views === null ? (
                              <span className="muted">Unavailable</span>
                            ) : (
                              observation.views.toLocaleString('en-GB')
                            )}
                          </td>
                          <td>
                            {observation.retention === null ? (
                              <span className="muted">Unavailable</span>
                            ) : (
                              `${observation.retention}%`
                            )}
                          </td>
                          <td>{observation.window}</td>
                          <td>
                            <span className={`badge support-status-${observation.maturity}`}>
                              {observation.maturity === 'maturing'
                                ? 'Provisional'
                                : human(observation.maturity)}
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="support-inline-empty">
                <h3>No observations yet</h3>
                <p className="muted">
                  An absence of metrics does not mean zero performance. Record a sample manual post,
                  then add the observations you have.
                </p>
                <button className="button secondary" onClick={() => navigate('publication')}>
                  Open publication preparation
                </button>
              </div>
            )}
          </section>
          <div className="grid-2">
            <MetricsForm state={state} execute={execute} />
            <section className="panel support-fatigue">
              <span className="eyebrow">Creative fatigue</span>
              <h3>Watch repetition before changing policy.</h3>
              <p className="muted">
                Usage is a prompt for review, not proof of audience fatigue. Outcomes and an
                appropriate observation window are needed to make that judgement.
              </p>
              <div className="support-fatigue-list">
                {[...state.assets]
                  .sort((a, b) => b.usageCount - a.usageCount)
                  .slice(0, 4)
                  .map((asset) => (
                    <div key={asset.id}>
                      <div className="row">
                        <span>{asset.name}</span>
                        <strong>{asset.usageCount} uses</strong>
                      </div>
                      <progress
                        max={Math.max(1, ...state.assets.map((a) => a.usageCount))}
                        value={asset.usageCount}
                        aria-label={`${asset.name} usage count`}
                      />
                    </div>
                  ))}
              </div>
              {!state.assets.length && (
                <p className="muted">Asset use history will appear after content is created.</p>
              )}
              <button className="button ghost" onClick={() => navigate('assets')}>
                Inspect reusable assets ↗
              </button>
            </section>
          </div>
        </div>
      )}
      {tab === 'experiments' && (
        <div className="stack">
          <PermissionNote allowed={editable} action="create experiments" />
          {creating && editable && (
            <ExperimentForm state={state} execute={execute} close={() => setCreating(false)} />
          )}
          <div className="support-experiment-grid">
            {state.experiments.map((experiment) => (
              <article className="panel support-experiment-card" key={experiment.id}>
                <div className="row">
                  <span className="eyebrow">{experiment.metric}</span>
                  <span className="badge">{human(experiment.status)}</span>
                </div>
                <h3>{experiment.name}</h3>
                <div className="support-experiment-variants">
                  {experiment.contentIds.map((id) => {
                    const content = state.contents.find((c) => c.id === id);
                    return (
                      <button
                        key={id}
                        className="support-variant-link"
                        disabled={!content}
                        onClick={() => navigate('content', id)}
                      >
                        {content?.draft.title ?? 'Content unavailable'}{' '}
                        <span aria-hidden="true">↗</span>
                      </button>
                    );
                  })}
                </div>
                <div className="support-evidence">
                  <span className="support-detail-label">
                    Predeclared stopping rule · {experiment.windowDays} days
                  </span>
                  <p>{experiment.stoppingRule}</p>
                </div>
                <p className="support-experiment-conclusion">
                  <strong>Current conclusion</strong>
                  {experiment.conclusion ||
                    'No conclusion. Wait for the observation window and minimum evidence.'}
                </p>
              </article>
            ))}
          </div>
          {!state.experiments.length && !creating && (
            <div className="panel empty-state support-empty">
              <h3>Give your next test a clear question</h3>
              <p className="muted">
                Choose the variants, primary metric, observation window and stopping rule before
                interpreting results.
              </p>
              <button
                className="button primary"
                disabled={!editable}
                onClick={() => setCreating(true)}
              >
                Plan an experiment
              </button>
            </div>
          )}
        </div>
      )}
      {tab === 'suggestions' && (
        <div className="stack">
          <div className="notice support-shadow-note">
            <strong>Shadow decisions only.</strong> Accepting a proposal records your judgement in
            this prototype. It does not update production policy or trigger generation.
          </div>
          <PermissionNote
            allowed={canReview(state.role)}
            action="accept or dismiss policy proposals"
          />
          {state.suggestions.map((suggestion) => (
            <article className="panel support-suggestion" key={suggestion.id}>
              <div className="support-suggestion-icon" aria-hidden="true">
                ✳
              </div>
              <div className="support-suggestion-copy">
                <div className="row">
                  <span className="eyebrow">
                    {state.pages.find((p) => p.id === suggestion.pageId)?.name}
                  </span>
                  <span className="badge">{human(suggestion.status)}</span>
                </div>
                <h3>{suggestion.title}</h3>
                <p>{suggestion.reason}</p>
                <div className="support-evidence">
                  <span className="support-detail-label">Proposed policy change</span>
                  <p>{suggestion.change}</p>
                </div>
                <div className="support-card-actions">
                  <button
                    className="button primary"
                    disabled={
                      !canReview(state.role) ||
                      suggestion.status !== 'proposed' ||
                      pendingId === suggestion.id
                    }
                    onClick={() => void reviewSuggestion(suggestion.id, 'accepted')}
                  >
                    Accept in shadow mode
                  </button>
                  <button
                    className="button secondary"
                    disabled={
                      !canReview(state.role) ||
                      suggestion.status !== 'proposed' ||
                      pendingId === suggestion.id
                    }
                    onClick={() => void reviewSuggestion(suggestion.id, 'dismissed')}
                  >
                    Dismiss proposal
                  </button>
                </div>
              </div>
            </article>
          ))}
          {!state.suggestions.length && (
            <div className="panel empty-state support-empty">
              <h3>No learning proposals yet</h3>
              <p className="muted">
                This workspace waits for observations and review. It does not invent recommendations
                from missing data.
              </p>
              <button className="button secondary" onClick={() => setTab('outcomes')}>
                Review observations
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
