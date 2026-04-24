'use client';

import React from 'react';
import { useRouter } from 'next/navigation';
import { useState, useTransition, type FormEvent } from 'react';

import type { PageCreate, PageOut } from '@shared/types';

type PageCreatePanelProps = {
  orgId: string | null;
};

type FeedbackState =
  | {
      tone: 'success' | 'error' | 'pending';
      message: string;
    }
  | null;

const DEFAULT_FORM = {
  platform: 'instagram',
  displayName: '',
  handle: '',
  externalPageId: '',
};

function normalizeOptional(value: string): string | null {
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

export function PageCreatePanel({ orgId }: PageCreatePanelProps) {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [feedback, setFeedback] = useState<FeedbackState>(null);
  const [form, setForm] = useState(DEFAULT_FORM);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!orgId) {
      setFeedback({
        tone: 'error',
        message: 'Choose a workspace org before creating a page.',
      });
      return;
    }

    const displayName = form.displayName.trim();
    if (displayName.length === 0) {
      setFeedback({
        tone: 'error',
        message: 'Enter a page display name first.',
      });
      return;
    }

    setFeedback({
      tone: 'pending',
      message: 'Creating page...',
    });

    const body: PageCreate = {
      platform: form.platform,
      display_name: displayName,
      external_page_id: normalizeOptional(form.externalPageId),
      handle: normalizeOptional(form.handle),
      ownership: 'owned',
    };

    try {
      const response = await fetch(`/api/orgs/${orgId}/pages`, {
        method: 'POST',
        headers: {
          Accept: 'application/json',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(body),
      });

      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
        setFeedback({
          tone: 'error',
          message: payload?.detail ?? 'The page could not be created.',
        });
        return;
      }

      const created = (await response.json()) as PageOut;
      setForm(DEFAULT_FORM);
      setFeedback({
        tone: 'success',
        message: `${created.display_name} was created and added to Pages.`,
      });
      startTransition(() => {
        router.refresh();
      });
    } catch (error) {
      setFeedback({
        tone: 'error',
        message: error instanceof Error ? error.message : 'The page could not be created.',
      });
    }
  }

  return (
    <form className="cl-form-grid" onSubmit={(event) => void handleSubmit(event)}>
      <div className="cl-form-columns">
        <label className="cl-label">
          Display name
          <input
            value={form.displayName}
            onChange={(event) => setForm((current) => ({ ...current, displayName: event.target.value }))}
            placeholder="Testing Page"
          />
          <p className="cl-field-note">Use the account name you want the operator workspace to show.</p>
        </label>

        <label className="cl-label">
          Platform
          <select
            value={form.platform}
            onChange={(event) => setForm((current) => ({ ...current, platform: event.target.value }))}
          >
            <option value="instagram">Instagram</option>
            <option value="tiktok">TikTok</option>
            <option value="youtube">YouTube</option>
            <option value="facebook">Facebook</option>
          </select>
          <p className="cl-field-note">Owned pages appear in the main Pages directory for this workspace org.</p>
        </label>
      </div>

      <div className="cl-form-columns">
        <label className="cl-label">
          Handle
          <input
            value={form.handle}
            onChange={(event) => setForm((current) => ({ ...current, handle: event.target.value }))}
            placeholder="@testing-page"
          />
          <p className="cl-field-note">Optional, but useful when you want the table to show the social handle.</p>
        </label>

        <label className="cl-label">
          External page ID
          <input
            value={form.externalPageId}
            onChange={(event) => setForm((current) => ({ ...current, externalPageId: event.target.value }))}
            placeholder="testing-page-01"
          />
          <p className="cl-field-note">Optional. Leave it blank unless you already know the platform-side ID.</p>
        </label>
      </div>

      <div className="cl-button-row">
        <button type="submit" className="cl-button is-primary" disabled={isPending}>
          {isPending ? 'Creating...' : 'Create page'}
        </button>
      </div>

      {feedback ? <div className={`cl-feedback is-${feedback.tone}`}><p className="cl-field-note">{feedback.message}</p></div> : null}
    </form>
  );
}
