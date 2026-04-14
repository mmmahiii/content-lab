'use client';

import { useRouter } from 'next/navigation';
import { useState, useTransition, type FormEvent } from 'react';

import {
  describeOperatorContextSource,
  normalizeOrgId,
  type OperatorContextSource,
} from '../_lib/operator-context';

type WorkspaceOrgSwitcherProps = {
  initialOrgId: string | null;
  source: OperatorContextSource;
};

export function WorkspaceOrgSwitcher({
  initialOrgId,
  source,
}: WorkspaceOrgSwitcherProps) {
  const router = useRouter();
  const [value, setValue] = useState(initialOrgId ?? '');
  const [feedback, setFeedback] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  function refreshWorkspace(message: string) {
    setFeedback(message);
    startTransition(() => {
      router.refresh();
    });
  }

  async function handleSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const orgId = normalizeOrgId(value);

    if (!orgId) {
      setFeedback('Enter a full org UUID to save this workspace.');
      return;
    }

    const response = await fetch('/api/operator-context', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ orgId }),
    });

    if (!response.ok) {
      const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
      setFeedback(payload?.detail ?? 'The workspace org could not be saved.');
      return;
    }

    refreshWorkspace(`Workspace connected to ${orgId}.`);
  }

  async function handleClear() {
    const response = await fetch('/api/operator-context', {
      method: 'DELETE',
    });

    if (!response.ok) {
      setFeedback('The saved workspace org could not be cleared.');
      return;
    }

    setValue('');
    refreshWorkspace('Saved workspace org cleared.');
  }

  return (
    <form className="cl-workspace-form" onSubmit={(event) => void handleSave(event)}>
      <div className="cl-workspace-head">
        <div>
          <div className="cl-kicker">Workspace Org</div>
          <div className="cl-workspace-source">{describeOperatorContextSource(source)}</div>
        </div>
        <div className="cl-org-pill">{initialOrgId ? `Org ${initialOrgId.slice(0, 8)}...` : 'No org selected'}</div>
      </div>

      <label className="cl-label">
        Org UUID
        <input
          value={value}
          onChange={(event) => setValue(event.target.value)}
          placeholder="7d3d7599-820e-4c8d-9c74-3d3b6d6f2785"
          spellCheck={false}
        />
        <p className="cl-field-note">
          Save it here once and the dashboard, queue, and policy views will reuse it.
        </p>
      </label>

      <div className="cl-button-row">
        <button type="submit" className="cl-button is-primary" disabled={isPending}>
          {isPending ? 'Saving...' : 'Use this org'}
        </button>
        <button type="button" className="cl-button" disabled={isPending} onClick={() => void handleClear()}>
          Clear
        </button>
      </div>

      {feedback ? <p className="cl-field-note">{feedback}</p> : null}
    </form>
  );
}
