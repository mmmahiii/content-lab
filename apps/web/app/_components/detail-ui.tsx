import React from 'react';
import Link from 'next/link';
import type { CSSProperties, ReactElement, ReactNode } from 'react';

type FrameProps = {
  eyebrow: string;
  title: string;
  subtitle: string;
  actions?: ReactNode;
  children: ReactNode;
};

type SectionProps = {
  title: string;
  description?: string;
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
};

const colors = {
  ink: '#172033',
  slate: '#55627a',
  card: 'rgba(255, 252, 245, 0.92)',
  line: 'rgba(23, 32, 51, 0.12)',
  highlight: '#a04a2d',
  success: '#1f6a4d',
  warning: '#8b5b16',
  muted: '#6d7483',
  canvasTop: '#f7efe4',
  canvasBottom: '#e7eef6',
};

const surfaceStyle: CSSProperties = {
  minHeight: '100vh',
  padding: '32px 20px 48px',
};

const shellStyle: CSSProperties = {
  maxWidth: 1120,
  margin: '0 auto',
  display: 'grid',
  gap: 24,
};

const heroStyle: CSSProperties = {
  display: 'grid',
  gap: 16,
  padding: 28,
  borderRadius: 28,
  border: `1px solid ${colors.line}`,
  background:
    'linear-gradient(140deg, rgba(255,255,255,0.92), rgba(246,235,220,0.95) 52%, rgba(229,239,247,0.9))',
  boxShadow: '0 30px 80px rgba(23, 32, 51, 0.08)',
};

const heroHeaderStyle: CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  gap: 16,
  alignItems: 'flex-start',
  flexWrap: 'wrap',
};

const eyebrowStyle: CSSProperties = {
  fontSize: 12,
  textTransform: 'uppercase',
  letterSpacing: '0.2em',
  color: colors.highlight,
  fontWeight: 700,
};

const titleStyle: CSSProperties = {
  margin: '6px 0 8px',
  fontSize: 'clamp(2rem, 4vw, 3.4rem)',
  lineHeight: 1.05,
  color: colors.ink,
  fontFamily: 'Georgia, Cambria, "Times New Roman", Times, serif',
};

const subtitleStyle: CSSProperties = {
  margin: 0,
  maxWidth: 760,
  color: colors.slate,
  fontSize: 16,
  lineHeight: 1.6,
};

const sectionGridStyle: CSSProperties = {
  display: 'grid',
  gap: 20,
};

const cardStyle: CSSProperties = {
  display: 'grid',
  gap: 16,
  padding: 24,
  borderRadius: 24,
  border: `1px solid ${colors.line}`,
  background: colors.card,
  boxShadow: '0 20px 50px rgba(23, 32, 51, 0.05)',
};

const sectionTitleStyle: CSSProperties = {
  margin: 0,
  color: colors.ink,
  fontSize: 22,
  fontFamily: 'Georgia, Cambria, "Times New Roman", Times, serif',
};

const sectionDescriptionStyle: CSSProperties = {
  margin: 0,
  color: colors.slate,
  lineHeight: 1.6,
};

const metaGridStyle: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
  gap: 14,
};

const metaCardStyle: CSSProperties = {
  padding: 16,
  borderRadius: 18,
  background: 'rgba(255, 255, 255, 0.7)',
  border: `1px solid ${colors.line}`,
  display: 'grid',
  gap: 8,
};

const metaLabelStyle: CSSProperties = {
  fontSize: 12,
  textTransform: 'uppercase',
  letterSpacing: '0.12em',
  color: colors.muted,
  fontWeight: 700,
};

const metaValueStyle: CSSProperties = {
  color: colors.ink,
  fontSize: 15,
  lineHeight: 1.5,
  wordBreak: 'break-word',
};

const inlineListStyle: CSSProperties = {
  display: 'flex',
  gap: 10,
  flexWrap: 'wrap',
  alignItems: 'center',
};

const anchorStyle: CSSProperties = {
  color: colors.ink,
  textDecoration: 'none',
  padding: '10px 14px',
  borderRadius: 999,
  border: `1px solid ${colors.line}`,
  background: 'rgba(255, 255, 255, 0.82)',
  fontWeight: 600,
};

const codeStyle: CSSProperties = {
  margin: 0,
  padding: 16,
  borderRadius: 18,
  border: `1px solid ${colors.line}`,
  background: '#111827',
  color: '#e5eef8',
  fontSize: 13,
  overflowX: 'auto',
  lineHeight: 1.6,
};

const badgeBaseStyle: CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 8,
  padding: '8px 12px',
  borderRadius: 999,
  fontSize: 13,
  fontWeight: 700,
  textTransform: 'capitalize',
  border: `1px solid ${colors.line}`,
};

function badgeColor(status: string): { background: string; color: string } {
  if (['posted', 'ready', 'active', 'succeeded'].includes(status)) {
    return {
      background: 'rgba(31, 106, 77, 0.12)',
      color: colors.success,
    };
  }
  if (['qa_failed', 'failed', 'removed', 'unavailable', 'archived'].includes(status)) {
    return {
      background: 'rgba(160, 74, 45, 0.12)',
      color: colors.highlight,
    };
  }
  return {
    background: 'rgba(139, 91, 22, 0.12)',
    color: colors.warning,
  };
}

export function DetailFrame({
  eyebrow,
  title,
  subtitle,
  actions,
  children,
}: FrameProps): ReactElement {
  return (
    <main
      style={{
        ...surfaceStyle,
        background: `linear-gradient(180deg, ${colors.canvasTop}, ${colors.canvasBottom})`,
      }}
    >
      <div style={shellStyle}>
        <section style={heroStyle}>
          <div style={heroHeaderStyle}>
            <div>
              <div style={eyebrowStyle}>{eyebrow}</div>
              <h1 style={titleStyle}>{title}</h1>
              <p style={subtitleStyle}>{subtitle}</p>
            </div>
            {actions ? <div style={inlineListStyle}>{actions}</div> : null}
          </div>
        </section>
        <div style={sectionGridStyle}>{children}</div>
      </div>
    </main>
  );
}

export function SectionCard({ title, description, children }: SectionProps): ReactElement {
  return (
    <section style={cardStyle}>
      <div style={{ display: 'grid', gap: 8 }}>
        <h2 style={sectionTitleStyle}>{title}</h2>
        {description ? <p style={sectionDescriptionStyle}>{description}</p> : null}
      </div>
      {children}
    </section>
  );
}

export function MetaGrid({ items }: MetaGridProps): ReactElement {
  return (
    <div style={metaGridStyle}>
      {items.map((item) => (
        <div key={item.label} style={metaCardStyle}>
          <div style={metaLabelStyle}>{item.label}</div>
          <div style={metaValueStyle}>{item.value}</div>
        </div>
      ))}
    </div>
  );
}

export function StatusBadge({ status }: { status: string }): ReactElement {
  const palette = badgeColor(status);
  return (
    <span
      style={{
        ...badgeBaseStyle,
        background: palette.background,
        color: palette.color,
      }}
    >
      {formatStatus(status)}
    </span>
  );
}

export function JsonPanel({ title, value }: JsonPanelProps): ReactElement {
  return (
    <div style={{ display: 'grid', gap: 10 }}>
      <div style={metaLabelStyle}>{title}</div>
      <pre style={codeStyle}>{JSON.stringify(value, null, 2)}</pre>
    </div>
  );
}

export function LinkAction({ href, label }: LinkActionProps): ReactElement {
  return (
    <Link href={href} style={anchorStyle}>
      {label}
    </Link>
  );
}

export function ExternalAction({ href, label }: LinkActionProps): ReactElement {
  return (
    <a href={href} rel="noreferrer" style={anchorStyle} target="_blank">
      {label}
    </a>
  );
}

export function InlineList({ children }: { children: ReactNode }): ReactElement {
  return <div style={inlineListStyle}>{children}</div>;
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

export const sharedStyles = {
  anchorStyle,
  inlineListStyle,
  metaLabelStyle,
  metaValueStyle,
  line: colors.line,
  slate: colors.slate,
  ink: colors.ink,
  highlight: colors.highlight,
};
