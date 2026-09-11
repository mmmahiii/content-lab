'use client';

import type { ReactNode } from 'react';

const paths: Record<string, ReactNode> = {
  content: (
    <>
      <rect x="4" y="3" width="16" height="18" rx="3" />
      <path d="m10 8 5 4-5 4Z" />
    </>
  ),
  pages: (
    <>
      <rect x="3" y="3" width="7" height="7" rx="1.5" />
      <rect x="14" y="3" width="7" height="7" rx="1.5" />
      <rect x="3" y="14" width="7" height="7" rx="1.5" />
      <rect x="14" y="14" width="7" height="7" rx="1.5" />
    </>
  ),
  ideas: (
    <>
      <path d="M9 18h6m-5 3h4M8 14a7 7 0 1 1 8 0l-1 3H9Z" />
      <path d="M12 1v2" />
    </>
  ),
  assets: (
    <>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <circle cx="8" cy="9" r="1.5" />
      <path d="m3 17 5-4 4 3 4-7 5 8" />
    </>
  ),
  packs: (
    <>
      <path d="m12 2 10 5-10 5L2 7Zm-10 5v10l10 5 10-5V7M12 12v10M7 4.5l10 5" />
    </>
  ),
  review: (
    <>
      <path d="M12 2 3 6v6c0 5 9 10 9 10s9-5 9-10V6Z" />
      <path d="m8 12 3 3 5-6" />
    </>
  ),
  publication: (
    <>
      <path d="m3 11 18-8-8 18-2-8ZM11 13 21 3" />
    </>
  ),
  operations: (
    <>
      <path d="M3 12h4l3-8 4 16 3-8h4" />
    </>
  ),
  learning: (
    <>
      <path d="M4 3v18h18M8 16v-5m5 5V7m5 9V4" />
    </>
  ),
  arrow: (
    <>
      <path d="M4 12h16m-6-6 6 6-6 6" />
    </>
  ),
  back: <path d="M20 12H4m6-6-6 6 6 6" />,
  plus: <path d="M12 5v14M5 12h14" />,
  search: (
    <>
      <circle cx="10" cy="10" r="6" />
      <path d="m15 15 5 5" />
    </>
  ),
  clock: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </>
  ),
  spark: (
    <>
      <path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5ZM20 2v4m-2-2h4" />
    </>
  ),
  check: <path d="m5 12 4 4L19 6" />,
  close: <path d="m6 6 12 12M6 18 18 6" />,
  settings: (
    <>
      <path d="M4 7h16M4 17h16" />
      <circle cx="9" cy="7" r="3" />
      <circle cx="16" cy="17" r="3" />
    </>
  ),
  download: (
    <>
      <path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5" />
    </>
  ),
};
export function Icon({ name, size = 20 }: { name: string; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.65"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name] ?? paths.content}
    </svg>
  );
}
export function Badge({ children, tone = '' }: { children: ReactNode; tone?: string }) {
  return <span className={`badge ${tone}`}>{children}</span>;
}
export function EmptyState({
  title,
  children,
  action,
}: {
  title: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="empty-state">
      <span className="empty-mark">
        <Icon name="spark" size={28} />
      </span>
      <h2>{title}</h2>
      <p>{children}</p>
      {action}
    </div>
  );
}
export function StatusBadge({ status }: { status: string }) {
  const tone = /approved|published|ready|succeeded|pass|eligible/.test(status)
    ? 'green'
    : /blocked|failed|rejected|restricted/.test(status)
      ? 'red'
      : /review|partial|unknown|warning/.test(status)
        ? 'amber'
        : 'purple';
  return (
    <Badge tone={tone}>
      <span className="status-dot" />
      {status.replaceAll('_', ' ')}
    </Badge>
  );
}
export function DownloadButton({
  data,
  filename,
  children,
}: {
  data: unknown;
  filename: string;
  children: ReactNode;
}) {
  return (
    <button
      className="button secondary"
      onClick={() => {
        const url = URL.createObjectURL(
          new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }),
        );
        const anchor = document.createElement('a');
        anchor.href = url;
        anchor.download = filename;
        anchor.click();
        window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      }}
    >
      <Icon name="download" size={16} />
      {children}
    </button>
  );
}
