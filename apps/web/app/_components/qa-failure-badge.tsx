import React from 'react';

import type { QaFailureClass } from '../_lib/qa-failure-triage';

const SEMANTIC_LABEL = 'Semantic / content';
const TECHNICAL_LABEL = 'Packaging / format';
const UNKNOWN_LABEL = 'Needs classification';

export function QaFailureClassBadge({ failureClass }: { failureClass: QaFailureClass }): React.ReactElement {
  const label =
    failureClass === 'semantic'
      ? SEMANTIC_LABEL
      : failureClass === 'technical'
        ? TECHNICAL_LABEL
        : UNKNOWN_LABEL;

  const toneClass =
    failureClass === 'semantic'
      ? ' is-warning'
      : failureClass === 'technical'
        ? ' is-danger'
        : '';

  return (
    <span className={`cl-pill${toneClass}`} title={label}>
      {label}
    </span>
  );
}

export function QaFailureGatesSummary({ gates }: { gates: string[] }): React.ReactElement | null {
  if (gates.length === 0) {
    return null;
  }

  const preview = gates.slice(0, 4).join(', ');
  const suffix = gates.length > 4 ? ` (+${gates.length - 4} more)` : '';

  return (
    <div className="cl-resource-meta">
      <strong>Failing gates: </strong>
      {preview}
      {suffix}
    </div>
  );
}
