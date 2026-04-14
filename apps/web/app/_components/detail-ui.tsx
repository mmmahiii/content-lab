import React from 'react';
import Link from 'next/link';
import type { ReactElement, ReactNode } from 'react';

export type BreadcrumbItem = {
  label: string;
  href?: string;
};

type CueItem = {
  label: string;
  value: ReactNode;
};

type FrameProps = {
  eyebrow: string;
  title: string;
  subtitle: string;
  breadcrumbs?: BreadcrumbItem[];
  cues?: CueItem[];
  cuesSummary?: string;
  actions?: ReactNode;
  children: ReactNode;
};

type SectionProps = {
  title: string;
  description?: string;
  actions?: ReactNode;
  note?: ReactNode;
  children: ReactNode;
};

type MetaGridProps = {
  items: Array<{
    label: string;
    value: ReactNode;
  }>;
};

type JsonPanelProps = {
  title: string;
  value: unknown;
};

type LinkActionProps = {
  href: string;
  label: string;
  tone?: 'default' | 'primary' | 'secondary';
};

function toneClass(status: string): string {
  const normalized = status.toLowerCase();

  if (
    ['ready', 'posted', 'succeeded', 'success', 'owned', 'active', 'saved', 'reviewed'].includes(
      normalized,
    )
  ) {
    return ' is-success';
  }

  if (
    ['failed', 'archived', 'removed', 'error', 'qa_failed', 'unavailable'].includes(normalized)
  ) {
    return ' is-danger';
  }

  if (
    ['running', 'queued', 'pending', 'draft', 'manual', 'not_started', 'processing'].includes(
      normalized,
    )
  ) {
    return ' is-warning';
  }

  return '';
}

export function formatStatus(status: string): string {
  return status.replaceAll('_', ' ');
}

export function formatTimestamp(value: string | null | undefined): string {
  if (!value) {
    return 'Not recorded';
  }

  return new Date(value).toLocaleString('en-GB', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'Europe/London',
  });
}

function Breadcrumbs({ items }: { items: BreadcrumbItem[] | undefined }) {
  if (!items || items.length === 0) {
    return null;
  }

  return (
    <nav className="cl-breadcrumbs" aria-label="Breadcrumb">
      {items.map((item, index) => (
        <span key={`${item.label}-${index}`}>
          {item.href ? <Link href={item.href}>{item.label}</Link> : item.label}
          {index < items.length - 1 ? ' / ' : ''}
        </span>
      ))}
    </nav>
  );
}

export function DetailFrame({
  eyebrow,
  title,
  subtitle,
  breadcrumbs,
  cues,
  cuesSummary,
  actions,
  children,
}: FrameProps): ReactElement {
  return (
    <div className="cl-page">
      <section className="cl-page-header">
        <Breadcrumbs items={breadcrumbs} />
        <div className="cl-page-hero">
          <div className="cl-page-copy">
            <div className="cl-eyebrow">{eyebrow}</div>
            <h1 className="cl-page-title">{title}</h1>
            <p className="cl-page-subtitle">{subtitle}</p>
          </div>
          {actions ? <div className="cl-actions">{actions}</div> : null}
        </div>
        {cues && cues.length > 0 ? (
          <details className="cl-guide-panel">
            <summary className="cl-guide-summary">
              <span className="cl-guide-title">How to use this page</span>
              <span className="cl-guide-copy">
                {cuesSummary ?? 'Open for a quick explanation of what this page is for, what you can do here, and what comes next.'}
              </span>
            </summary>
            <div className="cl-cue-grid">
              {cues.map((cue) => (
                <article key={cue.label} className="cl-cue-card">
                  <div className="cl-cue-label">{cue.label}</div>
                  <div className="cl-cue-value">{cue.value}</div>
                </article>
              ))}
            </div>
          </details>
        ) : null}
      </section>
      {children}
    </div>
  );
}

export function SectionCard({
  title,
  description,
  actions,
  note,
  children,
}: SectionProps): ReactElement {
  return (
    <section className="cl-panel">
      <div className="cl-panel-header">
        <div>
          <h2 className="cl-panel-title">{title}</h2>
          {description ? <p className="cl-panel-description">{description}</p> : null}
        </div>
        {actions ? <div className="cl-actions">{actions}</div> : null}
      </div>
      {children}
      {note ? <div className="cl-panel-note">{note}</div> : null}
    </section>
  );
}

export function MetaGrid({ items }: MetaGridProps): ReactElement {
  return (
    <div className="cl-meta-grid">
      {items.map((item) => (
        <article key={item.label} className="cl-meta-card">
          <div className="cl-meta-label">{item.label}</div>
          <div className="cl-meta-value">{item.value}</div>
        </article>
      ))}
    </div>
  );
}

export function StatusBadge({ status }: { status: string }): ReactElement {
  return <span className={`cl-pill${toneClass(status)}`}>{formatStatus(status)}</span>;
}

export function JsonPanel({ title, value }: JsonPanelProps): ReactElement {
  return (
    <div className="cl-panel">
      <div>
        <div className="cl-meta-label">{title}</div>
      </div>
      <pre className="cl-json">{JSON.stringify(value, null, 2)}</pre>
    </div>
  );
}

function toneToButtonClass(tone?: LinkActionProps['tone']): string {
  if (tone === 'primary') {
    return 'cl-link-button is-primary';
  }

  if (tone === 'secondary') {
    return 'cl-link-button is-secondary';
  }

  return 'cl-link-button';
}

export function LinkAction({ href, label, tone }: LinkActionProps): ReactElement {
  return (
    <Link href={href} className={toneToButtonClass(tone)}>
      {label}
    </Link>
  );
}

export function ExternalAction({ href, label }: LinkActionProps): ReactElement {
  return (
    <a href={href} rel="noreferrer" target="_blank" className="cl-link-button">
      {label}
    </a>
  );
}

export function InlineList({ children }: { children: ReactNode }): ReactElement {
  return <div className="cl-inline-list">{children}</div>;
}
