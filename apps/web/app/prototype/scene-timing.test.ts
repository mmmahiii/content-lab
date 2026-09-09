import { describe, expect, it } from 'vitest';
import type { Composition, Scene } from './domain';
import { reorderScene, resizeScene, secondsAtFrame } from './scene-timing';

function makeScene(id: string, startFrame: number, endFrame: number): Scene {
  return {
    id,
    name: id,
    purpose: 'Show a useful step',
    startFrame,
    endFrame,
    background: '#302030',
    instances: [
      {
        id: `${id}-clip`,
        name: 'Source clip',
        kind: 'video',
        color: '#ffffff',
        x: 0,
        y: 0,
        width: 1,
        height: 1,
        rotation: 0,
        opacity: 1,
        startFrame,
        endFrame,
        sourceInFrame: 20,
        layer: 0,
        relation: 'independent',
        protectedProperties: [],
      },
      {
        id: `${id}-caption`,
        name: 'Caption',
        kind: 'text',
        text: 'Two useful steps',
        color: '#ffffff',
        x: 0.1,
        y: 0.1,
        width: 0.8,
        height: 0.1,
        rotation: 0,
        opacity: 1,
        startFrame: startFrame + 10,
        endFrame: endFrame - 10,
        sourceInFrame: 0,
        layer: 1,
        relation: 'overlay',
        protectedProperties: [],
      },
    ],
    audio: [
      {
        id: `${id}-voice`,
        representationId: 'guide',
        role: 'voice',
        startFrame: startFrame + 10,
        endFrame: endFrame - 10,
        gain: 0.7,
      },
    ],
  };
}

function composition(): Composition {
  return {
    title: 'Timing test',
    brief: { objective: '', audienceValue: '', tone: '', claims: '', evidence: '', payoff: '' },
    hookId: 'hook',
    blueprintId: 'blueprint',
    mode: 'existing_assets',
    fps: { numerator: 30, denominator: 1 },
    canvas: { width: 1080, height: 1920 },
    totalFrames: 300,
    scenes: [makeScene('a', 0, 90), makeScene('b', 90, 210), makeScene('c', 210, 300)],
    selectedAssets: [],
    caption: '',
    disclosures: '',
    coverFrame: 250,
  };
}

describe('the editor’s single media clock', () => {
  it('moves source clips, captions and audio together without changing source in or the original revision', () => {
    const original = composition();
    const next = reorderScene(original, 'b', -1);
    expect(next.scenes.map((scene) => [scene.id, scene.startFrame, scene.endFrame])).toEqual([
      ['b', 0, 120],
      ['a', 120, 210],
      ['c', 210, 300],
    ]);
    expect(next.scenes[0].instances[0]).toMatchObject({
      startFrame: 0,
      endFrame: 120,
      sourceInFrame: 20,
    });
    expect(next.scenes[0].instances[1]).toMatchObject({ startFrame: 10, endFrame: 110 });
    expect(next.scenes[0].audio[0]).toMatchObject({ startFrame: 10, endFrame: 110, gain: 0.7 });
    expect(original.scenes[1].startFrame).toBe(90);
    expect(original.scenes[1].instances[1].startFrame).toBe(100);
  });

  it('retimes a shortened scene and shifts later scenes without audio/text drift', () => {
    const next = resizeScene(composition(), 'b', 60);
    expect(next.totalFrames).toBe(240);
    expect(next.scenes.map((scene) => [scene.startFrame, scene.endFrame])).toEqual([
      [0, 90],
      [90, 150],
      [150, 240],
    ]);
    expect(next.scenes[1].instances[0]).toMatchObject({
      startFrame: 90,
      endFrame: 150,
      sourceInFrame: 20,
    });
    expect(next.scenes[1].instances[1]).toMatchObject({ startFrame: 95, endFrame: 145 });
    expect(next.scenes[1].audio[0]).toMatchObject({ startFrame: 95, endFrame: 145 });
    expect(next.scenes[2].audio[0]).toMatchObject({ startFrame: 160, endFrame: 230 });
    expect(next.coverFrame).toBe(239);
  });

  it('keeps non-empty integer half-open intervals when rounding to a one-frame scene', () => {
    const next = resizeScene(composition(), 'a', 1);
    expect(
      next.scenes[0].instances.every((event) => event.startFrame === 0 && event.endFrame === 1),
    ).toBe(true);
    expect(next.scenes[0].audio[0]).toMatchObject({ startFrame: 0, endFrame: 1 });
    expect(next.scenes[1].startFrame).toBe(1);
    expect(next.totalFrames).toBe(211);
  });

  it('rejects out-of-bounds moves and uses the rational frame rate for display time', () => {
    const original = composition();
    expect(reorderScene(original, 'a', -1)).toBe(original);
    expect(reorderScene(original, 'c', 1)).toBe(original);
    expect(secondsAtFrame({ ...original, fps: { numerator: 30000, denominator: 1001 } }, 900)).toBe(
      30.03,
    );
  });
});
