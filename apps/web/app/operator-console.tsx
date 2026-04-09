'use client';

import {
  default as React,
  useState,
  type ChangeEvent,
  type CSSProperties,
  type Dispatch,
  type FormEvent,
  type SetStateAction,
} from 'react';

import type { ReelResponse, RunResponse } from '@shared/types';

import {
  DEFAULT_API_BASE_URL,
  HUMAN_BOUNDARY_COPY,
  createMarkPostedSubmission,
  createReelReviewSubmission,
  createReelTriggerSubmission,
  createRunTriggerSubmission,
  type FieldErrors,
  type MarkPostedField,
  type MarkPostedFormValues,
  type ReelReviewField,
  type ReelReviewFormValues,
  type ReelTriggerField,
  type ReelTriggerFormValues,
  type RunTriggerField,
  type RunTriggerFormValues,
  type SubmissionFeedback,
  submitOperatorRequest,
} from './operator-console.helpers';

const pageStyle: CSSProperties = {
  minHeight: '100vh',
  padding: '32px 20px 56px',
  background:
    'radial-gradient(circle at top left, rgba(255, 214, 170, 0.95), transparent 35%), linear-gradient(180deg, #fff8ef 0%, #f3efe7 100%)',
  color: '#1f1d19',
  fontFamily: "Georgia, 'Times New Roman', serif",
};

const shellStyle: CSSProperties = {
  maxWidth: 1180,
  margin: '0 auto',
  display: 'grid',
  gap: 24,
};

const heroStyle: CSSProperties = {
  display: 'grid',
  gap: 12,
  padding: 28,
  borderRadius: 24,
  border: '1px solid rgba(63, 51, 36, 0.15)',
  background: 'rgba(255, 252, 247, 0.92)',
  boxShadow: '0 20px 45px rgba(74, 56, 31, 0.08)',
};

const gridStyle: CSSProperties = {
  display: 'grid',
  gap: 18,
  gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
};

const cardStyle: CSSProperties = {
  display: 'grid',
  gap: 14,
  padding: 20,
  borderRadius: 22,
  border: '1px solid rgba(63, 51, 36, 0.12)',
  background: 'rgba(255, 255, 255, 0.9)',
  boxShadow: '0 14px 35px rgba(74, 56, 31, 0.06)',
};

const labelStyle: CSSProperties = {
  display: 'grid',
  gap: 6,
  fontSize: 14,
  fontWeight: 600,
};

const fieldStyle: CSSProperties = {
  width: '100%',
  padding: '10px 12px',
  borderRadius: 12,
  border: '1px solid rgba(72, 60, 44, 0.2)',
  background: '#fffdfa',
  color: '#1f1d19',
  fontSize: 14,
  fontFamily: "Consolas, 'Courier New', monospace",
};

const helperTextStyle: CSSProperties = {
  fontSize: 12,
  lineHeight: 1.5,
  color: '#5d5345',
  margin: 0,
};

const errorTextStyle: CSSProperties = {
  fontSize: 12,
  lineHeight: 1.5,
  color: '#8e1b1b',
  margin: 0,
};

const codeStyle: CSSProperties = {
  fontFamily: "Consolas, 'Courier New', monospace",
  fontSize: 12,
  padding: '3px 6px',
  borderRadius: 8,
  background: 'rgba(53, 44, 33, 0.08)',
};

const actionRowStyle: CSSProperties = {
  display: 'flex',
  flexWrap: 'wrap',
  gap: 10,
};

const primaryButtonStyle: CSSProperties = {
  border: 'none',
  borderRadius: 999,
  padding: '11px 18px',
  background: '#222f3c',
  color: '#fffaf2',
  fontWeight: 700,
  cursor: 'pointer',
};

const secondaryButtonStyle: CSSProperties = {
  ...primaryButtonStyle,
  background: '#6d5637',
};

const dangerButtonStyle: CSSProperties = {
  ...primaryButtonStyle,
  background: '#8b2d2d',
};

const feedbackShellStyle: CSSProperties = {
  display: 'grid',
  gap: 8,
  padding: 14,
  borderRadius: 16,
  border: '1px solid rgba(72, 60, 44, 0.15)',
};

const responsePreStyle: CSSProperties = {
  margin: 0,
  maxHeight: 220,
  overflow: 'auto',
  padding: 12,
  borderRadius: 12,
  background: '#17130f',
  color: '#f7efe5',
  fontSize: 12,
  fontFamily: "Consolas, 'Courier New', monospace",
};

const checkboxLabelStyle: CSSProperties = {
  display: 'flex',
  gap: 10,
  alignItems: 'flex-start',
  fontSize: 14,
  lineHeight: 1.5,
};

function emptyFeedback<TPayload>(): SubmissionFeedback<TPayload> {
  return { kind: 'idle' };
}

type StringFieldKey<TForm> = {
  [TKey in keyof TForm]: TForm[TKey] extends string ? TKey : never;
}[keyof TForm];

function updateField<TForm extends object, TKey extends StringFieldKey<TForm>>(
  setForm: Dispatch<SetStateAction<TForm>>,
  key: TKey,
) {
  return (event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
    const value = event.target.value as TForm[TKey];
    setForm((current) => ({
      ...current,
      [key]: value,
    }));
  };
}

function FeedbackPanel<TPayload>({ feedback }: { feedback: SubmissionFeedback<TPayload> }) {
  if (feedback.kind === 'idle') {
    return null;
  }

  const tone =
    feedback.kind === 'error'
      ? {
          background: 'rgba(255, 238, 234, 0.9)',
          borderColor: 'rgba(157, 45, 45, 0.18)',
        }
      : feedback.kind === 'pending'
        ? {
            background: 'rgba(242, 236, 223, 0.92)',
            borderColor: 'rgba(90, 74, 49, 0.16)',
          }
        : {
            background: 'rgba(232, 247, 237, 0.95)',
            borderColor: 'rgba(44, 115, 77, 0.18)',
          };

  return (
    <div style={{ ...feedbackShellStyle, ...tone }}>
      {feedback.title ? <strong>{feedback.title}</strong> : null}
      {feedback.message ? (
        <p style={{ ...helperTextStyle, margin: 0 }}>{feedback.message}</p>
      ) : null}
      {feedback.route ? (
        <p style={{ ...helperTextStyle, margin: 0 }}>
          Audited route: <code style={codeStyle}>POST {feedback.route}</code>
        </p>
      ) : null}
      {feedback.details && feedback.details.length > 0 ? (
        <ul style={{ margin: 0, paddingLeft: 18 }}>
          {feedback.details.map((detail) => (
            <li key={detail} style={helperTextStyle}>
              {detail}
            </li>
          ))}
        </ul>
      ) : null}
      {feedback.payload ? (
        <pre style={responsePreStyle}>{JSON.stringify(feedback.payload, null, 2)}</pre>
      ) : null}
    </div>
  );
}

function FieldError<TField extends string>({
  fieldErrors,
  field,
}: {
  fieldErrors: FieldErrors<TField>;
  field: TField;
}) {
  const message = fieldErrors[field];
  if (!message) {
    return null;
  }
  return <p style={errorTextStyle}>{message}</p>;
}

export function OperatorConsole() {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? DEFAULT_API_BASE_URL;

  const [runForm, setRunForm] = useState<RunTriggerFormValues>({
    orgId: '',
    actorId: '',
    workflowKey: 'daily_reel_factory',
    inputParamsText: '{\n  "page_limit": 3\n}',
    metadataText: '{\n  "source": "web-operator-console"\n}',
    idempotencyKey: '',
  });
  const [runErrors, setRunErrors] = useState<FieldErrors<RunTriggerField>>({});
  const [runFeedback, setRunFeedback] = useState<SubmissionFeedback<RunResponse>>(emptyFeedback);
  const [runPending, setRunPending] = useState(false);

  const [reelTriggerForm, setReelTriggerForm] = useState<ReelTriggerFormValues>({
    orgId: '',
    pageId: '',
    reelId: '',
    actorId: '',
    inputParamsText: '{\n  "priority": "high"\n}',
    metadataText: '{\n  "source": "web-operator-console"\n}',
    idempotencyKey: '',
  });
  const [reelTriggerErrors, setReelTriggerErrors] = useState<FieldErrors<ReelTriggerField>>({});
  const [reelTriggerFeedback, setReelTriggerFeedback] =
    useState<SubmissionFeedback<RunResponse>>(emptyFeedback);
  const [reelTriggerPending, setReelTriggerPending] = useState(false);

  const [reviewForm, setReviewForm] = useState<ReelReviewFormValues>({
    orgId: '',
    pageId: '',
    reelId: '',
    actorId: '',
  });
  const [reviewErrors, setReviewErrors] = useState<FieldErrors<ReelReviewField>>({});
  const [reviewFeedback, setReviewFeedback] =
    useState<SubmissionFeedback<ReelResponse>>(emptyFeedback);
  const [reviewPending, setReviewPending] = useState(false);

  const [markPostedForm, setMarkPostedForm] = useState<MarkPostedFormValues>({
    orgId: '',
    pageId: '',
    reelId: '',
    actorId: '',
    manualConfirmation: false,
  });
  const [markPostedErrors, setMarkPostedErrors] = useState<FieldErrors<MarkPostedField>>({});
  const [markPostedFeedback, setMarkPostedFeedback] =
    useState<SubmissionFeedback<ReelResponse>>(emptyFeedback);
  const [markPostedPending, setMarkPostedPending] = useState(false);

  async function handleRunSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const submission = createRunTriggerSubmission(runForm);
    if (!submission.ok) {
      setRunErrors(submission.fieldErrors);
      setRunFeedback({
        kind: 'error',
        title: 'Run trigger validation failed',
        details: submission.summary,
      });
      return;
    }

    setRunErrors({});
    setRunPending(true);
    setRunFeedback({
      kind: 'pending',
      title: 'Submitting run trigger',
      message: 'The console is sending a manual workflow trigger to the audited API route.',
      route: submission.value.actionPath,
    });
    const response = await submitOperatorRequest<RunResponse>(apiBaseUrl, submission.value);
    setRunFeedback(response);
    setRunPending(false);
  }

  async function handleReelTriggerSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const submission = createReelTriggerSubmission(reelTriggerForm);
    if (!submission.ok) {
      setReelTriggerErrors(submission.fieldErrors);
      setReelTriggerFeedback({
        kind: 'error',
        title: 'Reel trigger validation failed',
        details: submission.summary,
      });
      return;
    }

    setReelTriggerErrors({});
    setReelTriggerPending(true);
    setReelTriggerFeedback({
      kind: 'pending',
      title: 'Submitting reel trigger',
      message: 'The console is queuing a reel-processing run through the audited trigger route.',
      route: submission.value.actionPath,
    });
    const response = await submitOperatorRequest<RunResponse>(apiBaseUrl, submission.value);
    setReelTriggerFeedback(response);
    setReelTriggerPending(false);
  }

  async function handleReviewAction(action: 'approve' | 'archive') {
    const submission = createReelReviewSubmission(reviewForm, action);
    if (!submission.ok) {
      setReviewErrors(submission.fieldErrors);
      setReviewFeedback({
        kind: 'error',
        title: 'Human review validation failed',
        details: submission.summary,
      });
      return;
    }

    setReviewErrors({});
    setReviewPending(true);
    setReviewFeedback({
      kind: 'pending',
      title: action === 'approve' ? 'Recording approval' : 'Archiving reel',
      message: 'Only generated reels in the ready state can pass this human review step.',
      route: submission.value.actionPath,
    });
    const response = await submitOperatorRequest<ReelResponse>(apiBaseUrl, submission.value);
    setReviewFeedback(response);
    setReviewPending(false);
  }

  async function handleMarkPostedSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const submission = createMarkPostedSubmission(markPostedForm);
    if (!submission.ok) {
      setMarkPostedErrors(submission.fieldErrors);
      setMarkPostedFeedback({
        kind: 'error',
        title: 'Human posting validation failed',
        details: submission.summary,
      });
      return;
    }

    setMarkPostedErrors({});
    setMarkPostedPending(true);
    setMarkPostedFeedback({
      kind: 'pending',
      title: 'Recording human posting',
      message:
        'This does not publish a reel. It only records that a human operator already posted it.',
      route: submission.value.actionPath,
    });
    const response = await submitOperatorRequest<ReelResponse>(apiBaseUrl, submission.value);
    setMarkPostedFeedback(response);
    setMarkPostedPending(false);
  }

  return (
    <main style={pageStyle}>
      <div style={shellStyle}>
        <section style={heroStyle}>
          <p
            style={{
              margin: 0,
              fontSize: 12,
              letterSpacing: '0.14em',
              textTransform: 'uppercase',
              color: '#715534',
              fontWeight: 700,
            }}
          >
            Content Lab Operator Console
          </p>
          <h1 style={{ margin: 0, fontSize: 'clamp(2.25rem, 4vw, 4.25rem)', lineHeight: 1.05 }}>
            Trigger work, review reels, and record manual posting without crossing the human
            boundary.
          </h1>
          <p style={{ margin: 0, fontSize: 18, lineHeight: 1.6, maxWidth: 920 }}>
            {HUMAN_BOUNDARY_COPY}
          </p>
          <p style={{ ...helperTextStyle, fontSize: 13 }}>
            API base URL: <code style={codeStyle}>{apiBaseUrl}</code>
          </p>
        </section>

        <section style={gridStyle}>
          <form style={cardStyle} onSubmit={handleRunSubmit}>
            <div style={{ display: 'grid', gap: 6 }}>
              <h2 style={{ margin: 0, fontSize: 28 }}>Trigger Run</h2>
              <p style={{ ...helperTextStyle, fontSize: 14 }}>
                Use this for explicit operator-started workflows. The UI sends a manual trigger to{' '}
                <code style={codeStyle}>POST /orgs/{'{org_id}'}/runs</code>.
              </p>
            </div>

            <label style={labelStyle}>
              Org ID
              <input
                style={fieldStyle}
                value={runForm.orgId}
                onChange={updateField(setRunForm, 'orgId')}
              />
              <FieldError fieldErrors={runErrors} field="orgId" />
            </label>

            <label style={labelStyle}>
              Operator Actor ID
              <input
                style={fieldStyle}
                value={runForm.actorId}
                onChange={updateField(setRunForm, 'actorId')}
                placeholder="operator:queue-manager"
              />
              <p style={helperTextStyle}>
                Sent as the audited <code style={codeStyle}>X-Actor-Id</code> header.
              </p>
              <FieldError fieldErrors={runErrors} field="actorId" />
            </label>

            <label style={labelStyle}>
              Workflow Key
              <select
                style={fieldStyle}
                value={runForm.workflowKey}
                onChange={updateField(setRunForm, 'workflowKey')}
              >
                <option value="daily_reel_factory">daily_reel_factory</option>
                <option value="process_reel">process_reel</option>
              </select>
              <FieldError fieldErrors={runErrors} field="workflowKey" />
            </label>

            <label style={labelStyle}>
              Input Params JSON
              <textarea
                style={{ ...fieldStyle, minHeight: 120 }}
                value={runForm.inputParamsText}
                onChange={updateField(setRunForm, 'inputParamsText')}
              />
              <FieldError fieldErrors={runErrors} field="inputParamsText" />
            </label>

            <label style={labelStyle}>
              Metadata JSON
              <textarea
                style={{ ...fieldStyle, minHeight: 110 }}
                value={runForm.metadataText}
                onChange={updateField(setRunForm, 'metadataText')}
              />
              <p style={helperTextStyle}>Optional client metadata lands in the run audit trail.</p>
              <FieldError fieldErrors={runErrors} field="metadataText" />
            </label>

            <label style={labelStyle}>
              Idempotency Key
              <input
                style={fieldStyle}
                value={runForm.idempotencyKey}
                onChange={updateField(setRunForm, 'idempotencyKey')}
                placeholder="factory-batch-001"
              />
              <FieldError fieldErrors={runErrors} field="idempotencyKey" />
            </label>

            <div style={actionRowStyle}>
              <button type="submit" style={primaryButtonStyle} disabled={runPending}>
                {runPending ? 'Submitting...' : 'Trigger Run'}
              </button>
            </div>

            <FeedbackPanel feedback={runFeedback} />
          </form>

          <form style={cardStyle} onSubmit={handleReelTriggerSubmit}>
            <div style={{ display: 'grid', gap: 6 }}>
              <h2 style={{ margin: 0, fontSize: 28 }}>Trigger Reel</h2>
              <p style={{ ...helperTextStyle, fontSize: 14 }}>
                This queues the audited reel-processing route{' '}
                <code style={codeStyle}>
                  POST /orgs/{'{org_id}'}/pages/{'{page_id}'}/reels/{'{reel_id}'}/trigger
                </code>
                .
              </p>
            </div>

            <label style={labelStyle}>
              Org ID
              <input
                style={fieldStyle}
                value={reelTriggerForm.orgId}
                onChange={updateField(setReelTriggerForm, 'orgId')}
              />
              <FieldError fieldErrors={reelTriggerErrors} field="orgId" />
            </label>

            <label style={labelStyle}>
              Page ID
              <input
                style={fieldStyle}
                value={reelTriggerForm.pageId}
                onChange={updateField(setReelTriggerForm, 'pageId')}
              />
              <FieldError fieldErrors={reelTriggerErrors} field="pageId" />
            </label>

            <label style={labelStyle}>
              Reel ID
              <input
                style={fieldStyle}
                value={reelTriggerForm.reelId}
                onChange={updateField(setReelTriggerForm, 'reelId')}
              />
              <FieldError fieldErrors={reelTriggerErrors} field="reelId" />
            </label>

            <label style={labelStyle}>
              Operator Actor ID
              <input
                style={fieldStyle}
                value={reelTriggerForm.actorId}
                onChange={updateField(setReelTriggerForm, 'actorId')}
                placeholder="operator:queue-manager"
              />
              <FieldError fieldErrors={reelTriggerErrors} field="actorId" />
            </label>

            <label style={labelStyle}>
              Input Params JSON
              <textarea
                style={{ ...fieldStyle, minHeight: 120 }}
                value={reelTriggerForm.inputParamsText}
                onChange={updateField(setReelTriggerForm, 'inputParamsText')}
              />
              <p style={helperTextStyle}>
                Reserved keys like <code style={codeStyle}>org_id</code> and{' '}
                <code style={codeStyle}>reel_id</code> are blocked in the UI before the request is
                sent.
              </p>
              <FieldError fieldErrors={reelTriggerErrors} field="inputParamsText" />
            </label>

            <label style={labelStyle}>
              Metadata JSON
              <textarea
                style={{ ...fieldStyle, minHeight: 110 }}
                value={reelTriggerForm.metadataText}
                onChange={updateField(setReelTriggerForm, 'metadataText')}
              />
              <FieldError fieldErrors={reelTriggerErrors} field="metadataText" />
            </label>

            <label style={labelStyle}>
              Idempotency Key
              <input
                style={fieldStyle}
                value={reelTriggerForm.idempotencyKey}
                onChange={updateField(setReelTriggerForm, 'idempotencyKey')}
                placeholder="process-reel-001"
              />
              <FieldError fieldErrors={reelTriggerErrors} field="idempotencyKey" />
            </label>

            <div style={actionRowStyle}>
              <button type="submit" style={secondaryButtonStyle} disabled={reelTriggerPending}>
                {reelTriggerPending ? 'Submitting...' : 'Trigger Reel'}
              </button>
            </div>

            <FeedbackPanel feedback={reelTriggerFeedback} />
          </form>

          <section style={cardStyle}>
            <div style={{ display: 'grid', gap: 6 }}>
              <h2 style={{ margin: 0, fontSize: 28 }}>Human Review</h2>
              <p style={{ ...helperTextStyle, fontSize: 14 }}>
                Approval and archive are explicit human-review actions only. They map to{' '}
                <code style={codeStyle}>/approve</code> and <code style={codeStyle}>/archive</code>{' '}
                on a generated reel.
              </p>
            </div>

            <label style={labelStyle}>
              Org ID
              <input
                style={fieldStyle}
                value={reviewForm.orgId}
                onChange={updateField(setReviewForm, 'orgId')}
              />
              <FieldError fieldErrors={reviewErrors} field="orgId" />
            </label>

            <label style={labelStyle}>
              Page ID
              <input
                style={fieldStyle}
                value={reviewForm.pageId}
                onChange={updateField(setReviewForm, 'pageId')}
              />
              <FieldError fieldErrors={reviewErrors} field="pageId" />
            </label>

            <label style={labelStyle}>
              Reel ID
              <input
                style={fieldStyle}
                value={reviewForm.reelId}
                onChange={updateField(setReviewForm, 'reelId')}
              />
              <FieldError fieldErrors={reviewErrors} field="reelId" />
            </label>

            <label style={labelStyle}>
              Reviewer Actor ID
              <input
                style={fieldStyle}
                value={reviewForm.actorId}
                onChange={updateField(setReviewForm, 'actorId')}
                placeholder="operator:reviewer"
              />
              <FieldError fieldErrors={reviewErrors} field="actorId" />
            </label>

            <div style={actionRowStyle}>
              <button
                type="button"
                style={secondaryButtonStyle}
                disabled={reviewPending}
                onClick={() => void handleReviewAction('approve')}
              >
                {reviewPending ? 'Submitting...' : 'Approve Reel'}
              </button>
              <button
                type="button"
                style={dangerButtonStyle}
                disabled={reviewPending}
                onClick={() => void handleReviewAction('archive')}
              >
                {reviewPending ? 'Submitting...' : 'Archive Reel'}
              </button>
            </div>

            <FeedbackPanel feedback={reviewFeedback} />
          </section>

          <form style={cardStyle} onSubmit={handleMarkPostedSubmit}>
            <div style={{ display: 'grid', gap: 6 }}>
              <h2 style={{ margin: 0, fontSize: 28 }}>Human Posting</h2>
              <p style={{ ...helperTextStyle, fontSize: 14 }}>
                This form never publishes to a channel. It only records manual posting through{' '}
                <code style={codeStyle}>
                  POST /orgs/{'{org_id}'}/pages/{'{page_id}'}/reels/{'{reel_id}'}/mark-posted
                </code>
                .
              </p>
            </div>

            <label style={labelStyle}>
              Org ID
              <input
                style={fieldStyle}
                value={markPostedForm.orgId}
                onChange={updateField(setMarkPostedForm, 'orgId')}
              />
              <FieldError fieldErrors={markPostedErrors} field="orgId" />
            </label>

            <label style={labelStyle}>
              Page ID
              <input
                style={fieldStyle}
                value={markPostedForm.pageId}
                onChange={updateField(setMarkPostedForm, 'pageId')}
              />
              <FieldError fieldErrors={markPostedErrors} field="pageId" />
            </label>

            <label style={labelStyle}>
              Reel ID
              <input
                style={fieldStyle}
                value={markPostedForm.reelId}
                onChange={updateField(setMarkPostedForm, 'reelId')}
              />
              <FieldError fieldErrors={markPostedErrors} field="reelId" />
            </label>

            <label style={labelStyle}>
              Publisher Actor ID
              <input
                style={fieldStyle}
                value={markPostedForm.actorId}
                onChange={updateField(setMarkPostedForm, 'actorId')}
                placeholder="operator:publisher"
              />
              <p style={helperTextStyle}>
                The API records <code style={codeStyle}>posted_by</code> from this header and stamps
                the posting time server-side.
              </p>
              <FieldError fieldErrors={markPostedErrors} field="actorId" />
            </label>

            <label style={checkboxLabelStyle}>
              <input
                type="checkbox"
                checked={markPostedForm.manualConfirmation}
                onChange={(event) =>
                  setMarkPostedForm((current) => ({
                    ...current,
                    manualConfirmation: event.target.checked,
                  }))
                }
              />
              <span>I confirm a human operator already posted this reel outside Content Lab.</span>
            </label>
            <FieldError fieldErrors={markPostedErrors} field="manualConfirmation" />

            <div style={actionRowStyle}>
              <button type="submit" style={primaryButtonStyle} disabled={markPostedPending}>
                {markPostedPending ? 'Submitting...' : 'Mark Posted'}
              </button>
            </div>

            <FeedbackPanel feedback={markPostedFeedback} />
          </form>
        </section>
      </div>
    </main>
  );
}
