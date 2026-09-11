'use client';

import { useEffect, useState } from 'react';
import Image from 'next/image';
import type { CommandResult, ContentItem, Role, Scenario, WorkspaceProps } from './domain';
import { canEdit, money } from './domain';
import { useOperator } from './provider';
import { Badge, EmptyState, Icon, StatusBadge } from './ui';
import { CompositionPreview } from './scene-editor';
import {
  PagesWorkspace,
  IdeasWorkspace,
  AssetsWorkspace,
  PacksWorkspace,
  LearningWorkspace,
} from './support-workspaces';
import {
  ContentWorkspace,
  OperationsWorkspace,
  PublicationWorkspace,
  ReviewWorkspace,
} from './production-workspaces';

const navigation = [
  ['content', 'Content', 'Your production workspace'],
  ['pages', 'Pages', 'Build a recognisable voice'],
  ['ideas', 'Ideas', 'Make room for the next good idea'],
  ['assets', 'Asset Registry', 'A library with a longer life'],
  ['packs', 'Asset packs', 'Build useful combinations'],
  ['review', 'Review', 'A fresh pair of eyes'],
  ['publication', 'Publication', 'Ready for the next step'],
  ['operations', 'Operations', 'Know what is happening'],
  ['learning', 'Learning', 'Turn observations into better decisions'],
];
interface Route {
  view: string;
  id?: string;
  tab?: string;
  detail?: string;
}
function readRoute(): Route {
  const [view = 'content', id, tab, detail] = window.location.hash
    .slice(1)
    .split('/')
    .map(decodeURIComponent);
  return { view: navigation.some((n) => n[0] === view) ? view : 'content', id, tab, detail };
}
export function OperatorApp() {
  const { state, loading, error, execute, reset, notice, dismissNotice } = useOperator();
  const [route, setRoute] = useState<Route>({ view: 'content' });
  const [demoOpen, setDemoOpen] = useState(false);
  const [resetOpen, setResetOpen] = useState(false);
  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: 'instant' });
  }, [route.view, route.id, route.tab]);
  useEffect(() => {
    setRoute(readRoute());
    const handler = () => setRoute(readRoute());
    window.addEventListener('hashchange', handler);
    return () => window.removeEventListener('hashchange', handler);
  }, []);
  useEffect(() => {
    if (!notice?.ok) return;
    const timer = window.setTimeout(dismissNotice, 5000);
    return () => window.clearTimeout(timer);
  }, [notice, dismissNotice]);
  const navigate = (view: string, id?: string, tab?: string, detail?: string) => {
    window.location.hash = [view, id, tab, detail]
      .filter(Boolean)
      .map((value) => encodeURIComponent(value!))
      .join('/');
  };
  const nav = navigation.find((n) => n[0] === route.view)!;
  const props: WorkspaceProps | null = state ? { state, execute, navigate } : null;
  const selectedContent = state?.contents.find((c) => c.id === route.id);
  const pendingReview = state?.packages.filter((p) => p.status === 'review').length ?? 0;
  return (
    <div className="app-shell">
      <a
        href="#main-workspace"
        className="skip-link"
        onClick={(event) => {
          event.preventDefault();
          document.getElementById('main-workspace')?.focus();
        }}
      >
        Skip to workspace
      </a>
      <aside className="sidebar">
        <a className="brand" href="#content" aria-label="Content Laboratory home">
          <span className="brand-mark">
            <i />
            <i />
            <i />
            <i />
          </span>
          <span>
            content<span>laboratory</span>
          </span>
        </a>
        <div className="studio-switch">
          <span className="studio-avatar">CL</span>
          <div>
            <strong>The working studio</strong>
            <small>Personal workspace</small>
          </div>
          <span className="chevron">⌄</span>
        </div>
        <div className="nav-label">WORKSPACE</div>
        <nav aria-label="Main navigation">
          {navigation.map(([key, label], index) => (
            <div key={key}>
              {index === 5 && <div className="nav-label nav-divider">PRODUCTION & INSIGHTS</div>}
              <a
                href={`#${key}`}
                aria-label={label}
                className={`nav-item ${route.view === key ? 'active' : ''}`}
                aria-current={route.view === key ? 'page' : undefined}
              >
                <Icon name={key} />
                <span>{label}</span>
                {key === 'review' && pendingReview > 0 && <b>{pendingReview}</b>}
              </a>
            </div>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="demo-note">
            <span className="live-dot" />
            <strong>Your ideas. Room to grow.</strong>
            <p>
              This is a local prototype.
              <br />
              Every service is simulated.
            </p>
          </div>
          <button
            className="nav-item demo-toggle"
            aria-label="Show demo controls"
            onClick={() => setDemoOpen(!demoOpen)}
            aria-expanded={demoOpen}
          >
            <Icon name="settings" />
            <span>Demo controls</span>
          </button>
          <div className="operator-user">
            <span className="user-avatar">DO</span>
            <div>
              <strong>Demo owner</strong>
              <small>{state?.role ?? 'owner'} · role preview</small>
            </div>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            Studio <span>/</span> <strong>{nav[1]}</strong>
            {selectedContent && (
              <>
                <span>/</span>
                <span className="crumb-content">{selectedContent.draft.title}</span>
              </>
            )}
          </div>
          <div className="topbar-right">
            <Badge tone="demo">
              <span className="live-dot" />
              Prototype · simulated services
            </Badge>
            <button
              className="icon-button"
              aria-label="Open demo controls"
              onClick={() => setDemoOpen(!demoOpen)}
            >
              <Icon name="settings" />
            </button>
          </div>
        </header>
        {demoOpen && (
          <section className="demo-controls" aria-label="Demo controls">
            <div>
              <strong>Explore the edge cases</strong>
              <p>Role permissions and service conditions affect every workspace.</p>
            </div>
            <label className="field">
              Preview role
              <select
                aria-label="Preview role"
                value={state?.role ?? 'owner'}
                onChange={(e) => void execute({ type: 'setRole', role: e.target.value as Role })}
              >
                <option value="owner">Owner · full journey</option>
                <option value="editor">Editor · creation only</option>
                <option value="reviewer">Reviewer · approval only</option>
                <option value="viewer">Read only</option>
              </select>
            </label>
            <label className="field">
              Service scenario
              <select
                aria-label="Service scenario"
                value={state?.scenario ?? 'portfolio'}
                onChange={(e) => void reset(e.target.value as Scenario)}
              >
                <option value="portfolio">Working portfolio</option>
                <option value="empty">Empty workspace</option>
                <option value="unavailable">Service unavailable</option>
                <option value="loading">Loading</option>
              </select>
            </label>
            <button className="button secondary" onClick={() => setResetOpen(true)}>
              Reset demo
            </button>
            {resetOpen && (
              <div className="notice amber">
                Reset replaces local prototype edits with the original fixtures.{' '}
                <button
                  className="button secondary"
                  onClick={() => {
                    void reset();
                    setResetOpen(false);
                    navigate('content');
                  }}
                >
                  Reset local data
                </button>
                <button className="button ghost" onClick={() => setResetOpen(false)}>
                  Keep my edits
                </button>
              </div>
            )}
          </section>
        )}
        <main
          id="main-workspace"
          tabIndex={-1}
          className={`main-workspace ${route.id ? 'detail-main' : ''}`}
        >
          {!route.id && (
            <header className="workspace-heading">
              <div>
                <p className="eyebrow">
                  {route.view === 'content' ? 'MAKE SOMETHING WORTH SHARING' : 'THE WORKING STUDIO'}
                </p>
                <h1>{route.view === 'content' ? 'Content studio' : nav[1]}</h1>
                <p>{nav[2]}. One considered step at a time.</p>
              </div>
              {route.view === 'content' && props && <CreateContentButton {...props} />}
            </header>
          )}
          {state?.recoveryNotice && <div className="notice amber">{state.recoveryNotice}</div>}
          {state && state.role !== 'owner' && (
            <div className="permission-banner">
              <Icon name="review" size={16} />
              {state.role === 'viewer'
                ? 'Read-only preview. Explore every screen; editing and approval need a different role.'
                : `${state.role === 'editor' ? 'Editor' : 'Reviewer'} role preview. ${state.role === 'editor' ? 'Package and publication approval belong to the owner or reviewer.' : 'Creative edits belong to the owner or editor.'}`}
            </div>
          )}
          {loading || state?.scenario === 'loading' ? (
            <div className="loading-workspace" role="status" aria-label="Loading workspace">
              <div className="skeleton" />
              <div className="grid-3">
                <div className="skeleton" />
                <div className="skeleton" />
                <div className="skeleton" />
              </div>
              <p>Preparing your workspace…</p>
              <button className="button secondary" onClick={() => void reset()}>
                Load working portfolio
              </button>
            </div>
          ) : error || state?.scenario === 'unavailable' ? (
            <EmptyState
              title="The workspace is unavailable"
              action={
                <button className="button primary" onClick={() => void reset()}>
                  Reconnect simulated service
                </button>
              }
            >
              This is a simulated service failure. Reconnect to return to the working portfolio.
            </EmptyState>
          ) : props ? (
            <>
              {route.view === 'content' &&
                (route.id ? (
                  selectedContent ? (
                    <ContentWorkspace
                      {...props}
                      content={selectedContent}
                      tab={route.tab ?? 'brief'}
                      detail={route.detail}
                    />
                  ) : (
                    <EmptyState
                      title="Content not found"
                      action={
                        <button className="button primary" onClick={() => navigate('content')}>
                          Back to content
                        </button>
                      }
                    >
                      This item may belong to a previous demo session.
                    </EmptyState>
                  )
                ) : (
                  <ContentHome {...props} />
                ))}
              {route.view === 'pages' && <PagesWorkspace {...props} />}
              {route.view === 'ideas' && <IdeasWorkspace {...props} />}
              {route.view === 'assets' && <AssetsWorkspace {...props} />}
              {route.view === 'packs' && <PacksWorkspace {...props} />}
              {route.view === 'review' && <ReviewWorkspace {...props} />}
              {route.view === 'publication' && <PublicationWorkspace {...props} />}
              {route.view === 'operations' && (
                <OperationsWorkspace {...props} selectedRunId={route.id} />
              )}
              {route.view === 'learning' && <LearningWorkspace {...props} />}
            </>
          ) : null}
          <footer className="workspace-footer">
            <span>CONTENT LABORATORY</span>
            <span>Thoughtful content, from idea to insight.</span>
            <span>Local prototype / v0.1</span>
          </footer>
        </main>
        {notice && (
          <div
            className={`toast ${notice.ok ? 'success' : 'error'}`}
            role={notice.ok ? 'status' : 'alert'}
          >
            <Icon name={notice.ok ? 'check' : 'operations'} />
            <div>
              <strong>
                {notice.ok
                  ? 'Workspace updated'
                  : notice.kind === 'permission'
                    ? 'Permission limited'
                    : notice.kind === 'blocked'
                      ? 'Action blocked'
                      : 'Something needs attention'}
              </strong>
              <p>{notice.message}</p>
            </div>
            <button
              className="icon-button"
              onClick={dismissNotice}
              aria-label="Dismiss notification"
            >
              <Icon name="close" size={18} />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function CreateContentButton({ state, execute, navigate }: WorkspaceProps) {
  const [open, setOpen] = useState(false);
  const [pageId, setPageId] = useState(state.pages[0]?.id ?? '');
  const [title, setTitle] = useState('');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<CommandResult | null>(null);
  return (
    <div className="create-content-control">
      <button
        className="button primary"
        disabled={!canEdit(state.role)}
        title={!canEdit(state.role) ? 'Owner or editor role required' : undefined}
        onClick={() => setOpen(!open)}
        aria-expanded={open}
      >
        <Icon name="plus" size={18} />
        New content
      </button>
      {open && (
        <form
          className="create-popover panel"
          aria-label="Create content"
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            const response = await execute({ type: 'createContent', pageId, title });
            setResult(response);
            setBusy(false);
            if (response.ok) {
              setOpen(false);
              navigate('content', response.entityId);
            }
          }}
        >
          <div className="section-heading">
            <h2>A new starting point</h2>
            <button
              type="button"
              className="icon-button"
              aria-label="Close new content"
              onClick={() => setOpen(false)}
            >
              <Icon name="close" />
            </button>
          </div>
          {state.pages.length ? (
            <>
              <label className="field">
                Page
                <select required value={pageId} onChange={(e) => setPageId(e.target.value)}>
                  {state.pages.map((page) => (
                    <option key={page.id} value={page.id}>
                      {page.name}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                Working title
                <input
                  value={title}
                  required
                  placeholder="What is the idea?"
                  onChange={(e) => setTitle(e.target.value)}
                />
              </label>
              {result && !result.ok && <p className="notice red">{result.message}</p>}
              <button className="button primary" disabled={busy}>
                {busy ? 'Creating…' : 'Create draft'}
                <Icon name="arrow" size={16} />
              </button>
            </>
          ) : (
            <>
              <p>Create a page to give your content a purpose and a voice.</p>
              <button type="button" className="button primary" onClick={() => navigate('pages')}>
                Set up a page
              </button>
            </>
          )}
        </form>
      )}
    </div>
  );
}
function ContentHome({ state, execute, navigate }: WorkspaceProps) {
  const [filter, setFilter] = useState('all');
  const [search, setSearch] = useState('');
  const [pageId, setPageId] = useState('all');
  const contents = state.contents.filter(
    (c) =>
      (filter === 'all' || c.stage === filter) &&
      (pageId === 'all' || c.pageId === pageId) &&
      c.draft.title.toLowerCase().includes(search.toLowerCase()),
  );
  const featured = state.contents.find((c) => c.id === 'content-mug') ?? state.contents[0];
  const attention = state.contents
    .filter((c) => c.stage === 'blocked' || c.stage === 'review')
    .slice(0, 3);
  if (!state.contents.length)
    return (
      <EmptyState
        title="A fresh page. A first idea."
        action={<CreateContentButton state={state} execute={execute} navigate={navigate} />}
      >
        Set up your page, choose an idea or start with an asset. Your first content draft will
        appear here.
      </EmptyState>
    );
  return (
    <>
      <section className="studio-stats" aria-label="Portfolio summary">
        {[
          [
            'In the making',
            state.contents.filter((c) => ['draft', 'in_progress'].includes(c.stage)).length,
            'Active creative work',
            'content',
          ],
          [
            'Ready for a fresh look',
            state.packages.filter((p) => p.status === 'review').length,
            'Waiting for review',
            'review',
          ],
          [
            'Approved & prepared',
            state.packages.filter((p) => p.status === 'approved').length,
            'Exact revisions approved',
            'publication',
          ],
          [
            'Illustrative spend',
            money(state.runs.reduce((sum, r) => sum + r.spent.minor, 0)),
            'Simulated · this portfolio',
            'operations',
          ],
        ].map(([label, count, detail, view]) => (
          <button key={String(label)} className="stat-card" onClick={() => navigate(String(view))}>
            <span>{label}</span>
            <strong>
              {count}
              <Icon name={String(view)} size={21} />
            </strong>
            <small>{detail}</small>
          </button>
        ))}
      </section>
      <div className="focus-grid">
        <section className="focus-card">
          <div className="focus-copy">
            <Badge tone="light">PICK UP WHERE YOU LEFT OFF</Badge>
            <p className="eyebrow">
              {state.pages.find((p) => p.id === featured.pageId)?.name} / PRODUCT STORY
            </p>
            <h2>
              Small rituals.
              <br />
              <em>Better mornings.</em>
            </h2>
            <p>
              A familiar object. A different perspective.
              <br />
              Give your next story a little more shape.
            </p>
            <button
              className="button cream"
              onClick={() => navigate('content', featured.id, 'edit')}
            >
              Continue creating
              <Icon name="arrow" size={17} />
            </button>
            <span className="focus-meta">
              <Icon name="clock" size={13} />
              {(featured.draft.totalFrames * featured.draft.fps.denominator) /
                featured.draft.fps.numerator}{' '}
              sec · {featured.draft.scenes.length} scenes · editable composition
            </span>
          </div>
          <div className="focus-art">
            <span className="focus-circle" />
            <Image
              src="/demo/mug.svg"
              alt="Illustrated stoneware mug"
              width={600}
              height={600}
              unoptimized
            />
            <span className="specimen-label">OBJECT STUDY — 001</span>
          </div>
        </section>
        <section className="attention-card panel">
          <div className="section-heading">
            <h2>A little attention</h2>
            <span className="count-pill">{attention.length}</span>
          </div>
          <p className="muted small">A few decisions to keep things moving.</p>
          {attention.map((c, i) => (
            <button
              className="attention-item"
              key={c.id}
              onClick={() =>
                navigate(
                  'content',
                  c.id,
                  state.runs.some((r) => r.contentId === c.id && r.status === 'failed')
                    ? 'run'
                    : c.stage === 'blocked'
                      ? 'assets'
                      : 'review',
                )
              }
            >
              <span className={`attention-icon ${c.stage}`}>
                <Icon name={c.stage === 'blocked' ? 'packs' : 'review'} size={19} />
              </span>
              <span>
                <strong>
                  {state.runs.some((r) => r.contentId === c.id && r.status === 'failed')
                    ? 'An execution needs another look'
                    : c.stage === 'blocked'
                      ? 'An ingredient is missing'
                      : i === 1
                        ? 'Your review makes the difference'
                        : 'Ready for your review'}
                </strong>
                <small>{c.draft.title}</small>
              </span>
              <Icon name="arrow" size={16} />
            </button>
          ))}
          <button className="text-button" onClick={() => navigate('operations')}>
            Open operations
            <Icon name="arrow" size={15} />
          </button>
        </section>
      </div>
      <section className="content-section">
        <div className="section-heading">
          <div>
            <h2>On your workbench</h2>
            <p className="muted">Every story, at its own stage.</p>
          </div>
          <label className="compact-select">
            <span className="sr-only">Filter by page</span>
            <select value={pageId} onChange={(e) => setPageId(e.target.value)}>
              <option value="all">All pages</option>
              {state.pages.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="workbench-toolbar">
          <div className="filter-tabs" aria-label="Content status">
            {['all', 'draft', 'review', 'approved', 'blocked'].map((value) => (
              <button
                key={value}
                className={filter === value ? 'active' : ''}
                onClick={() => setFilter(value)}
              >
                {value === 'all'
                  ? 'All content'
                  : value === 'review'
                    ? 'In review'
                    : value[0].toUpperCase() + value.slice(1)}
                {value === 'all' && <span>{state.contents.length}</span>}
              </button>
            ))}
          </div>
          <label className="search-field">
            <Icon name="search" size={17} />
            <input
              aria-label="Search content"
              placeholder="Find a story…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </label>
        </div>
        <div className="content-grid">
          {contents.map((content) => (
            <ContentCard
              key={content.id}
              content={content}
              state={state}
              onClick={() => navigate('content', content.id)}
            />
          ))}
        </div>
        {!contents.length && (
          <EmptyState
            title="No stories here yet"
            action={
              <button
                className="button secondary"
                onClick={() => {
                  setSearch('');
                  setFilter('all');
                  setPageId('all');
                }}
              >
                Clear filters
              </button>
            }
          >
            Try a different search or production stage.
          </EmptyState>
        )}
      </section>
    </>
  );
}
function ContentCard({
  content,
  state,
  onClick,
}: {
  content: ContentItem;
  state: WorkspaceProps['state'];
  onClick: () => void;
}) {
  const page = state.pages.find((p) => p.id === content.pageId);
  return (
    <button className="content-card" onClick={onClick}>
      <div className={`content-thumbnail family-${content.family}`}>
        <CompositionPreview composition={content.draft} state={state} />
        <span className="thumbnail-duration">
          {Math.round(
            (content.draft.totalFrames * content.draft.fps.denominator) /
              content.draft.fps.numerator,
          )}
          s
        </span>
        <span className="thumbnail-open">
          <Icon name="arrow" size={18} />
        </span>
      </div>
      <div className="content-card-body">
        <div className="row">
          <span className="page-tag">
            <i style={{ background: page?.color }} />
            {page?.name}
          </span>
          <StatusBadge status={content.stage} />
        </div>
        <h3>{content.draft.title}</h3>
        <p>
          {content.family === 'product'
            ? 'Object story'
            : content.family === 'graphic'
              ? 'Graphic explainer'
              : 'Source-video story'}{' '}
          <span>·</span> {content.draft.scenes.length} scenes
        </p>
        <div className="content-card-footer">
          <span>{content.currentRevisionId ? 'Saved revision' : 'Working draft'}</span>
          <span>
            {content.draft.mode.replaceAll('_', ' ')}
            <Icon name="arrow" size={14} />
          </span>
        </div>
      </div>
    </button>
  );
}
