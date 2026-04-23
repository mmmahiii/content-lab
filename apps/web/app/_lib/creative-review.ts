import type {
  JsonObject,
  PackageDetailOut,
  ProcessReelOperatorDebugOut,
  ReelDetailOut,
  RunDetailOut,
} from '@shared/types';

function asJsonObject(value: unknown): JsonObject | null {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    return null;
  }
  return value as JsonObject;
}

export function creativePlanningFromRun(run: RunDetailOut | null): JsonObject | null {
  const outputs = asJsonObject(run?.output_payload)?.step_outputs;
  return asJsonObject(asJsonObject(outputs)?.creative_planning);
}

export function mergeOperatorDebug(
  reel: ReelDetailOut | null,
  run: RunDetailOut | null,
  packageDetail: PackageDetailOut | null,
): ProcessReelOperatorDebugOut | null {
  return (
    run?.operator_debug ?? packageDetail?.operator_debug ?? reel?.operator_debug ?? null
  );
}
