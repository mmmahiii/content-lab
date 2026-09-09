import type { Composition, Finding, Representation, WorkspaceState } from './domain';

/** Local structural checks only. Perceptual quality and identity need real measurements later. */
export function validateComposition(comp: Composition, state: WorkspaceState): Finding[] {
  const findings: Finding[] = [];
  const add = (
    category: Finding['category'],
    severity: Finding['severity'],
    title: string,
    detail: string,
    context: Partial<Finding> = {},
  ) => {
    findings.push({
      id: `check-${findings.length + 1}`,
      category,
      severity,
      title,
      detail,
      evidence: 'local_check',
      ...context,
    });
  };
  const integer = (value: number) => Number.isSafeInteger(value);
  if (!comp.title.trim())
    add(
      'editorial',
      'fail',
      'Give this content a title',
      'A title is required before saving a production revision.',
    );
  if (!comp.brief.objective.trim() || !comp.brief.audienceValue.trim() || !comp.brief.payoff.trim())
    add(
      'editorial',
      'fail',
      'Complete the brief',
      'Describe the objective, audience value and payoff.',
    );
  if (comp.brief.claims.trim() && !comp.brief.evidence.trim())
    add(
      'editorial',
      'warning',
      'Claims need supporting evidence',
      'Add a source or explain that this is an illustrative creative claim.',
    );
  if (!state.hooks.some((h) => h.id === comp.hookId))
    add('editorial', 'fail', 'Choose a hook', 'The selected hook is unavailable.');
  if (!state.blueprints.some((b) => b.id === comp.blueprintId))
    add('editorial', 'fail', 'Choose a blueprint', 'The selected blueprint is unavailable.');
  if (!integer(comp.totalFrames) || comp.totalFrames < 1)
    add(
      'timing',
      'fail',
      'Invalid duration',
      'Duration must contain a positive whole number of frames.',
    );
  if (
    !integer(comp.fps.numerator) ||
    !integer(comp.fps.denominator) ||
    comp.fps.numerator < 1 ||
    comp.fps.denominator < 1
  )
    add(
      'timing',
      'fail',
      'Invalid frame rate',
      'Frame rate requires positive integer numerator and denominator.',
    );
  if (
    !integer(comp.canvas.width) ||
    !integer(comp.canvas.height) ||
    comp.canvas.width < 1 ||
    comp.canvas.height < 1
  )
    add('package', 'fail', 'Invalid canvas', 'Canvas dimensions must be positive whole pixels.');
  if (!integer(comp.coverFrame) || comp.coverFrame < 0 || comp.coverFrame >= comp.totalFrames)
    add(
      'timing',
      'fail',
      'Cover is outside the timeline',
      'Select a cover frame inside the composition.',
    );
  if (!comp.scenes.length) add('timing', 'fail', 'Add a scene', 'At least one scene is required.');
  const seenScenes = new Set<string>();
  const seenInstances = new Set<string>();
  const usedAssets = new Set<string>();
  const ordered = [...comp.scenes].sort((a, b) => a.startFrame - b.startFrame);
  let previousEnd = 0;
  const checkRepresentation = (rep: Representation | undefined, context: Partial<Finding>) => {
    if (!rep) {
      add(
        'assets',
        'fail',
        'Media representation is missing',
        'Choose a registered representation for this instance.',
        context,
      );
      return;
    }
    if (rep.readiness !== 'ready')
      add(
        'assets',
        'fail',
        'Media is not ready',
        `This representation is ${rep.readiness}. Replace it or resolve its registry status.`,
        context,
      );
    if (rep.rights !== 'eligible')
      add(
        'rights',
        'fail',
        'Rights need review',
        rep.rightsNote || 'This representation is not eligible for production.',
        context,
      );
    if (!rep.src)
      add(
        'assets',
        'fail',
        'No media attached',
        'Attach media before using this representation.',
        context,
      );
  };
  for (const scene of ordered) {
    const context = { sceneId: scene.id, frame: scene.startFrame };
    if (seenScenes.has(scene.id))
      add('timing', 'fail', 'Duplicate scene identity', 'Each scene needs its own ID.', context);
    seenScenes.add(scene.id);
    if (
      !integer(scene.startFrame) ||
      !integer(scene.endFrame) ||
      scene.startFrame < 0 ||
      scene.endFrame <= scene.startFrame ||
      scene.endFrame > comp.totalFrames
    )
      add(
        'timing',
        'fail',
        'Scene timing is invalid',
        'Scene boundaries must be whole frames inside the composition, with an end after the start.',
        context,
      );
    if (scene.startFrame !== previousEnd)
      add(
        'timing',
        'fail',
        scene.startFrame < previousEnd ? 'Scenes overlap' : 'There is a gap between scenes',
        `This scene starts at frame ${scene.startFrame}; the previous scene ends at ${previousEnd}.`,
        context,
      );
    previousEnd = scene.endFrame;
    for (const item of scene.instances) {
      const target = { ...context, instanceId: item.id, frame: item.startFrame };
      if (seenInstances.has(item.id))
        add(
          'assets',
          'fail',
          'Duplicate object identity',
          'Repeated assets still need separate instance IDs.',
          target,
        );
      seenInstances.add(item.id);
      if (
        !integer(item.startFrame) ||
        !integer(item.endFrame) ||
        item.startFrame < scene.startFrame ||
        item.endFrame > scene.endFrame ||
        item.endFrame <= item.startFrame
      )
        add(
          'timing',
          'fail',
          'Object timing is invalid',
          'Object timing must stay inside its scene using global composition frames.',
          target,
        );
      if (
        ![item.x, item.y, item.width, item.height, item.rotation, item.opacity].every(
          Number.isFinite,
        ) ||
        item.width <= 0 ||
        item.height <= 0 ||
        item.x < 0 ||
        item.y < 0 ||
        item.x + item.width > 1.001 ||
        item.y + item.height > 1.001 ||
        item.opacity < 0 ||
        item.opacity > 1
      )
        add(
          'assets',
          'fail',
          'Object is outside the canvas',
          'Use a positive size and keep the top-left position and footprint within the canvas; opacity must be 0–1.',
          target,
        );
      if (!integer(item.layer))
        add(
          'assets',
          'fail',
          'Layer must be a whole number',
          'Use a whole-number layer order.',
          target,
        );
      if (item.kind === 'text') {
        if (!item.text?.trim())
          add(
            'text',
            'fail',
            'Empty text layer',
            'Add audience-facing copy or remove this layer.',
            target,
          );
        if ((item.text?.length ?? 0) > 140)
          add(
            'text',
            'warning',
            'Text may be difficult to read',
            'This layer exceeds 140 characters. Shorten it and inspect the preview; this is a length heuristic, not a measured text fit.',
            target,
          );
        if (item.y < 0.05 || item.y + item.height > 0.92)
          add(
            'text',
            'warning',
            'Text near the safe-area edge',
            'Inspect platform overlays before export. This local guide uses a provisional 5% top and 8% bottom margin.',
            target,
          );
      }
      if (item.assetId) usedAssets.add(item.assetId);
      if (item.kind === 'image' || item.kind === 'video') {
        const version = state.assetVersions.find((v) => v.id === item.assetVersionId);
        const rep = state.representations.find((r) => r.id === item.representationId);
        if (!version || version.assetId !== item.assetId || rep?.assetVersionId !== version.id)
          add(
            'assets',
            'fail',
            'Asset version binding is invalid',
            'Pin the instance to a representation belonging to this exact asset version.',
            target,
          );
        checkRepresentation(rep, target);
        if (rep && rep.mediaType !== item.kind)
          add(
            'assets',
            'fail',
            'Media type does not match the layer',
            `A ${item.kind} layer cannot use ${rep.mediaType} media.`,
            target,
          );
        if (
          item.kind === 'video' &&
          (!integer(item.sourceInFrame) ||
            item.sourceInFrame < 0 ||
            (rep?.durationFrames !== undefined &&
              item.sourceInFrame + item.endFrame - item.startFrame > rep.durationFrames))
        )
          add(
            'timing',
            'fail',
            'Source footage is too short',
            'Trim this use or choose a longer source; footage will not be silently looped.',
            target,
          );
      }
      if (item.relation !== 'independent') {
        const support = scene.instances.find(
          (i) => i.id === item.targetInstanceId && i.id !== item.id,
        );
        if (!support)
          add(
            'assets',
            'fail',
            'Relationship target is missing',
            'Choose another object in this same scene.',
            target,
          );
        else if (item.relation === 'behind' && item.layer >= support.layer)
          add(
            'assets',
            'fail',
            'Depth order contradicts the relationship',
            'An object marked behind must use a lower layer than its target.',
            target,
          );
        else if (
          (item.relation === 'on_surface' || item.relation === 'overlay') &&
          item.layer <= support.layer
        )
          add(
            'assets',
            'fail',
            'Layer order contradicts the relationship',
            'This object must use a higher layer than its support or overlay target.',
            target,
          );
      }
    }
    for (const audio of scene.audio) {
      const rep = state.representations.find((r) => r.id === audio.representationId);
      checkRepresentation(rep, context);
      if (rep && rep.mediaType !== 'audio')
        add(
          'assets',
          'fail',
          'Audio source is invalid',
          'Choose an audio representation.',
          context,
        );
      if (
        !integer(audio.startFrame) ||
        !integer(audio.endFrame) ||
        audio.startFrame < scene.startFrame ||
        audio.endFrame > scene.endFrame ||
        audio.endFrame <= audio.startFrame ||
        (rep?.durationFrames !== undefined &&
          audio.endFrame - audio.startFrame > rep.durationFrames)
      )
        add(
          'timing',
          'fail',
          'Audio timing is invalid',
          'Audio must fit inside its scene and available source duration.',
          context,
        );
      if (!Number.isFinite(audio.gain) || audio.gain < 0 || audio.gain > 2)
        add('assets', 'fail', 'Audio level is invalid', 'Choose a gain between 0 and 2.', context);
    }
  }
  if (ordered.length && previousEnd !== comp.totalFrames)
    add(
      'timing',
      'fail',
      'Timeline ends early',
      'The final scene must end at the composition duration.',
    );
  for (const selected of comp.selectedAssets) {
    if (!state.assets.some((a) => a.id === selected.assetId))
      add(
        'assets',
        'fail',
        'Selected asset is unavailable',
        `Asset ${selected.assetId} is no longer in the registry.`,
      );
    if (selected.mandatory && !usedAssets.has(selected.assetId))
      add(
        'assets',
        'fail',
        'A mandatory ingredient is missing',
        `${state.assets.find((a) => a.id === selected.assetId)?.name ?? selected.assetId} is selected as mandatory but is not used in any scene.`,
      );
  }
  if (!findings.some((f) => f.category === 'timing' && f.severity === 'fail'))
    add(
      'timing',
      'pass',
      'Timeline structure is valid',
      'Scene and media frame ranges passed local structural checks.',
    );
  if (
    !findings.some(
      (f) => (f.category === 'assets' || f.category === 'rights') && f.severity === 'fail',
    )
  )
    add(
      'assets',
      'pass',
      'Pinned media is ready',
      'Referenced asset versions and representations exist and are eligible in this simulated registry.',
    );
  add(
    'identity',
    'not_evaluated',
    'Identity preservation is not measured',
    'A real identity/protected-region analysis has not run. Any comparison indicators are illustrative.',
    { evidence: 'simulated' },
  );
  add(
    'package',
    'not_evaluated',
    'Audio and encoded export are not measured',
    'The browser composition can be previewed. No final video, loudness or encoded-file QA has been produced.',
    { evidence: 'simulated' },
  );
  return findings;
}
