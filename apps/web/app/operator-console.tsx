'use client';

import React from 'react';
import { useEffect, useState, type ChangeEvent, type Dispatch, type FormEvent, type SetStateAction } from 'react';
import { useSearchParams } from 'next/navigation';

import type { ReelResponse, RunResponse } from '@shared/types';

import { DetailFrame, LinkAction, MetaGrid, SectionCard } from './_components/detail-ui';
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
    setForm((current) => ({ ...current, [key]: value }));
  };
}

function FeedbackPanel<TPayload>({ feedback }: { feedback: SubmissionFeedback<TPayload> }) {
  if (feedback.kind === 'idle') {
    return null;
  }

  const toneClass =
    feedback.kind === 'success'
      ? 'cl-feedback is-success'
      : feedback.kind === 'error'
        ? 'cl-feedback is-error'
        : 'cl-feedback is-pending';

  return (
    <div className={toneClass}>
      {feedback.title ? <strong>{feedback.title}</strong> : null}
      {feedback.message ? <p className="cl-field-note">{feedback.message}</p> : null}
      {feedback.route ? (
        <p className="cl-field-note">
          Audited route: <code className="cl-code">POST {feedback.route}</code>
        </p>
      ) : null}
      {feedback.details && feedback.details.length > 0 ? (
        <ul className="cl-compact">
          {feedback.details.map((detail) => (
            <li key={detail} className="cl-field-note">
              {detail}
            </li>
          ))}
        </ul>
      ) : null}
      {feedback.payload ? <pre className="cl-json">{JSON.stringify(feedback.payload, null, 2)}</pre> : null}
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
  return message ? <p className="cl-field-error">{message}</p> : null;
}

export function OperatorConsole({
  defaultApiBaseUrl = DEFAULT_API_BASE_URL,
  defaultOrgId = null,
}: {
  defaultApiBaseUrl?: string;
  defaultOrgId?: string | null;
}) {
  const searchParams = useSearchParams();
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? defaultApiBaseUrl;
  const seedOrgId = searchParams.get('orgId') ?? defaultOrgId ?? '';
  const seedPageId = searchParams.get('pageId') ?? '';
  const seedReelId = searchParams.get('reelId') ?? '';

  const [runForm, setRunForm] = useState<RunTriggerFormValues>({
    orgId: seedOrgId,
    actorId: '',
    workflowKey: 'daily_reel_factory',
    inputParamsText: '{\n  "page_limit": 3\n}',
    metadataText: '{\n  "source": "web-operator-workspace"\n}',
    idempotencyKey: '',
  });
  const [runErrors, setRunErrors] = useState<FieldErrors<RunTriggerField>>({});
  const [runFeedback, setRunFeedback] = useState<SubmissionFeedback<RunResponse>>(emptyFeedback);
  const [runPending, setRunPending] = useState(false);

  const [reelTriggerForm, setReelTriggerForm] = useState<ReelTriggerFormValues>({
    orgId: seedOrgId,
    pageId: seedPageId,
    reelId: seedReelId,
    actorId: '',
    inputParamsText: '{\n  "priority": "high"\n}',
    metadataText: '{\n  "source": "web-operator-workspace"\n}',
    idempotencyKey: '',
  });
  const [reelTriggerErrors, setReelTriggerErrors] = useState<FieldErrors<ReelTriggerField>>({});
  const [reelTriggerFeedback, setReelTriggerFeedback] = useState<SubmissionFeedback<RunResponse>>(emptyFeedback);
  const [reelTriggerPending, setReelTriggerPending] = useState(false);

  const [reviewForm, setReviewForm] = useState<ReelReviewFormValues>({
    orgId: seedOrgId,
    pageId: seedPageId,
    reelId: seedReelId,
    actorId: '',
  });
  const [reviewErrors, setReviewErrors] = useState<FieldErrors<ReelReviewField>>({});
  const [reviewFeedback, setReviewFeedback] = useState<SubmissionFeedback<ReelResponse>>(emptyFeedback);
  const [reviewPending, setReviewPending] = useState(false);

  const [markPostedForm, setMarkPostedForm] = useState<MarkPostedFormValues>({
    orgId: seedOrgId,
    pageId: seedPageId,
    reelId: seedReelId,
    actorId: '',
    manualConfirmation: false,
  });
  const [markPostedErrors, setMarkPostedErrors] = useState<FieldErrors<MarkPostedField>>({});
  const [markPostedFeedback, setMarkPostedFeedback] = useState<SubmissionFeedback<ReelResponse>>(emptyFeedback);
  const [markPostedPending, setMarkPostedPending] = useState(false);

  useEffect(() => {
    const orgId = searchParams.get('orgId') ?? '';
    const pageId = searchParams.get('pageId') ?? '';
    const reelId = searchParams.get('reelId') ?? '';

    setRunForm((current) => ({ ...current, orgId: orgId || current.orgId }));
    setReelTriggerForm((current) => ({ ...current, orgId: orgId || current.orgId, pageId: pageId || current.pageId, reelId: reelId || current.reelId }));
    setReviewForm((current) => ({ ...current, orgId: orgId || current.orgId, pageId: pageId || current.pageId, reelId: reelId || current.reelId }));
    setMarkPostedForm((current) => ({ ...current, orgId: orgId || current.orgId, pageId: pageId || current.pageId, reelId: reelId || current.reelId }));
  }, [searchParams]);

  async function handleRunSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const submission = createRunTriggerSubmission(runForm);
    if (!submission.ok) {
      setRunErrors(submission.fieldErrors);
      setRunFeedback({ kind: 'error', title: 'Run trigger validation failed', details: submission.summary });
      return;
    }

    setRunErrors({});
    setRunPending(true);
    setRunFeedback({
      kind: 'pending',
      title: 'Submitting workflow start',
      message: 'This sends a manual workflow request to the audited run route.',
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
      setReelTriggerFeedback({ kind: 'error', title: 'Reel processing validation failed', details: submission.summary });
      return;
    }

    setReelTriggerErrors({});
    setReelTriggerPending(true);
    setReelTriggerFeedback({
      kind: 'pending',
      title: 'Submitting reel processing',
      message: 'This queues the reel-processing route with explicit audited inputs.',
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
      setReviewFeedback({ kind: 'error', title: 'Human review validation failed', details: submission.summary });
      return;
    }

    setReviewErrors({});
    setReviewPending(true);
    setReviewFeedback({
      kind: 'pending',
      title: action === 'approve' ? 'Recording approval' : 'Archiving reel',
      message: 'This human review step never posts content to a platform.',
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
      setMarkPostedFeedback({ kind: 'error', title: 'Manual posting validation failed', details: submission.summary });
      return;
    }

    setMarkPostedErrors({});
    setMarkPostedPending(true);
    setMarkPostedFeedback({
      kind: 'pending',
      title: 'Recording manual posting',
      message: 'This records that a human posted externally. It does not publish content for you.',
      route: submission.value.actionPath,
    });
    const response = await submitOperatorRequest<ReelResponse>(apiBaseUrl, submission.value);
    setMarkPostedFeedback(response);
    setMarkPostedPending(false);
  }

  return (
    <DetailFrame
      breadcrumbs={[{ label: 'Home', href: '/' }, { label: 'Actions' }]}
      eyebrow="Actions"
      title="Start work, review output, and record manual outcomes"
      subtitle="This workspace turns backend routes into task-based actions. Use it to start workflows, process a specific reel, approve or archive during human review, and record manual posting after a person has already posted externally."
      cuesSummary="Choose the action that matches the job, use the prefilled IDs when they exist, and inspect the result after each submission."
      actions={<LinkAction href="/queue" label="Open Queue" tone="secondary" />}
      cues={[
        { label: 'What this page is for', value: 'Run the operator actions that move work forward without dropping into raw API usage.' },
        { label: 'What you can do here', value: 'Launch workflows, process a reel, handle human review, and record manual posting with audited headers.' },
        { label: 'What comes next', value: 'After any action succeeds, move back to Runs, Reels, Queue, or detail pages to inspect the outcome.' },
      ]}
    >
      <SectionCard title="Action workspace summary" description="These are task-based actions, not hidden endpoints. If you arrived from another route, IDs from that page are prefilled here when possible.">
        <MetaGrid
          items={[
            { label: 'API base URL', value: apiBaseUrl },
            { label: 'Prefilled org ID', value: seedOrgId || 'None' },
            { label: 'Prefilled page ID', value: seedPageId || 'None' },
            { label: 'Prefilled reel ID', value: seedReelId || 'None' },
          ]}
        />
        <p className="cl-panel-description">{HUMAN_BOUNDARY_COPY}</p>
      </SectionCard>

      <SectionCard
        title="Before you use these forms"
        description="You do not need every form every day. Pick the one that matches the job you are trying to do."
      >
        <MetaGrid
          items={[
            {
              label: 'Use Start a workflow',
              value: 'When you want to kick off a larger workflow for an org.',
            },
            {
              label: 'Use Process a specific reel',
              value: 'When you already know the reel you want to move forward.',
            },
            {
              label: 'Use Approve or archive',
              value: 'When a human reviewer has finished looking at the reel.',
            },
            {
              label: 'Use Record manual posting',
              value: 'Only after a person has already posted outside Content Lab.',
            },
          ]}
        />
      </SectionCard>

      <div className="cl-form-columns">
        <SectionCard title="Start a workflow" description="Use this when you want to kick off a manual workflow for an org.">
          <form className="cl-form-grid" onSubmit={handleRunSubmit}>
            <label className="cl-label">Org ID
              <input value={runForm.orgId} onChange={updateField(setRunForm, 'orgId')} />
              <p className="cl-field-note">This is the organization you are working inside.</p>
              <FieldError fieldErrors={runErrors} field="orgId" />
            </label>
            <label className="cl-label">Operator actor ID
              <input value={runForm.actorId} onChange={updateField(setRunForm, 'actorId')} placeholder="operator:queue-manager" />
              <p className="cl-field-note">Sent as the audited <code className="cl-code">X-Actor-Id</code> header.</p>
              <FieldError fieldErrors={runErrors} field="actorId" />
            </label>
            <label className="cl-label">Workflow key
              <select value={runForm.workflowKey} onChange={updateField(setRunForm, 'workflowKey')}>
                <option value="daily_reel_factory">daily_reel_factory</option>
                <option value="process_reel">process_reel</option>
              </select>
              <FieldError fieldErrors={runErrors} field="workflowKey" />
            </label>
            <label className="cl-label">Input params JSON
              <textarea value={runForm.inputParamsText} onChange={updateField(setRunForm, 'inputParamsText')} />
              <p className="cl-field-note">Use the starter example unless you already know the extra inputs this workflow expects.</p>
              <FieldError fieldErrors={runErrors} field="inputParamsText" />
            </label>
            <label className="cl-label">Metadata JSON
              <textarea value={runForm.metadataText} onChange={updateField(setRunForm, 'metadataText')} />
              <p className="cl-field-note">Use metadata for operator notes or trace context that should land in the audit trail.</p>
              <FieldError fieldErrors={runErrors} field="metadataText" />
            </label>
            <label className="cl-label">Idempotency key
              <input value={runForm.idempotencyKey} onChange={updateField(setRunForm, 'idempotencyKey')} placeholder="factory-batch-001" />
              <FieldError fieldErrors={runErrors} field="idempotencyKey" />
            </label>
            <div className="cl-button-row">
              <button type="submit" className="cl-button is-primary" disabled={runPending}>{runPending ? 'Submitting...' : 'Start workflow'}</button>
            </div>
            <FeedbackPanel feedback={runFeedback} />
          </form>
        </SectionCard>

        <SectionCard title="Process a specific reel" description="Use this when you already know the reel you want to process.">
          <form className="cl-form-grid" onSubmit={handleReelTriggerSubmit}>
            <label className="cl-label">Org ID
              <input value={reelTriggerForm.orgId} onChange={updateField(setReelTriggerForm, 'orgId')} />
              <p className="cl-field-note">The org the reel belongs to.</p>
              <FieldError fieldErrors={reelTriggerErrors} field="orgId" />
            </label>
            <label className="cl-label">Page ID
              <input value={reelTriggerForm.pageId} onChange={updateField(setReelTriggerForm, 'pageId')} />
              <p className="cl-field-note">The page the reel belongs to.</p>
              <FieldError fieldErrors={reelTriggerErrors} field="pageId" />
            </label>
            <label className="cl-label">Reel ID
              <input value={reelTriggerForm.reelId} onChange={updateField(setReelTriggerForm, 'reelId')} />
              <p className="cl-field-note">If you arrived from Reel detail or Queue, this may already be filled in.</p>
              <FieldError fieldErrors={reelTriggerErrors} field="reelId" />
            </label>
            <label className="cl-label">Operator actor ID
              <input value={reelTriggerForm.actorId} onChange={updateField(setReelTriggerForm, 'actorId')} placeholder="operator:queue-manager" />
              <FieldError fieldErrors={reelTriggerErrors} field="actorId" />
            </label>
            <label className="cl-label">Input params JSON
              <textarea value={reelTriggerForm.inputParamsText} onChange={updateField(setReelTriggerForm, 'inputParamsText')} />
              <p className="cl-field-note">Reserved keys like <code className="cl-code">org_id</code> and <code className="cl-code">reel_id</code> are blocked before submission.</p>
              <FieldError fieldErrors={reelTriggerErrors} field="inputParamsText" />
            </label>
            <label className="cl-label">Metadata JSON
              <textarea value={reelTriggerForm.metadataText} onChange={updateField(setReelTriggerForm, 'metadataText')} />
              <FieldError fieldErrors={reelTriggerErrors} field="metadataText" />
            </label>
            <label className="cl-label">Idempotency key
              <input value={reelTriggerForm.idempotencyKey} onChange={updateField(setReelTriggerForm, 'idempotencyKey')} placeholder="process-reel-001" />
              <FieldError fieldErrors={reelTriggerErrors} field="idempotencyKey" />
            </label>
            <div className="cl-button-row">
              <button type="submit" className="cl-button is-secondary" disabled={reelTriggerPending}>{reelTriggerPending ? 'Submitting...' : 'Process reel'}</button>
            </div>
            <FeedbackPanel feedback={reelTriggerFeedback} />
          </form>
        </SectionCard>

        <SectionCard title="Approve or archive" description="Use this after a human has reviewed the reel and made a decision.">
          <div className="cl-form-grid">
            <label className="cl-label">Org ID
              <input value={reviewForm.orgId} onChange={updateField(setReviewForm, 'orgId')} />
              <p className="cl-field-note">Use the same org, page, and reel IDs shown on the reel you reviewed.</p>
              <FieldError fieldErrors={reviewErrors} field="orgId" />
            </label>
            <label className="cl-label">Page ID
              <input value={reviewForm.pageId} onChange={updateField(setReviewForm, 'pageId')} />
              <FieldError fieldErrors={reviewErrors} field="pageId" />
            </label>
            <label className="cl-label">Reel ID
              <input value={reviewForm.reelId} onChange={updateField(setReviewForm, 'reelId')} />
              <FieldError fieldErrors={reviewErrors} field="reelId" />
            </label>
            <label className="cl-label">Reviewer actor ID
              <input value={reviewForm.actorId} onChange={updateField(setReviewForm, 'actorId')} placeholder="operator:reviewer" />
              <p className="cl-field-note">{HUMAN_BOUNDARY_COPY}</p>
              <FieldError fieldErrors={reviewErrors} field="actorId" />
            </label>
            <div className="cl-button-row">
              <button type="button" className="cl-button is-primary" disabled={reviewPending} onClick={() => void handleReviewAction('approve')}>{reviewPending ? 'Submitting...' : 'Approve reel'}</button>
              <button type="button" className="cl-button is-danger" disabled={reviewPending} onClick={() => void handleReviewAction('archive')}>{reviewPending ? 'Submitting...' : 'Archive reel'}</button>
            </div>
            <FeedbackPanel feedback={reviewFeedback} />
          </div>
        </SectionCard>

        <SectionCard title="Record manual posting" description="Use this only after a human has already posted the reel outside Content Lab.">
          <form className="cl-form-grid" onSubmit={handleMarkPostedSubmit}>
            <label className="cl-label">Org ID
              <input value={markPostedForm.orgId} onChange={updateField(setMarkPostedForm, 'orgId')} />
              <p className="cl-field-note">Keep these IDs aligned with the reel that was posted manually.</p>
              <FieldError fieldErrors={markPostedErrors} field="orgId" />
            </label>
            <label className="cl-label">Page ID
              <input value={markPostedForm.pageId} onChange={updateField(setMarkPostedForm, 'pageId')} />
              <FieldError fieldErrors={markPostedErrors} field="pageId" />
            </label>
            <label className="cl-label">Reel ID
              <input value={markPostedForm.reelId} onChange={updateField(setMarkPostedForm, 'reelId')} />
              <FieldError fieldErrors={markPostedErrors} field="reelId" />
            </label>
            <label className="cl-label">Publisher actor ID
              <input value={markPostedForm.actorId} onChange={updateField(setMarkPostedForm, 'actorId')} placeholder="operator:publisher" />
              <p className="cl-field-note">The API records who marked the reel posted and stamps the posting time server-side.</p>
              <FieldError fieldErrors={markPostedErrors} field="actorId" />
            </label>
            <label className="cl-checkbox">
              <input type="checkbox" checked={markPostedForm.manualConfirmation} onChange={(event) => setMarkPostedForm((current) => ({ ...current, manualConfirmation: event.target.checked }))} />
              <span>I confirm a human operator already posted this reel outside Content Lab.</span>
            </label>
            <FieldError fieldErrors={markPostedErrors} field="manualConfirmation" />
            <div className="cl-button-row">
              <button type="submit" className="cl-button is-primary" disabled={markPostedPending}>{markPostedPending ? 'Submitting...' : 'Record manual posting'}</button>
            </div>
            <FeedbackPanel feedback={markPostedFeedback} />
          </form>
        </SectionCard>
      </div>
    </DetailFrame>
  );
}
