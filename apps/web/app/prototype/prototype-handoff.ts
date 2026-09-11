import type { PackageRecord, WorkspaceState } from './domain';

/** Export the package's frozen references, including repeated uses of an asset. */
export function buildPrototypeHandoff(state: WorkspaceState, pack: PackageRecord) {
  const revision = state.revisions.find((r) => r.id === pack.revisionId);
  if (!revision) throw new Error('The package revision is unavailable.');
  const resolve = (representationId?: string) => {
    const representation = state.representations.find((r) => r.id === representationId);
    const version = state.assetVersions.find((v) => v.id === representation?.assetVersionId);
    return { representationId, representation, version, assetId: version?.assetId };
  };
  return {
    kind: 'content-laboratory-prototype-handoff',
    simulated: true,
    encodedVideo: 'NOT PRODUCED — this bundle is for UI review only',
    revision,
    packageId: pack.id,
    approval: { id: pack.approvalId, approvedAt: pack.approvedAt, approvedBy: pack.approvedBy },
    copy: pack.copy,
    disclosures: pack.disclosures,
    coverFrame: pack.coverFrame,
    qa: pack.findings,
    selectedIngredients: revision.composition.selectedAssets,
    provenance: revision.composition.scenes.flatMap((scene) => [
      ...scene.instances
        .filter((i) => i.representationId)
        .map((instance) => ({
          sceneId: scene.id,
          instanceId: instance.id,
          kind: 'visual',
          ...resolve(instance.representationId),
        })),
      ...scene.audio.map((event) => ({
        sceneId: scene.id,
        instanceId: event.id,
        kind: 'audio',
        ...resolve(event.representationId),
      })),
    ]),
  };
}
