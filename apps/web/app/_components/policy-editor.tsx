'use client';

import React, { useState, type CSSProperties, type ChangeEvent } from 'react';

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

const shellStyle: CSSProperties = {
  display: 'grid',
  gap: 18,
};

const pickerStyle: CSSProperties = {
  display: 'grid',
  gap: 12,
  padding: 16,
  borderRadius: 14,
  border: '1px solid #d9ddd4',
  backgroundColor: '#fbfbf9',
};

const metaGridStyle: CSSProperties = {
  display: 'grid',
  gap: 12,
  gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))',
};

const metaCardStyle: CSSProperties = {
  padding: 12,
  borderRadius: 12,
  border: '1px solid #e7e9e2',
  backgroundColor: '#ffffff',
};

const formGridStyle: CSSProperties = {
  display: 'grid',
  gap: 16,
  gridTemplateColumns: 'repeat(auto-fit, minmax(230px, 1fr))',
};

const sectionStyle: CSSProperties = {
  display: 'grid',
  gap: 12,
  padding: 16,
  borderRadius: 14,
  border: '1px solid #d9ddd4',
  backgroundColor: '#ffffff',
};

const labelStyle: CSSProperties = {
  display: 'grid',
  gap: 6,
  fontSize: '0.94rem',
  fontWeight: 600,
};

const fieldStyle: CSSProperties = {
  width: '100%',
  padding: '10px 12px',
  borderRadius: 10,
  border: '1px solid #c4cbc0',
  fontSize: '0.95rem',
};

const helpTextStyle: CSSProperties = {
  color: '#4f5b65',
  fontSize: '0.88rem',
  lineHeight: 1.5,
  margin: 0,
};

const errorTextStyle: CSSProperties = {
  color: '#7d2d23',
  fontSize: '0.88rem',
  lineHeight: 1.5,
  margin: 0,
};

const actionRowStyle: CSSProperties = {
  display: 'flex',
  flexWrap: 'wrap',
  gap: 10,
};

const primaryButtonStyle: CSSProperties = {
  border: 'none',
  borderRadius: '999px',
  backgroundColor: '#16202a',
  color: '#ffffff',
  cursor: 'pointer',
  fontWeight: 700,
  padding: '10px 16px',
};

const secondaryButtonStyle: CSSProperties = {
  ...primaryButtonStyle,
  backgroundColor: '#f0f3ee',
  border: '1px solid #c4cbc0',
  color: '#16202a',
};

const feedbackStyle: CSSProperties = {
  display: 'grid',
  gap: 8,
  padding: 14,
  borderRadius: 14,
  border: '1px solid #d9ddd4',
};

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

  const tone =
    feedback.kind === 'success'
      ? { backgroundColor: '#e7f4e3', borderColor: '#bbd9b7' }
      : feedback.kind === 'error'
        ? { backgroundColor: '#fde4e1', borderColor: '#edb7b0' }
        : { backgroundColor: '#fff0d6', borderColor: '#ebca8f' };

  return (
    <div style={{ ...feedbackStyle, ...tone }}>
      {feedback.title ? <strong>{feedback.title}</strong> : null}
      {feedback.message ? <p style={helpTextStyle}>{feedback.message}</p> : null}
      {feedback.route ? <p style={helpTextStyle}>Audited route: PATCH {feedback.route}</p> : null}
      {feedback.details && feedback.details.length > 0 ? (
        <ul style={{ margin: 0, paddingLeft: 18 }}>
          {feedback.details.map((detail) => (
            <li key={detail} style={helpTextStyle}>
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
  return message ? <p style={errorTextStyle}>{message}</p> : null;
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
    <div style={shellStyle}>
      <div style={pickerStyle}>
        <label style={labelStyle}>
          Page
          <select
            style={fieldStyle}
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

        <div style={metaGridStyle}>
          <div style={metaCardStyle}>
            <strong>{selectedRecord.page.displayName}</strong>
            <p style={helpTextStyle}>{selectedRecord.page.handle ?? 'Handle not set'}</p>
          </div>
          <div style={metaCardStyle}>
            <strong>Policy source</strong>
            <p style={helpTextStyle}>
              {selectedRecord.source === 'saved'
                ? 'Loaded from the page policy route.'
                : 'Default phase-1 guardrails ready to save.'}
            </p>
          </div>
          <div style={metaCardStyle}>
            <strong>Last saved</strong>
            <p style={helpTextStyle}>
              {formatTimestamp(selectedRecord.policy?.updated_at ?? null)}
            </p>
          </div>
          <div style={metaCardStyle}>
            <strong>Scope</strong>
            <p style={helpTextStyle}>page:{selectedRecord.page.id}</p>
          </div>
        </div>
      </div>

      <form style={shellStyle} onSubmit={handleSubmit}>
        <label style={labelStyle}>
          Operator Actor ID
          <input
            style={fieldStyle}
            value={actorId}
            onChange={(event) => setActorId(event.target.value)}
            placeholder="operator:policy-manager"
          />
          <p style={helpTextStyle}>
            The save action uses the audited <code>X-Actor-Id</code> header on the page-policy PATCH
            route.
          </p>
          <SectionError errors={fieldErrors} field="actorId" />
        </label>

        <div style={formGridStyle}>
          <section style={sectionStyle}>
            <div>
              <h3 style={{ margin: 0 }}>Mode ratios</h3>
              <p style={helpTextStyle}>
                These values must stay within 0.00 to 1.00 and sum to 1.00.
              </p>
            </div>

            <label style={labelStyle}>
              Exploit
              <input
                min="0"
                max="1"
                step="0.01"
                style={fieldStyle}
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

            <label style={labelStyle}>
              Explore
              <input
                min="0"
                max="1"
                step="0.01"
                style={fieldStyle}
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

            <label style={labelStyle}>
              Mutation
              <input
                min="0"
                max="1"
                step="0.01"
                style={fieldStyle}
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

            <label style={labelStyle}>
              Chaos
              <input
                min="0"
                max="1"
                step="0.01"
                style={fieldStyle}
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

          <section style={sectionStyle}>
            <div>
              <h3 style={{ margin: 0 }}>Budget guardrails</h3>
              <p style={helpTextStyle}>
                Per-run must stay below daily, and daily must stay below monthly.
              </p>
            </div>

            <label style={labelStyle}>
              Per-run USD limit
              <input
                min="0"
                step="0.01"
                style={fieldStyle}
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

            <label style={labelStyle}>
              Daily USD limit
              <input
                min="0"
                step="0.01"
                style={fieldStyle}
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

            <label style={labelStyle}>
              Monthly USD limit
              <input
                min="0"
                step="0.01"
                style={fieldStyle}
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

          <section style={sectionStyle}>
            <div>
              <h3 style={{ margin: 0 }}>Thresholds</h3>
              <p style={helpTextStyle}>
                Similarity warning must stay below the block threshold, and QA stays in the unit
                range.
              </p>
            </div>

            <label style={labelStyle}>
              Similarity warn at
              <input
                min="0"
                max="1"
                step="0.01"
                style={fieldStyle}
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

            <label style={labelStyle}>
              Similarity block at
              <input
                min="0"
                max="1"
                step="0.01"
                style={fieldStyle}
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

            <label style={labelStyle}>
              Minimum QA score
              <input
                min="0"
                max="1"
                step="0.01"
                style={fieldStyle}
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

        <div style={actionRowStyle}>
          <button disabled={pending} style={primaryButtonStyle} type="submit">
            {pending ? 'Saving...' : 'Save policy'}
          </button>
          <button
            disabled={pending}
            style={secondaryButtonStyle}
            type="button"
            onClick={resetSelectedDraft}
          >
            Reset
          </button>
        </div>

        <FeedbackPanel feedback={feedback} />
      </form>
    </div>
  );
}
