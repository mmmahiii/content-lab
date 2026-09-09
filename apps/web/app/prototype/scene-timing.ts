import type { Composition, Scene } from './domain';

/** Reflow global, half-open frame intervals while preserving scene-local timing. */
export function reflowScenes(composition: Composition, scenes: Scene[]): Composition {
  let cursor = 0;
  const nextScenes = scenes.map((scene) => {
    const duration = Math.max(1, scene.endFrame - scene.startFrame);
    const shift = cursor - scene.startFrame;
    const next = {
      ...scene,
      startFrame: cursor,
      endFrame: cursor + duration,
      instances: scene.instances.map((item) => ({
        ...item,
        startFrame: item.startFrame + shift,
        endFrame: item.endFrame + shift,
      })),
      audio: scene.audio.map((event) => ({
        ...event,
        startFrame: event.startFrame + shift,
        endFrame: event.endFrame + shift,
      })),
    };
    cursor += duration;
    return next;
  });
  return {
    ...composition,
    scenes: nextScenes,
    totalFrames: cursor,
    coverFrame: Math.min(composition.coverFrame, Math.max(0, cursor - 1)),
  };
}

export function reorderScene(
  composition: Composition,
  sceneId: string,
  direction: -1 | 1,
): Composition {
  const scenes = [...composition.scenes];
  const from = scenes.findIndex((scene) => scene.id === sceneId);
  const to = from + direction;
  if (from < 0 || to < 0 || to >= scenes.length) return composition;
  [scenes[from], scenes[to]] = [scenes[to], scenes[from]];
  return reflowScenes(composition, scenes);
}

/** Duration edits retime linked intervals together; source playback remains 1×. */
export function resizeScene(
  composition: Composition,
  sceneId: string,
  durationFrames: number,
): Composition {
  const duration = Math.max(1, Math.round(durationFrames));
  const scenes = composition.scenes.map((scene) => {
    if (scene.id !== sceneId) return scene;
    const ratio = duration / Math.max(1, scene.endFrame - scene.startFrame);
    const interval = (start: number, end: number) => {
      const localStart = Math.max(
        0,
        Math.min(duration - 1, Math.round((start - scene.startFrame) * ratio)),
      );
      const localEnd = Math.max(
        localStart + 1,
        Math.min(duration, Math.round((end - scene.startFrame) * ratio)),
      );
      return { startFrame: scene.startFrame + localStart, endFrame: scene.startFrame + localEnd };
    };
    return {
      ...scene,
      endFrame: scene.startFrame + duration,
      instances: scene.instances.map((item) => ({
        ...item,
        ...interval(item.startFrame, item.endFrame),
      })),
      audio: scene.audio.map((event) => ({
        ...event,
        ...interval(event.startFrame, event.endFrame),
      })),
    };
  });
  return reflowScenes(composition, scenes);
}

export function secondsAtFrame(composition: Composition, frame: number): number {
  return (frame * composition.fps.denominator) / composition.fps.numerator;
}
