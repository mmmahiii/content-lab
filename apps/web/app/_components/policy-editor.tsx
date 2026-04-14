'use client';

import React, { useState, type ChangeEvent } from 'react';

import type { PolicyStateOut } from '@shared/types';

import {
  clonePolicyDocument,
  createPolicyUpdateSubmission,
  type PolicyEditorField,
} from '../policy-editor.helpers';
import {
  submitOperatorRequest,
  type FieldErrors,
  type SubmissionFeedback,
} from '../operator-console.helpers';
import type { PolicyEditorRecord } from '../_lib/operator-policy';

function formatTimestamp(value: string | null): string {
  if (!value) {
    return 'Not saved yet';
  }

  return new Intl.DateTimeFormat('en-GB', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value));
}

function FeedbackPanel({ feedback }: { feedback: SubmissionFeedback<PolicyStateOut> }) {
  if (feedback.kind === 'idle') {
    return null;
  }

  const className =
    feedback.kind === 'success'
      ? 'cl-feedback is-success'
      : feedback.kind === 'error'
        ? 'cl-feedback is-error'
        : 'cl-feedback is-pending';

  return (
    <div className={className}>
      {feedback.title ? <strong>{feedback.title}</strong> : null}
      {feedback.message ? <p className="cl-field-note">{feedback.message}</p> : null}
      {feedback.route ? <p className="cl-field-note">Audited route: PATCH {feedback.route}</p> : null}
      {feedback.details && feedback.details.length > 0 ? (
        <ul className="cl-compact">
          {feedback.details.map((detail) => (
            <li key={detail} className="cl-field-note">
              {detail}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function SectionError({
  errors,
  field,
}: {
  errors: FieldErrors<PolicyEditorField>;
  field: PolicyEditorField;
}) {
  const message = errors[field];
  return message ? <p className="cl-field-error">{message}</p> : null;
}

export function PolicyEditor({
  apiBaseUrl,
  orgId,
  records,
}: {
  apiBaseUrl: string;
  orgId: string;
  records: PolicyEditorRecord[];
}) {
  const [policyRecords, setPolicyRecords] = useState(records);
  const [selectedPageId, setSelectedPageId] = useState(records[0]?.page.id ?? '');
  const [actorId, setActorId] = useState('');
  const [fieldErrors, setFieldErrors] = useState<FieldErrors<PolicyEditorField>>({});
  const [feedback, setFeedback] = useState<SubmissionFeedback<PolicyStateOut>>({ kind: 'idle' });
  const [pending, setPending] = useState(false);

  const selectedRecord =
    policyRecords.find((record) => record.page.id === selectedPageId) ?? policyRecords[0] ?? null;

  if (selectedRecord === null) {
    return null;
  }

  function updateSelectedDraft(updater: (current: PolicyEditorRecord) => PolicyEditorRecord): void {
    setPolicyRecords((current) =>
      current.map((record) =>
        record.page.id === selectedRecord.page.id ? updater(record) : record,
      ),
    );
  }

  function handleNumberChange(
    update: (current: PolicyEditorRecord, nextValue: number) => PolicyEditorRecord,
  ) {
    return (event: ChangeEvent<HTMLInputElement>) => {
      const nextValue = Number(event.target.value);
      updateSelectedDraft((current) => update(current, nextValue));
    };
  }

  function resetSelectedDraft(): void {
    updateSelectedDraft((current) => ({
      ...current,
      draft: clonePolicyDocument(current.baseline),
    }));
    setFieldErrors({});
    setFeedback({ kind: 'idle' });
  }

  async function handleSubmit(
    event: ChangeEvent<HTMLFormElement> | React.FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault();

    const submission = createPolicyUpdateSubmission({
      orgId,
      pageId: selectedRecord.page.id,
      form: {
        actorId,
        state: selectedRecord.draft,
      },
    });

    if (!submission.ok) {
      setFieldErrors(submission.fieldErrors);
      setFeedback({
        kind: 'error',
        title: 'Policy validation failed',
        details: submission.summary,
      });
      return;
    }

    setFieldErrors({});
    setPending(true);
    setFeedback({
      kind: 'pending',
      title: 'Saving page policy',
      message: 'Only the supported phase-1 policy guardrails are being patched.',
      route: submission.value.actionPath,
    });

    const result = await submitOperatorRequest<PolicyStateOut>(apiBaseUrl, submission.value);
    setFeedback(result);
    setPending(false);

    const payload = result.payload;
    if (result.kind === 'success' && payload) {
      updateSelectedDraft((current) => ({
        ...current,
        policy: payload,
        baseline: clonePolicyDocument(payload.state),
        draft: clonePolicyDocument(payload.state),
        source: 'saved',
      }));
    }
  }

  return (
    <div className="cl-policy-shell">
      <div className="cl-highlight-card cl-policy-picker">
        <label className="cl-label">
          Page
          <select
            value={selectedRecord.page.id}
            onChange={(event) => {
              setSelectedPageId(event.target.value);
              setFieldErrors({});
              setFeedback({ kind: 'idle' });
            }}
          >
            {policyRecords.map((record) => (
              <option key={record.page.id} value={record.page.id}>
                {record.page.displayName} (
                {record.source === 'saved' ? 'saved policy' : 'default guardrails'})
              </option>
            ))}
          </select>
        </label>

        <div className="cl-meta-grid">
          <article className="cl-meta-card">
            <strong>{selectedRecord.page.displayName}</strong>
            <p className="cl-field-note">{selectedRecord.page.handle ?? 'Handle not set'}</p>
          </article>
          <article className="cl-meta-card">
            <strong>Policy source</strong>
            <p className="cl-field-note">
              {selectedRecord.source === 'saved'
                ? 'Loaded from the page policy route.'
                : 'Default phase-1 guardrails ready to save.'}
            </p>
          </article>
          <article className="cl-meta-card">
            <strong>Last saved</strong>
            <p className="cl-field-note">{formatTimestamp(selectedRecord.policy?.updated_at ?? null)}</p>
          </article>
          <article className="cl-meta-card">
            <strong>Scope</strong>
            <p className="cl-field-note">page:{selectedRecord.page.id}</p>
          </article>
        </div>
      </div>

      <form className="cl-policy-shell" onSubmit={handleSubmit}>
        <label className="cl-label">
          Operator Actor ID
          <input
            value={actorId}
            onChange={(event) => setActorId(event.target.value)}
            placeholder="operator:policy-manager"
          />
          <p className="cl-field-note">
            The save action uses the audited <code className="cl-code">X-Actor-Id</code> header on the
            page-policy PATCH route.
          </p>
          <SectionError errors={fieldErrors} field="actorId" />
        </label>

        <div className="cl-policy-grid">
          <section className="cl-policy-section">
            <div className="cl-policy-head">
              <h3 className="cl-compact">Mode ratios</h3>
              <p className="cl-field-note">These values must stay within 0.00 to 1.00 and sum to 1.00.</p>
            </div>

            <label className="cl-label">
              Exploit
              <input
                min="0"
                max="1"
                step="0.01"
                type="number"
                value={selectedRecord.draft.mode_ratios.exploit}
                onChange={handleNumberChange((current, nextValue) => ({
                  ...current,
                  draft: {
                    ...current.draft,
                    mode_ratios: {
                      ...current.draft.mode_ratios,
                      exploit: nextValue,
                    },
                  },
                }))}
              />
            </label>

            <label className="cl-label">
              Explore
              <input
                min="0"
                max="1"
                step="0.01"
                type="number"
                value={selectedRecord.draft.mode_ratios.explore}
                onChange={handleNumberChange((current, nextValue) => ({
                  ...current,
                  draft: {
                    ...current.draft,
                    mode_ratios: {
                      ...current.draft.mode_ratios,
                      explore: nextValue,
                    },
                  },
                }))}
              />
            </label>

            <label className="cl-label">
              Mutation
              <input
                min="0"
                max="1"
                step="0.01"
                type="number"
                value={selectedRecord.draft.mode_ratios.mutation}
                onChange={handleNumberChange((current, nextValue) => ({
                  ...current,
                  draft: {
                    ...current.draft,
                    mode_ratios: {
                      ...current.draft.mode_ratios,
                      mutation: nextValue,
                    },
                  },
                }))}
              />
            </label>

            <label className="cl-label">
              Chaos
              <input
                min="0"
                max="1"
                step="0.01"
                type="number"
                value={selectedRecord.draft.mode_ratios.chaos}
                onChange={handleNumberChange((current, nextValue) => ({
                  ...current,
                  draft: {
                    ...current.draft,
                    mode_ratios: {
                      ...current.draft.mode_ratios,
                      chaos: nextValue,
                    },
                  },
                }))}
              />
            </label>

            <SectionError errors={fieldErrors} field="mode_ratios" />
          </section>

          <section className="cl-policy-section">
            <div className="cl-policy-head">
              <h3 className="cl-compact">Budget guardrails</h3>
              <p className="cl-field-note">Per-run must stay below daily, and daily must stay below monthly.</p>
            </div>

            <label className="cl-label">
              Per-run USD limit
              <input
                min="0"
                step="0.01"
                type="number"
                value={selectedRecord.draft.budget.per_run_usd_limit}
                onChange={handleNumberChange((current, nextValue) => ({
                  ...current,
                  draft: {
                    ...current.draft,
                    budget: {
                      ...current.draft.budget,
                      per_run_usd_limit: nextValue,
                    },
                  },
                }))}
              />
            </label>

            <label className="cl-label">
              Daily USD limit
              <input
                min="0"
                step="0.01"
                type="number"
                value={selectedRecord.draft.budget.daily_usd_limit}
                onChange={handleNumberChange((current, nextValue) => ({
                  ...current,
                  draft: {
                    ...current.draft,
                    budget: {
                      ...current.draft.budget,
                      daily_usd_limit: nextValue,
                    },
                  },
                }))}
              />
            </label>

            <label className="cl-label">
              Monthly USD limit
              <input
                min="0"
                step="0.01"
                type="number"
                value={selectedRecord.draft.budget.monthly_usd_limit}
                onChange={handleNumberChange((current, nextValue) => ({
                  ...current,
                  draft: {
                    ...current.draft,
                    budget: {
                      ...current.draft.budget,
                      monthly_usd_limit: nextValue,
                    },
                  },
                }))}
              />
            </label>

            <SectionError errors={fieldErrors} field="budget" />
          </section>

          <section className="cl-policy-section">
            <div className="cl-policy-head">
              <h3 className="cl-compact">Thresholds</h3>
              <p className="cl-field-note">
                Similarity warning must stay below the block threshold, and QA stays in the unit range.
              </p>
            </div>

            <label className="cl-label">
              Similarity warn at
              <input
                min="0"
                max="1"
                step="0.01"
                type="number"
                value={selectedRecord.draft.thresholds.similarity.warn_at}
                onChange={handleNumberChange((current, nextValue) => ({
                  ...current,
                  draft: {
                    ...current.draft,
                    thresholds: {
                      ...current.draft.thresholds,
                      similarity: {
                        ...current.draft.thresholds.similarity,
                        warn_at: nextValue,
                      },
                    },
                  },
                }))}
              />
            </label>

            <label className="cl-label">
              Similarity block at
              <input
                min="0"
                max="1"
                step="0.01"
                type="number"
                value={selectedRecord.draft.thresholds.similarity.block_at}
                onChange={handleNumberChange((current, nextValue) => ({
                  ...current,
                  draft: {
                    ...current.draft,
                    thresholds: {
                      ...current.draft.thresholds,
                      similarity: {
                        ...current.draft.thresholds.similarity,
                        block_at: nextValue,
                      },
                    },
                  },
                }))}
              />
            </label>

            <label className="cl-label">
              Minimum QA score
              <input
                min="0"
                max="1"
                step="0.01"
                type="number"
                value={selectedRecord.draft.thresholds.min_quality_score}
                onChange={handleNumberChange((current, nextValue) => ({
                  ...current,
                  draft: {
                    ...current.draft,
                    thresholds: {
                      ...current.draft.thresholds,
                      min_quality_score: nextValue,
                    },
                  },
                }))}
              />
            </label>

            <SectionError errors={fieldErrors} field="thresholds" />
          </section>
        </div>

        <div className="cl-button-row">
          <button disabled={pending} className="cl-button is-primary" type="submit">
            {pending ? 'Saving...' : 'Save policy'}
          </button>
          <button disabled={pending} className="cl-button" type="button" onClick={resetSelectedDraft}>
            Reset
          </button>
        </div>

        <FeedbackPanel feedback={feedback} />
      </form>
    </div>
  );
}
