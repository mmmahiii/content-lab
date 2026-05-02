'use client';

import { FormEvent, useEffect, useMemo, useState } from 'react';

const ORG_ID = '7d3d7599-820e-4c8d-9c74-3d3b6d6f2785';

type PageRecord = {
  id: string;
  platform: string;
  display_name: string;
  external_page_id: string | null;
  handle: string | null;
  ownership: string;
  created_at: string;
  updated_at: string;
};

type PolicyDocument = {
  mode_ratios: {
    exploit: number;
    explore: number;
    mutation: number;
    chaos: number;
  };
  budget: {
    per_run_usd_limit: number;
    daily_usd_limit: number;
    monthly_usd_limit: number;
  };
  thresholds: {
    similarity: {
      warn_at: number;
      block_at: number;
    };
    min_quality_score: number;
  };
};

type PagePolicy = {
  state: PolicyDocument;
  updated_at: string | null;
  is_explicit_override: boolean;
  inherited_from: 'global' | 'default' | null;
};

type FormState = {
  displayName: string;
  handle: string;
  platform: string;
  ownership: 'owned' | 'competitor';
};

const emptyForm: FormState = {
  displayName: '',
  handle: '',
  platform: 'instagram',
  ownership: 'owned',
};

const policyLabels = {
  exploit: 'Exploit',
  explore: 'Explore',
  mutation: 'Mutation',
  chaos: 'Chaos',
  per_run_usd_limit: 'Per run',
  daily_usd_limit: 'Daily',
  monthly_usd_limit: 'Monthly',
  warn_at: 'Warn at',
  block_at: 'Block at',
  min_quality_score: 'Min QA',
} as const;

function normalizeHandle(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }
  return trimmed.startsWith('@') ? trimmed : `@${trimmed}`;
}

function clonePolicy(policy: PolicyDocument): PolicyDocument {
  return {
    mode_ratios: { ...policy.mode_ratios },
    budget: { ...policy.budget },
    thresholds: {
      similarity: { ...policy.thresholds.similarity },
      min_quality_score: policy.thresholds.min_quality_score,
    },
  };
}

function formatPolicySource(policy: PagePolicy | null): string {
  if (!policy) {
    return 'Loading policy...';
  }
  if (policy.is_explicit_override) {
    return 'Saved page override';
  }
  return policy.inherited_from === 'global' ? 'Inherited from global policy' : 'Using default guardrails';
}

function validatePolicy(policy: PolicyDocument): string | null {
  const ratios = Object.values(policy.mode_ratios);
  const ratioTotal = ratios.reduce((sum, value) => sum + value, 0);
  if (ratios.some((value) => value < 0 || value > 1 || !Number.isFinite(value))) {
    return 'Every mode ratio must be between 0 and 1.';
  }
  if (Math.abs(ratioTotal - 1) > 0.001) {
    return 'Mode ratios must add up to 1.00.';
  }
  if (policy.budget.per_run_usd_limit > policy.budget.daily_usd_limit) {
    return 'Per-run budget must not exceed daily budget.';
  }
  if (policy.budget.daily_usd_limit > policy.budget.monthly_usd_limit) {
    return 'Daily budget must not exceed monthly budget.';
  }
  if (policy.thresholds.similarity.warn_at >= policy.thresholds.similarity.block_at) {
    return 'Similarity warning must be lower than the block threshold.';
  }
  return null;
}

export function PageWorkspace() {
  const [pages, setPages] = useState<PageRecord[]>([]);
  const [selectedPageId, setSelectedPageId] = useState<string>('');
  const [form, setForm] = useState<FormState>(emptyForm);
  const [policy, setPolicy] = useState<PagePolicy | null>(null);
  const [policyDraft, setPolicyDraft] = useState<PolicyDocument | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [isPolicySaving, setIsPolicySaving] = useState(false);
  const [isPolicyOpen, setIsPolicyOpen] = useState(false);
  const [message, setMessage] = useState('Loading saved pages...');

  const selectedPage = useMemo(
    () => pages.find((page) => page.id === selectedPageId) ?? pages[0] ?? null,
    [pages, selectedPageId],
  );

  async function loadPages() {
    setIsLoading(true);
    try {
      const response = await fetch(`/api/orgs/${ORG_ID}/pages`, { cache: 'no-store' });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const nextPages = (await response.json()) as PageRecord[];
      setPages(nextPages);
      setSelectedPageId((current) => {
        if (current && nextPages.some((page) => page.id === current)) {
          return current;
        }
        return nextPages[0]?.id ?? '';
      });
      setMessage(nextPages.length ? 'Saved pages loaded.' : 'No pages yet. Create one to test persistence.');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not load pages.');
    } finally {
      setIsLoading(false);
    }
  }

  async function loadPolicy(pageId: string) {
    setPolicy(null);
    setPolicyDraft(null);
    try {
      const response = await fetch(`/api/orgs/${ORG_ID}/policy/page/${pageId}`, { cache: 'no-store' });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const nextPolicy = (await response.json()) as PagePolicy;
      setPolicy(nextPolicy);
      setPolicyDraft(clonePolicy(nextPolicy.state));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not load page policy.');
    }
  }

  useEffect(() => {
    void loadPages();
  }, []);

  useEffect(() => {
    if (selectedPage?.id) {
      void loadPolicy(selectedPage.id);
    } else {
      setPolicy(null);
      setPolicyDraft(null);
    }
  }, [selectedPage?.id]);

  async function createPage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSaving(true);
    setMessage('Creating page...');
    try {
      const displayName = form.displayName.trim();
      if (!displayName) {
        throw new Error('Page name is required.');
      }

      const handle = normalizeHandle(form.handle);
      const response = await fetch(`/api/orgs/${ORG_ID}/pages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          platform: form.platform,
          display_name: displayName,
          external_page_id: handle ? `${form.platform}-${handle.replace('@', '')}` : null,
          handle,
          ownership: form.ownership,
          metadata: {},
        }),
      });

      if (!response.ok) {
        throw new Error(await response.text());
      }

      const created = (await response.json()) as PageRecord;
      setForm(emptyForm);
      await loadPages();
      setSelectedPageId(created.id);
      setMessage(`Saved ${created.display_name}.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not create page.');
    } finally {
      setIsSaving(false);
    }
  }

  async function deleteSelectedPage() {
    if (!selectedPage) {
      return;
    }

    const confirmed = window.confirm(`Delete ${selectedPage.display_name}?`);
    if (!confirmed) {
      return;
    }

    setIsSaving(true);
    setMessage('Deleting page...');
    try {
      const response = await fetch(`/api/orgs/${ORG_ID}/pages/${selectedPage.id}`, {
        method: 'DELETE',
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      await loadPages();
      setMessage(`Deleted ${selectedPage.display_name}.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not delete page.');
    } finally {
      setIsSaving(false);
    }
  }

  async function savePolicy() {
    if (!selectedPage || !policyDraft) {
      return;
    }
    const validationMessage = validatePolicy(policyDraft);
    if (validationMessage) {
      setMessage(validationMessage);
      return;
    }

    setIsPolicySaving(true);
    setMessage('Saving page policy...');
    try {
      const response = await fetch(`/api/orgs/${ORG_ID}/policy/page/${selectedPage.id}`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          'X-Actor-Id': 'operator:ui-rebuild',
        },
        body: JSON.stringify(policyDraft),
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const saved = (await response.json()) as PagePolicy;
      setPolicy(saved);
      setPolicyDraft(clonePolicy(saved.state));
      setMessage(`Policy saved for ${selectedPage.display_name}.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not save page policy.');
    } finally {
      setIsPolicySaving(false);
    }
  }

  function updatePolicyDraft(updater: (current: PolicyDocument) => PolicyDocument) {
    setPolicyDraft((current) => (current ? updater(current) : current));
  }

  function numberValue(value: string): number {
    return Number.parseFloat(value || '0');
  }

  return (
    <main className="workspace">
      <aside className="sidebar" aria-label="Pages">
        <div className="sidebar__header">
          <div>
            <p className="eyebrow">Pages</p>
            <h1>Content Lab</h1>
          </div>
          <button className="icon-button" type="button" onClick={() => void loadPages()} disabled={isLoading}>
            Refresh
          </button>
        </div>

        <label className="page-picker">
          Select page
          <select
            value={selectedPage?.id ?? ''}
            onChange={(event) => setSelectedPageId(event.target.value)}
            disabled={!pages.length}
          >
            {pages.map((page) => (
              <option key={page.id} value={page.id}>
                {page.display_name} {page.handle ? `(${page.handle})` : ''}
              </option>
            ))}
            {!pages.length && <option value="">No pages yet</option>}
          </select>
        </label>

        {selectedPage ? (
          <div className="selected-card">
            <p className="eyebrow">{selectedPage.ownership}</p>
            <strong>{selectedPage.display_name}</strong>
            <span>{selectedPage.handle ?? selectedPage.platform}</span>
            <button className="danger-button" type="button" onClick={deleteSelectedPage} disabled={isSaving}>
              Delete page
            </button>
          </div>
        ) : null}

        <form className="create-form" onSubmit={createPage}>
          <p className="eyebrow">Create</p>
          <label>
            Name
            <input
              value={form.displayName}
              onChange={(event) => setForm((current) => ({ ...current, displayName: event.target.value }))}
              placeholder="New brand page"
            />
          </label>
          <label>
            Handle
            <input
              value={form.handle}
              onChange={(event) => setForm((current) => ({ ...current, handle: event.target.value }))}
              placeholder="@new.page"
            />
          </label>
          <div className="form-row">
            <label>
              Platform
              <select
                value={form.platform}
                onChange={(event) => setForm((current) => ({ ...current, platform: event.target.value }))}
              >
                <option value="instagram">Instagram</option>
                <option value="tiktok">TikTok</option>
                <option value="youtube">YouTube</option>
              </select>
            </label>
            <label>
              Type
              <select
                value={form.ownership}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    ownership: event.target.value as FormState['ownership'],
                  }))
                }
              >
                <option value="owned">Owned</option>
                <option value="competitor">Competitor</option>
              </select>
            </label>
          </div>
          <button className="primary-button" type="submit" disabled={isSaving}>
            Create page
          </button>
        </form>
      </aside>

      <section className="detail">
        <div className="detail__topline">
          <span className="status-dot" />
          <span>{message}</span>
        </div>
        {selectedPage ? (
          <div className="detail__panel">
            <div className="page-summary">
              <div>
                <p className="eyebrow">{selectedPage.platform}</p>
                <h2>{selectedPage.display_name}</h2>
              </div>
              <p className="policy-source">{formatPolicySource(policy)}</p>
            </div>

            <dl className="detail-grid">
              <div>
                <dt>Handle</dt>
                <dd>{selectedPage.handle ?? 'Not set'}</dd>
              </div>
              <div>
                <dt>Updated</dt>
                <dd>{new Date(selectedPage.updated_at).toLocaleString()}</dd>
              </div>
            </dl>

            {policyDraft ? (
              <section className="policy-editor" aria-label="Page policy">
                <button
                  className="policy-toggle"
                  type="button"
                  aria-expanded={isPolicyOpen}
                  onClick={() => setIsPolicyOpen((current) => !current)}
                >
                  <div>
                    <p className="eyebrow">Policy</p>
                    <h3>Page guardrails</h3>
                  </div>
                  <span>{isPolicyOpen ? 'Hide' : 'Show'}</span>
                </button>

                {isPolicyOpen ? (
                  <>
                    <div className="policy-editor__header">
                      <p className="muted">Edit and save the active policy for this page.</p>
                      <button
                        className="primary-button"
                        type="button"
                        onClick={() => void savePolicy()}
                        disabled={isPolicySaving}
                      >
                        {isPolicySaving ? 'Saving...' : 'Save policy'}
                      </button>
                    </div>

                    <div className="policy-grid">
                      <section className="policy-card">
                        <h4>Mode ratios</h4>
                        <p>Balance proven ideas, exploration, mutation, and riskier concepts.</p>
                        {Object.entries(policyDraft.mode_ratios).map(([key, value]) => (
                          <label key={key}>
                            {policyLabels[key as keyof typeof policyLabels]}
                            <input
                              min="0"
                              max="1"
                              step="0.01"
                              type="number"
                              value={value}
                              onChange={(event) =>
                                updatePolicyDraft((current) => ({
                                  ...current,
                                  mode_ratios: {
                                    ...current.mode_ratios,
                                    [key]: numberValue(event.target.value),
                                  },
                                }))
                              }
                            />
                          </label>
                        ))}
                        <span className="policy-note">
                          Total:{' '}
                          {Object.values(policyDraft.mode_ratios)
                            .reduce((sum, value) => sum + value, 0)
                            .toFixed(2)}
                        </span>
                      </section>

                      <section className="policy-card">
                        <h4>Budget</h4>
                        <p>Keep automated generation spend inside a page-specific envelope.</p>
                        {Object.entries(policyDraft.budget).map(([key, value]) => (
                          <label key={key}>
                            {policyLabels[key as keyof typeof policyLabels]}
                            <input
                              min="0"
                              step="0.01"
                              type="number"
                              value={value}
                              onChange={(event) =>
                                updatePolicyDraft((current) => ({
                                  ...current,
                                  budget: {
                                    ...current.budget,
                                    [key]: numberValue(event.target.value),
                                  },
                                }))
                              }
                            />
                          </label>
                        ))}
                      </section>

                      <section className="policy-card">
                        <h4>Quality thresholds</h4>
                        <p>Control reuse similarity and minimum QA quality before output moves forward.</p>
                        <label>
                          {policyLabels.warn_at}
                          <input
                            min="0"
                            max="1"
                            step="0.01"
                            type="number"
                            value={policyDraft.thresholds.similarity.warn_at}
                            onChange={(event) =>
                              updatePolicyDraft((current) => ({
                                ...current,
                                thresholds: {
                                  ...current.thresholds,
                                  similarity: {
                                    ...current.thresholds.similarity,
                                    warn_at: numberValue(event.target.value),
                                  },
                                },
                              }))
                            }
                          />
                        </label>
                        <label>
                          {policyLabels.block_at}
                          <input
                            min="0"
                            max="1"
                            step="0.01"
                            type="number"
                            value={policyDraft.thresholds.similarity.block_at}
                            onChange={(event) =>
                              updatePolicyDraft((current) => ({
                                ...current,
                                thresholds: {
                                  ...current.thresholds,
                                  similarity: {
                                    ...current.thresholds.similarity,
                                    block_at: numberValue(event.target.value),
                                  },
                                },
                              }))
                            }
                          />
                        </label>
                        <label>
                          {policyLabels.min_quality_score}
                          <input
                            min="0"
                            max="1"
                            step="0.01"
                            type="number"
                            value={policyDraft.thresholds.min_quality_score}
                            onChange={(event) =>
                              updatePolicyDraft((current) => ({
                                ...current,
                                thresholds: {
                                  ...current.thresholds,
                                  min_quality_score: numberValue(event.target.value),
                                },
                              }))
                            }
                          />
                        </label>
                      </section>
                    </div>
                  </>
                ) : null}
              </section>
            ) : (
              <p className="muted">Loading policy for this page...</p>
            )}
          </div>
        ) : (
          <div className="detail__panel">
            <p className="eyebrow">Start</p>
            <h2>Create your first page</h2>
            <p className="muted">Use the sidebar form. It will save through the API into the database.</p>
          </div>
        )}
      </section>
    </main>
  );
}
