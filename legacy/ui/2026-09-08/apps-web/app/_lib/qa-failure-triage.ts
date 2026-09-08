export type QaFailureClass = 'semantic' | 'technical' | 'unknown';

export type QaFailureFilter = QaFailureClass | 'all';

export type QaFailureTriage = {
  failureClass: QaFailureClass;
  gates: string[];
  nextAction: string;
};

type JsonRecord = Record<string, unknown>;

type PackageStatus = 'ready' | 'failed' | 'pending' | 'not_started';

function asRecord(value: unknown): JsonRecord | null {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    return null;
  }

  return value as JsonRecord;
}

function readBoolean(record: JsonRecord | null, key: string): boolean | null {
  if (record === null) {
    return null;
  }

  const value = record[key];
  return typeof value === 'boolean' ? value : null;
}

function gateFailed(section: JsonRecord | null): boolean {
  if (section === null) {
    return false;
  }

  const verdict = section.verdict;
  if (typeof verdict === 'string' && verdict.toLowerCase() === 'fail') {
    return true;
  }

  const passed = readBoolean(section, 'passed');
  if (passed === false) {
    return true;
  }

  const outcome = section.outcome;
  if (typeof outcome === 'string' && outcome.toLowerCase() === 'fail') {
    return true;
  }

  return false;
}

function gateLabel(key: string): string {
  if (key === 'semantic_script') {
    return 'Semantic script';
  }
  if (key === 'repetition') {
    return 'Repetition';
  }
  if (key === 'alignment') {
    return 'Brief alignment';
  }
  if (key === 'format') {
    return 'Format / structure';
  }

  return key.replaceAll('_', ' ');
}

function collectOperatorDebug(metadata: JsonRecord): JsonRecord | null {
  const direct = asRecord(metadata.operator_debug);
  if (direct) {
    return direct;
  }

  const processReel = asRecord(metadata.process_reel);
  if (!processReel) {
    return null;
  }

  const fromSummary = asRecord(asRecord(processReel.last_summary)?.operator_debug);

  return (
    asRecord(processReel.operator_debug) ??
    asRecord(processReel.last_operator_debug) ??
    fromSummary
  );
}

function buildNextAction(failureClass: QaFailureClass): string {
  if (failureClass === 'semantic') {
    return 'Review creative QA on the reel detail page, adjust script or prompts, then re-run process_reel from Actions.';
  }

  if (failureClass === 'technical') {
    return 'Open the linked package or run detail, verify manifest and artifacts, and fix packaging or media integrity before re-trying.';
  }

  return 'Open reel and run detail and read operator_debug to see which gate failed.';
}

/**
 * Derive QA triage from reel metadata (list/detail shape) plus lifecycle flags.
 * Returns null when the reel is not in a QA-blocked state.
 */
export function triageQaFailure(
  metadata: JsonRecord,
  ctx: { reelStatus: string; packageStatus: PackageStatus },
): QaFailureTriage | null {
  const creativeQaFailed = ctx.reelStatus === 'qa_failed';
  const packagingFailed = ctx.packageStatus === 'failed';

  if (!creativeQaFailed && !packagingFailed) {
    return null;
  }

  const opDebug = collectOperatorDebug(metadata);
  const qa = asRecord(opDebug?.qa);
  const packageRecord = asRecord(metadata.package);
  const packageQa = asRecord(packageRecord?.package_qa);

  const gates: string[] = [];
  let semanticGateFailed = false;
  let formatGateFailed = false;

  for (const key of ['semantic_script', 'repetition', 'alignment'] as const) {
    const section = asRecord(qa?.[key]);
    if (gateFailed(section)) {
      semanticGateFailed = true;
      gates.push(gateLabel(key));
    }
  }

  const formatSection = asRecord(qa?.format);
  if (gateFailed(formatSection)) {
    formatGateFailed = true;
    gates.push(gateLabel('format'));
  }

  if (Array.isArray(qa?.checks)) {
    for (const raw of qa.checks) {
      const check = asRecord(raw);
      if (!check || !gateFailed(check)) {
        continue;
      }

      const name =
        typeof check.label === 'string'
          ? check.label
          : typeof check.name === 'string'
            ? check.name
            : typeof check.code === 'string'
              ? check.code
              : 'QA check';

      gates.push(name);

      const code = typeof check.code === 'string' ? check.code.toLowerCase() : '';
      if (
        code.includes('format') ||
        code.includes('manifest') ||
        code.includes('package') ||
        code.includes('codec') ||
        code.includes('media')
      ) {
        formatGateFailed = true;
      } else {
        semanticGateFailed = true;
      }
    }
  }

  const packageQaFailed = readBoolean(packageQa, 'passed') === false;
  if (packageQaFailed) {
    gates.push('Package QA');
  }

  if (packagingFailed && !gates.includes('Package QA')) {
    gates.push('Package readiness');
  }

  if (creativeQaFailed && gates.length === 0) {
    gates.push('Creative QA');
  }

  const technicalSignal = packagingFailed || packageQaFailed || formatGateFailed;

  let failureClass: QaFailureClass;
  if (semanticGateFailed && technicalSignal) {
    failureClass = 'semantic';
  } else if (semanticGateFailed) {
    failureClass = 'semantic';
  } else if (technicalSignal) {
    failureClass = 'technical';
  } else if (creativeQaFailed) {
    failureClass = 'semantic';
  } else if (packagingFailed) {
    failureClass = 'technical';
  } else {
    failureClass = 'unknown';
  }

  return {
    failureClass,
    gates: uniqueStrings(gates),
    nextAction: buildNextAction(failureClass),
  };
}

function uniqueStrings(values: string[]): string[] {
  return Array.from(new Set(values));
}

export function normalizeQaFailureFilter(raw: string | undefined | null): QaFailureFilter {
  const value = (raw ?? 'all').trim().toLowerCase();

  if (value === 'semantic' || value === 'technical' || value === 'unknown') {
    return value;
  }

  return 'all';
}

export function resolvedQaFailureClass(value: QaFailureClass | null | undefined): QaFailureClass {
  return value ?? 'unknown';
}

export function reelMatchesQaFailureFilter(
  reel: {
    origin: string;
    status: string;
    packageStatus: PackageStatus;
    qaFailureClass: QaFailureClass | null;
  },
  filter: QaFailureFilter,
): boolean {
  if (filter === 'all') {
    return true;
  }

  if (reel.origin !== 'generated') {
    return false;
  }

  const blocked = reel.status === 'qa_failed' || reel.packageStatus === 'failed';
  return blocked && resolvedQaFailureClass(reel.qaFailureClass) === filter;
}

export function queueItemMatchesQaFailureFilter(
  item: {
    queueState: string;
    qaFailureClass: QaFailureClass | null;
  },
  filter: QaFailureFilter,
): boolean {
  if (filter === 'all') {
    return true;
  }

  return item.queueState === 'qa_failed' && resolvedQaFailureClass(item.qaFailureClass) === filter;
}
