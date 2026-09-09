'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import type { CSSProperties, PointerEvent } from 'react';
import { canEdit } from './domain';
import type {
  Command,
  CommandResult,
  Composition,
  ContentItem,
  Representation,
  Scene,
  SceneInstance,
  WorkspaceState,
} from './domain';
import { reorderScene, resizeScene, secondsAtFrame } from './scene-timing';
import './scene-editor.css';

export interface CompositionPreviewProps {
  composition: Composition;
  state: WorkspaceState;
  frame?: number;
  onSelect?: (instanceId: string, sceneId: string) => void;
  selectedId?: string;
  onChangeInstance?: (sceneId: string, instanceId: string, patch: Partial<SceneInstance>) => void;
}

function SourceVideo({
  representation,
  seconds,
}: {
  representation: Representation;
  seconds: number;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [failed, setFailed] = useState(false);
  const seek = useCallback(() => {
    const video = videoRef.current;
    if (!video || video.readyState < 1) return;
    const target = Math.max(
      0,
      Math.min(
        seconds,
        Number.isFinite(video.duration) ? Math.max(0, video.duration - 0.035) : seconds,
      ),
    );
    if (Math.abs(video.currentTime - target) > 0.025) video.currentTime = target;
  }, [seconds]);
  useEffect(seek, [seek]);
  if (failed) return <span className="composition-missing">Source video unavailable</span>;
  return (
    <video
      ref={videoRef}
      src={representation.src}
      muted
      playsInline
      preload="auto"
      onLoadedMetadata={seek}
      onError={() => setFailed(true)}
      aria-label="Reference source footage"
    />
  );
}

/** Browser composition, not an encoded render. Every visible layer uses the current plan. */
export function CompositionPreview({
  composition,
  state,
  frame = 0,
  onSelect,
  selectedId,
  onChangeInstance,
}: CompositionPreviewProps) {
  const surfaceRef = useRef<HTMLDivElement>(null);
  const [surfaceWidth, setSurfaceWidth] = useState(280);
  const dragRef = useRef<{
    instance: SceneInstance;
    sceneId: string;
    pointerId: number;
    x: number;
    y: number;
    width: number;
    height: number;
  } | null>(null);
  const boundedFrame = Math.max(
    0,
    Math.min(Math.round(frame), Math.max(0, composition.totalFrames - 1)),
  );
  const scene = composition.scenes.find(
    (item) => boundedFrame >= item.startFrame && boundedFrame < item.endFrame,
  );
  useEffect(() => {
    const surface = surfaceRef.current;
    if (!surface) return;
    const observer = new ResizeObserver((entries) =>
      setSurfaceWidth(entries[0]?.contentRect.width || 280),
    );
    observer.observe(surface);
    return () => observer.disconnect();
  }, []);

  function beginDrag(
    event: PointerEvent<HTMLButtonElement>,
    instance: SceneInstance,
    currentScene: Scene,
  ) {
    onSelect?.(instance.id, currentScene.id);
    if (!onChangeInstance || event.button !== 0) return;
    const bounds = surfaceRef.current?.getBoundingClientRect();
    if (!bounds) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    dragRef.current = {
      instance,
      sceneId: currentScene.id,
      pointerId: event.pointerId,
      x: event.clientX,
      y: event.clientY,
      width: bounds.width,
      height: bounds.height,
    };
  }

  function moveDrag(event: PointerEvent<HTMLButtonElement>) {
    const drag = dragRef.current;
    if (!drag || event.pointerId !== drag.pointerId) return;
    onChangeInstance?.(drag.sceneId, drag.instance.id, {
      x: Math.round((drag.instance.x + (event.clientX - drag.x) / drag.width) * 1000) / 1000,
      y: Math.round((drag.instance.y + (event.clientY - drag.y) / drag.height) * 1000) / 1000,
    });
  }

  return (
    <div
      className="composition-preview"
      ref={surfaceRef}
      style={{
        aspectRatio: `${composition.canvas.width} / ${composition.canvas.height}`,
        background: scene?.background || '#24212d',
      }}
      aria-label={`Composition preview at frame ${boundedFrame}`}
    >
      {!scene && <div className="composition-missing">No scene at this frame</div>}
      {scene?.instances
        .filter(
          (instance) => boundedFrame >= instance.startFrame && boundedFrame < instance.endFrame,
        )
        .sort((a, b) => a.layer - b.layer || a.id.localeCompare(b.id))
        .map((instance) => {
          const representation = state.representations.find(
            (item) => item.id === instance.representationId,
          );
          const selected = selectedId === instance.id;
          const sourceFrame = instance.sourceInFrame + boundedFrame - instance.startFrame;
          const style: CSSProperties = {
            left: `${instance.x * 100}%`,
            top: `${instance.y * 100}%`,
            width: `${instance.width * 100}%`,
            height: `${instance.height * 100}%`,
            transform: `rotate(${instance.rotation}deg)`,
            opacity: instance.opacity,
            zIndex: instance.layer,
            color: instance.color,
            fontSize: Math.max(
              1,
              surfaceWidth * (instance.kind === 'text' && instance.height > 0.14 ? 0.095 : 0.065),
            ),
            background: instance.kind === 'shape' ? instance.color : undefined,
          };
          const visual =
            instance.kind === 'text' ? (
              <span className="composition-text">{instance.text || ''}</span>
            ) : instance.kind === 'shape' ? null : !representation ||
              representation.readiness !== 'ready' ? (
              <span className="composition-missing">
                {representation ? 'Media not ready' : 'Missing media'}
              </span>
            ) : instance.kind === 'video' &&
              representation.durationFrames !== undefined &&
              sourceFrame >= representation.durationFrames ? (
              <span className="composition-missing">Source ends here. Repair this interval.</span>
            ) : instance.kind === 'video' ? (
              <SourceVideo
                representation={representation}
                seconds={secondsAtFrame(composition, sourceFrame)}
              />
            ) : (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={representation.src} alt={instance.name} draggable={false} />
            );
          return onSelect ? (
            <button
              key={instance.id}
              type="button"
              className={`composition-instance ${selected ? 'composition-selected' : ''} ${onChangeInstance ? 'composition-movable' : ''}`}
              style={style}
              aria-label={`Select ${instance.name}`}
              aria-pressed={selected}
              onPointerDown={(event) => beginDrag(event, instance, scene)}
              onPointerMove={moveDrag}
              onPointerUp={() => {
                dragRef.current = null;
              }}
              onPointerCancel={() => {
                dragRef.current = null;
              }}
              onClick={() => onSelect(instance.id, scene.id)}
              onKeyDown={(event) => {
                if (
                  !onChangeInstance ||
                  !['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(event.key)
                )
                  return;
                event.preventDefault();
                const amount = event.shiftKey ? 0.01 : 0.001;
                onChangeInstance(scene.id, instance.id, {
                  x:
                    instance.x +
                    (event.key === 'ArrowRight' ? amount : event.key === 'ArrowLeft' ? -amount : 0),
                  y:
                    instance.y +
                    (event.key === 'ArrowDown' ? amount : event.key === 'ArrowUp' ? -amount : 0),
                });
              }}
            >
              {visual}
              {selected && (
                <>
                  <i className="composition-handle composition-handle-nw" />
                  <i className="composition-handle composition-handle-ne" />
                  <i className="composition-handle composition-handle-sw" />
                  <i className="composition-handle composition-handle-se" />
                </>
              )}
            </button>
          ) : (
            <div key={instance.id} className="composition-instance" style={style}>
              {visual}
            </div>
          );
        })}
    </div>
  );
}

interface NumberControlProps {
  label: string;
  value: number;
  onChange: (value: number) => void;
  min?: number;
  max?: number;
  step?: number;
  disabled?: boolean;
  suffix?: string;
}
function NumberControl({
  label,
  value,
  onChange,
  min,
  max,
  step = 1,
  disabled,
  suffix,
}: NumberControlProps) {
  const [text, setText] = useState(String(Math.round(value * 1000) / 1000));
  useEffect(() => {
    setText(String(Math.round(value * 1000) / 1000));
  }, [value]);
  return (
    <label className="editor-field">
      <span>{label}</span>
      <div className="editor-number-wrap">
        <input
          type="number"
          value={text}
          min={min}
          max={max}
          step={step}
          disabled={disabled}
          onChange={(event) => {
            setText(event.target.value);
            const next = Number(event.target.value);
            if (
              event.target.value !== '' &&
              Number.isFinite(next) &&
              (min === undefined || next >= min) &&
              (max === undefined || next <= max)
            )
              onChange(next);
          }}
          onBlur={() => setText(String(Math.round(value * 1000) / 1000))}
        />
        {suffix && <em>{suffix}</em>}
      </div>
    </label>
  );
}

export interface SceneEditorProps {
  state: WorkspaceState;
  content: ContentItem;
  execute: (command: Command) => Promise<CommandResult>;
  focusSceneId?: string;
  focusInstanceId?: string;
}

export function SceneEditor({
  state,
  content,
  execute,
  focusSceneId,
  focusInstanceId,
}: SceneEditorProps) {
  const [draft, setDraft] = useState(content.draft);
  const [selectedSceneId, setSelectedSceneId] = useState(
    focusSceneId || content.draft.scenes[0]?.id || '',
  );
  const [selectedInstanceId, setSelectedInstanceId] = useState(focusInstanceId || '');
  const [frame, setFrame] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [saveState, setSaveState] = useState('Draft saved locally');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [replacement, setReplacement] = useState<{
    baseline: Composition;
    representationId: string;
    protectedProperties: string[];
  } | null>(null);
  const draftRef = useRef(content.draft);
  const contentIdRef = useRef(content.id);
  const changeSequence = useRef(0);
  const pendingWrites = useRef(0);
  const dirty = useRef(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const writeChain = useRef<Promise<boolean>>(Promise.resolve(true));
  const executeRef = useRef(execute);
  const replacementDialogRef = useRef<HTMLElement>(null);
  executeRef.current = execute;
  const editable = canEdit(state.role) && !busy;
  const scene = draft.scenes.find((item) => item.id === selectedSceneId) || draft.scenes[0];
  const instance = scene?.instances.find((item) => item.id === selectedInstanceId);
  const fps = draft.fps.numerator / draft.fps.denominator;
  const revision = state.revisions.find((item) => item.id === content.currentRevisionId);

  const persist = useCallback(() => {
    if (timer.current) {
      clearTimeout(timer.current);
      timer.current = null;
    }
    if (!dirty.current) return writeChain.current;
    const snapshot = draftRef.current;
    const sequence = changeSequence.current;
    const contentId = contentIdRef.current;
    pendingWrites.current += 1;
    setSaveState('Saving draft…');
    writeChain.current = writeChain.current
      .catch(() => false)
      .then(async () => {
        try {
          const result = await executeRef.current({
            type: 'updateDraft',
            contentId,
            draft: snapshot,
          });
          if (contentIdRef.current === contentId && sequence === changeSequence.current) {
            dirty.current = !result.ok;
            setSaveState(result.ok ? 'Draft saved locally' : 'Draft not saved');
            if (!result.ok) setNotice(result.message);
          }
          return result.ok;
        } catch {
          if (contentIdRef.current === contentId) {
            setSaveState('Draft not saved');
            setNotice('Local save failed. Your edits remain here; save again to retry.');
          }
          return false;
        } finally {
          pendingWrites.current -= 1;
        }
      });
    return writeChain.current;
  }, []);

  useEffect(() => {
    if (content.id !== contentIdRef.current) {
      if (dirty.current) void persist();
      if (timer.current) clearTimeout(timer.current);
      contentIdRef.current = content.id;
      dirty.current = false;
      changeSequence.current += 1;
      draftRef.current = content.draft;
      setDraft(content.draft);
      setSelectedSceneId(focusSceneId || content.draft.scenes[0]?.id || '');
      setSelectedInstanceId(focusInstanceId || '');
      setFrame(0);
      setPlaying(false);
      setReplacement(null);
      setNotice('');
      setSaveState('Draft saved locally');
    } else if (!dirty.current && pendingWrites.current === 0) {
      draftRef.current = content.draft;
      setDraft(content.draft);
    }
  }, [content.id, content.draft, focusSceneId, focusInstanceId, persist]);

  const replacementOpen = replacement !== null;
  useEffect(() => {
    if (!replacementOpen) return;
    const previouslyFocused =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const dialog = replacementDialogRef.current;
    dialog?.querySelector<HTMLElement>('button, select, input')?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setReplacement(null);
        return;
      }
      if (event.key !== 'Tab' || !dialog) return;
      const focusable = Array.from(
        dialog.querySelectorAll<HTMLElement>(
          'button:not(:disabled), select:not(:disabled), input:not(:disabled), [tabindex="0"]',
        ),
      );
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    };
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('keydown', onKey);
      previouslyFocused?.focus();
    };
  }, [replacementOpen]);

  useEffect(() => {
    if (!focusSceneId && !focusInstanceId) return;
    const targetScene = draftRef.current.scenes.find(
      (item) =>
        item.id === focusSceneId || item.instances.some((layer) => layer.id === focusInstanceId),
    );
    if (targetScene) {
      setSelectedSceneId(targetScene.id);
      setSelectedInstanceId(focusInstanceId || '');
      setFrame(targetScene.startFrame);
    }
  }, [focusSceneId, focusInstanceId]);

  useEffect(
    () => () => {
      void persist();
    },
    [persist],
  );

  useEffect(() => {
    if (!playing) return;
    const startedAt = performance.now();
    const startFrame = frame;
    let request = 0;
    const tick = (now: number) => {
      const next = startFrame + Math.floor(((now - startedAt) * fps) / 1000);
      if (next >= draft.totalFrames) {
        setFrame(Math.max(0, draft.totalFrames - 1));
        setPlaying(false);
        return;
      }
      setFrame(next);
      request = requestAnimationFrame(tick);
    };
    request = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(request);
    // Frame is captured at playback start; depending on every tick would restart the clock.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playing, fps, draft.totalFrames]);

  function update(next: Composition) {
    if (!editable) return;
    draftRef.current = next;
    setDraft(next);
    dirty.current = true;
    changeSequence.current += 1;
    setSaveState('Unsaved changes');
    setFrame((current) => Math.min(current, Math.max(0, next.totalFrames - 1)));
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      void persist();
    }, 300);
  }

  function changeInstance(sceneId: string, instanceId: string, patch: Partial<SceneInstance>) {
    const current = draftRef.current;
    update({
      ...current,
      scenes: current.scenes.map((item) =>
        item.id === sceneId
          ? {
              ...item,
              instances: item.instances.map((layer) =>
                layer.id === instanceId ? { ...layer, ...patch } : layer,
              ),
            }
          : item,
      ),
    });
  }

  function changeScene(patch: Partial<Scene>) {
    if (!scene) return;
    const current = draftRef.current;
    update({
      ...current,
      scenes: current.scenes.map((item) => (item.id === scene.id ? { ...item, ...patch } : item)),
    });
  }

  function selectLayer(instanceId: string, sceneId: string) {
    setSelectedSceneId(sceneId);
    setSelectedInstanceId(instanceId);
    const selected = draftRef.current.scenes
      .find((item) => item.id === sceneId)
      ?.instances.find((item) => item.id === instanceId);
    if (selected && (frame < selected.startFrame || frame >= selected.endFrame)) {
      setFrame(selected.startFrame);
      setPlaying(false);
    }
  }

  async function action(type: 'saveRevision' | 'createPreview') {
    setBusy(true);
    setPlaying(false);
    const saved = await persist();
    if (saved) {
      try {
        const result = await executeRef.current({ type, contentId: content.id });
        setNotice(result.message);
      } catch {
        setNotice(
          'The simulated service could not complete this action. Your local draft is preserved.',
        );
      }
    }
    setBusy(false);
  }

  function moveScene(direction: -1 | 1) {
    if (!scene) return;
    const next = reorderScene(draftRef.current, scene.id, direction);
    update(next);
    setPlaying(false);
    setFrame(next.scenes.find((item) => item.id === scene.id)?.startFrame || 0);
  }

  function addText() {
    if (!scene) return;
    const id = `text-${Date.now()}`;
    changeScene({
      instances: [
        ...scene.instances,
        {
          id,
          name: 'New text',
          kind: 'text',
          text: 'Your next idea starts here.',
          color: '#ffffff',
          x: 0.1,
          y: 0.12,
          width: 0.8,
          height: 0.16,
          rotation: 0,
          opacity: 1,
          startFrame: scene.startFrame,
          endFrame: scene.endFrame,
          sourceInFrame: 0,
          layer: Math.max(0, ...scene.instances.map((item) => item.layer)) + 1,
          relation: 'overlay',
          protectedProperties: [],
        },
      ],
    });
    setSelectedInstanceId(id);
    setFrame(scene.startFrame);
  }

  const activeScene = draft.scenes.find(
    (item) => frame >= item.startFrame && frame < item.endFrame,
  );
  const currentRepresentation = state.representations.find(
    (item) => item.id === instance?.representationId,
  );
  const candidates = state.representations.filter(
    (item) =>
      item.readiness === 'ready' &&
      item.rights === 'eligible' &&
      (item.mediaType === 'image' || item.mediaType === 'video') &&
      item.id !== instance?.representationId,
  );
  const candidateRepresentation = state.representations.find(
    (item) => item.id === replacement?.representationId,
  );
  const candidateVersion = state.assetVersions.find(
    (item) => item.id === candidateRepresentation?.assetVersionId,
  );
  const candidateAsset = state.assets.find((item) => item.id === candidateVersion?.assetId);
  const candidatePatch: Partial<SceneInstance> = candidateRepresentation
    ? {
        representationId: candidateRepresentation.id,
        assetVersionId: candidateRepresentation.assetVersionId,
        assetId: candidateVersion?.assetId,
        kind: candidateRepresentation.mediaType === 'video' ? 'video' : 'image',
        protectedProperties: replacement?.protectedProperties || [],
        sourceInFrame: 0,
      }
    : {};
  const candidateComposition =
    replacement && scene && instance
      ? {
          ...replacement.baseline,
          scenes: replacement.baseline.scenes.map((item) =>
            item.id === scene.id
              ? {
                  ...item,
                  instances: item.instances.map((layer) =>
                    layer.id === instance.id ? { ...layer, ...candidatePatch } : layer,
                  ),
                }
              : item,
          ),
        }
      : null;
  const sourceTooShort =
    currentRepresentation?.mediaType === 'video' &&
    currentRepresentation.durationFrames !== undefined &&
    instance &&
    instance.sourceInFrame + instance.endFrame - instance.startFrame >
      currentRepresentation.durationFrames;

  return (
    <section className="editor-root" aria-label="Scene and timeline editor">
      <div className="editor-toolbar">
        <div>
          <span className="editor-eyebrow">COMPOSITION STUDIO</span>
          <h2>Make every frame count.</h2>
          <p>Arrange your story. Keep the details that matter.</p>
        </div>
        <div className="editor-toolbar-actions">
          <span className="editor-save-status" role="status">
            {saveState}
          </span>
          <button
            type="button"
            disabled={!editable || busy}
            onClick={() => void action('saveRevision')}
          >
            Save revision
          </button>
          <button
            type="button"
            className="editor-primary"
            disabled={!editable || busy}
            onClick={() => void action('createPreview')}
          >
            Create preview <span>↗</span>
          </button>
        </div>
      </div>
      <div className="editor-context-strip">
        <span>
          <i /> LIVE BROWSER COMPOSITION
        </span>
        <span>
          {draft.canvas.width} × {draft.canvas.height} · {fps.toFixed(2).replace(/\.00$/, '')} fps ·{' '}
          {secondsAtFrame(draft, draft.totalFrames).toFixed(1)} sec
        </span>
        <span>
          {revision ? `Based on revision ${revision.number}` : 'Unsaved creative revision'}
        </span>
      </div>
      {!canEdit(state.role) && (
        <div className="editor-notice">
          {state.role === 'reviewer' ? 'Reviewer' : 'Read-only'} view: inspect, scrub and compare.
          Editing requires owner or editor authority.
        </div>
      )}
      {notice && (
        <div className="editor-notice" role="status">
          {notice}
          <button aria-label="Dismiss editor message" type="button" onClick={() => setNotice('')}>
            ×
          </button>
        </div>
      )}
      <div className="editor-workbench">
        <aside className="editor-storyboard" aria-label="Storyboard and layers">
          <div className="editor-panel-heading">
            <h3>Storyboard</h3>
            <span>{draft.scenes.length} scenes</span>
          </div>
          <div className="editor-scene-list">
            {draft.scenes.map((item, index) => (
              <button
                key={item.id}
                type="button"
                className={`editor-scene-card ${scene?.id === item.id ? 'is-active' : ''}`}
                onClick={() => {
                  setSelectedSceneId(item.id);
                  setSelectedInstanceId('');
                  setFrame(item.startFrame);
                  setPlaying(false);
                }}
                aria-pressed={scene?.id === item.id}
              >
                <div className="editor-scene-thumb">
                  <CompositionPreview composition={draft} state={state} frame={item.startFrame} />
                </div>
                <div>
                  <span className="editor-scene-index">
                    SCENE {String(index + 1).padStart(2, '0')}
                  </span>
                  <strong>{item.name}</strong>
                  <small>
                    {secondsAtFrame(draft, item.endFrame - item.startFrame).toFixed(1)} sec
                  </small>
                </div>
              </button>
            ))}
          </div>
          <div className="editor-panel-heading">
            <h3>Layers</h3>
            <button
              type="button"
              className="editor-icon-button"
              onClick={addText}
              disabled={!editable || !scene}
              aria-label="Add text layer"
            >
              +
            </button>
          </div>
          <div className="editor-layer-list">
            {scene?.instances
              .slice()
              .sort((a, b) => b.layer - a.layer)
              .map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className={`editor-layer ${instance?.id === item.id ? 'is-active' : ''}`}
                  onClick={() => selectLayer(item.id, scene.id)}
                  aria-pressed={instance?.id === item.id}
                >
                  <span className={`editor-layer-icon editor-layer-icon-${item.kind}`}>
                    {item.kind === 'text'
                      ? 'T'
                      : item.kind === 'video'
                        ? '▷'
                        : item.kind === 'shape'
                          ? '■'
                          : '◇'}
                  </span>
                  <span>
                    {item.name}
                    <small>{item.relation.replace('_', ' ')}</small>
                  </span>
                  <span className="editor-layer-order">{item.layer}</span>
                </button>
              ))}
          </div>
          <p className="editor-panel-footnote">
            Select a layer or click an object on the canvas. Use arrow keys to nudge; Shift for a
            larger move.
          </p>
        </aside>
        <main className="editor-stage">
          <div className="editor-stage-top">
            <span>{activeScene?.name || 'Composition'}</span>
            <span className="editor-demo-label">INTERACTIVE PREVIEW</span>
          </div>
          <div className="editor-canvas-area">
            <CompositionPreview
              composition={draft}
              state={state}
              frame={frame}
              selectedId={selectedInstanceId}
              onSelect={selectLayer}
              onChangeInstance={editable ? changeInstance : undefined}
            />
          </div>
          <div className="editor-stage-bottom">
            <span>9:16</span>
            <span>
              {selectedInstanceId
                ? 'Drag to move · resize in inspector'
                : 'Click an object to inspect it'}
            </span>
            <span>Fit</span>
          </div>
        </main>
        <aside className="editor-inspector" aria-label="Scene property inspector">
          <div className="editor-panel-heading">
            <h3>{instance ? 'Object inspector' : 'Scene settings'}</h3>
            {instance && (
              <button
                type="button"
                className="editor-icon-button"
                aria-label="Show scene settings"
                onClick={() => setSelectedInstanceId('')}
              >
                ×
              </button>
            )}
          </div>
          {instance && scene ? (
            <>
              <div className="editor-object-heading">
                <span className="editor-object-symbol">{instance.kind === 'text' ? 'T' : '◇'}</span>
                <div>
                  <strong>{instance.name}</strong>
                  <small>
                    {instance.kind} · layer {instance.layer}
                  </small>
                </div>
              </div>
              <label className="editor-field">
                <span>Layer name</span>
                <input
                  value={instance.name}
                  disabled={!editable}
                  onChange={(event) =>
                    changeInstance(scene.id, instance.id, { name: event.target.value })
                  }
                />
              </label>
              {instance.kind === 'text' && (
                <label className="editor-field">
                  <span>Exact on-screen text</span>
                  <textarea
                    rows={3}
                    value={instance.text || ''}
                    disabled={!editable}
                    onChange={(event) =>
                      changeInstance(scene.id, instance.id, { text: event.target.value })
                    }
                  />
                </label>
              )}
              <h4 className="editor-section-label">TRANSFORM</h4>
              <div className="editor-field-grid">
                <NumberControl
                  label="X position"
                  value={instance.x * 100}
                  min={-100}
                  max={200}
                  step={0.1}
                  suffix="%"
                  disabled={!editable}
                  onChange={(value) => changeInstance(scene.id, instance.id, { x: value / 100 })}
                />
                <NumberControl
                  label="Y position"
                  value={instance.y * 100}
                  min={-100}
                  max={200}
                  step={0.1}
                  suffix="%"
                  disabled={!editable}
                  onChange={(value) => changeInstance(scene.id, instance.id, { y: value / 100 })}
                />
                <NumberControl
                  label="Width"
                  value={instance.width * 100}
                  min={1}
                  max={200}
                  step={0.1}
                  suffix="%"
                  disabled={!editable}
                  onChange={(value) =>
                    changeInstance(scene.id, instance.id, { width: value / 100 })
                  }
                />
                <NumberControl
                  label="Height"
                  value={instance.height * 100}
                  min={1}
                  max={200}
                  step={0.1}
                  suffix="%"
                  disabled={!editable}
                  onChange={(value) =>
                    changeInstance(scene.id, instance.id, { height: value / 100 })
                  }
                />
                <NumberControl
                  label="Rotation"
                  value={instance.rotation}
                  min={-360}
                  max={360}
                  suffix="°"
                  disabled={!editable}
                  onChange={(value) => changeInstance(scene.id, instance.id, { rotation: value })}
                />
                <NumberControl
                  label="Opacity"
                  value={instance.opacity * 100}
                  min={0}
                  max={100}
                  suffix="%"
                  disabled={!editable}
                  onChange={(value) =>
                    changeInstance(scene.id, instance.id, { opacity: value / 100 })
                  }
                />
              </div>
              {(instance.kind === 'text' || instance.kind === 'shape') && (
                <label className="editor-field editor-color-field">
                  <span>Color</span>
                  <input
                    type="color"
                    value={/^#[0-9a-f]{6}$/i.test(instance.color) ? instance.color : '#ffffff'}
                    disabled={!editable}
                    onChange={(event) =>
                      changeInstance(scene.id, instance.id, { color: event.target.value })
                    }
                  />
                  <code>{instance.color}</code>
                </label>
              )}
              <h4 className="editor-section-label">TIMING · GLOBAL FRAMES</h4>
              <div className="editor-field-grid">
                <NumberControl
                  label="Start frame"
                  value={instance.startFrame}
                  min={scene.startFrame}
                  max={instance.endFrame - 1}
                  disabled={!editable}
                  onChange={(value) =>
                    changeInstance(scene.id, instance.id, { startFrame: Math.round(value) })
                  }
                />
                <NumberControl
                  label="End frame (exclusive)"
                  value={instance.endFrame}
                  min={instance.startFrame + 1}
                  max={scene.endFrame}
                  disabled={!editable}
                  onChange={(value) =>
                    changeInstance(scene.id, instance.id, { endFrame: Math.round(value) })
                  }
                />
              </div>
              {instance.kind === 'video' && (
                <NumberControl
                  label="Source in frame"
                  value={instance.sourceInFrame}
                  min={0}
                  max={
                    currentRepresentation?.durationFrames === undefined
                      ? undefined
                      : currentRepresentation.durationFrames - 1
                  }
                  disabled={!editable}
                  onChange={(value) =>
                    changeInstance(scene.id, instance.id, { sourceInFrame: Math.round(value) })
                  }
                />
              )}
              {sourceTooShort && (
                <p className="editor-inline-error">
                  Source footage is too short for this interval. Shorten the event, change source
                  in, or choose another asset. No implicit freeze or loop is approved.
                </p>
              )}
              <h4 className="editor-section-label">RELATIONSHIP</h4>
              <label className="editor-field">
                <span>Composition relationship</span>
                <select
                  value={instance.relation}
                  disabled={!editable}
                  onChange={(event) =>
                    changeInstance(scene.id, instance.id, {
                      relation: event.target.value as SceneInstance['relation'],
                    })
                  }
                >
                  <option value="independent">Independent</option>
                  <option value="on_surface">On a surface</option>
                  <option value="behind">Behind an object</option>
                  <option value="overlay">Overlay</option>
                </select>
              </label>
              {['on_surface', 'behind'].includes(instance.relation) && (
                <label className="editor-field">
                  <span>Related object</span>
                  <select
                    value={instance.targetInstanceId || ''}
                    disabled={!editable}
                    onChange={(event) =>
                      changeInstance(scene.id, instance.id, {
                        targetInstanceId: event.target.value || undefined,
                      })
                    }
                  >
                    <option value="">Choose a supporting object</option>
                    {scene.instances
                      .filter((item) => item.id !== instance.id)
                      .map((item) => (
                        <option key={item.id} value={item.id}>
                          {item.name}
                        </option>
                      ))}
                  </select>
                </label>
              )}
              <p className="editor-panel-footnote">
                Relationships express intent. Physical contact and occlusion have not been measured
                in this prototype.
              </p>
              <NumberControl
                label="Draw order"
                value={instance.layer}
                min={0}
                max={99}
                disabled={!editable}
                onChange={(value) =>
                  changeInstance(scene.id, instance.id, { layer: Math.round(value) })
                }
              />
              {instance.representationId && (
                <>
                  <h4 className="editor-section-label">PINNED ASSET</h4>
                  <div className="editor-asset-reference">
                    <strong>
                      {state.assets.find((item) => item.id === instance.assetId)?.name ||
                        instance.name}
                    </strong>
                    <span>
                      {currentRepresentation?.rights === 'eligible'
                        ? 'Eligible for this demo'
                        : 'Eligibility needs review'}
                    </span>
                    <small>{currentRepresentation?.rightsNote}</small>
                  </div>
                  <button
                    type="button"
                    className="editor-full-button"
                    disabled={!editable || candidates.length === 0}
                    onClick={() => {
                      setPlaying(false);
                      setReplacement({
                        baseline: draft,
                        representationId: candidates[0]?.id || '',
                        protectedProperties: ['Background', 'Other objects', 'Timing', 'Camera'],
                      });
                    }}
                  >
                    Replace object <span>↗</span>
                  </button>
                  {!candidates.length && (
                    <p className="editor-panel-footnote">
                      No ready, eligible replacement is available.
                    </p>
                  )}
                </>
              )}
              <details className="editor-diagnostics">
                <summary>Identity & provenance</summary>
                <dl>
                  <dt>Instance</dt>
                  <dd>{instance.id}</dd>
                  <dt>Asset identity</dt>
                  <dd>{instance.assetId || 'Local graphic'}</dd>
                  <dt>Version</dt>
                  <dd>{instance.assetVersionId || 'Plan revision'}</dd>
                  <dt>Representation</dt>
                  <dd>{instance.representationId || 'Procedural'}</dd>
                  <dt>Protected properties</dt>
                  <dd>{instance.protectedProperties.join(', ') || 'None declared'}</dd>
                </dl>
              </details>
            </>
          ) : scene ? (
            <>
              <label className="editor-field">
                <span>Scene name</span>
                <input
                  value={scene.name}
                  disabled={!editable}
                  onChange={(event) => changeScene({ name: event.target.value })}
                />
              </label>
              <label className="editor-field">
                <span>Scene purpose</span>
                <textarea
                  rows={3}
                  value={scene.purpose}
                  disabled={!editable}
                  onChange={(event) => changeScene({ purpose: event.target.value })}
                />
              </label>
              <NumberControl
                label="Scene duration"
                value={scene.endFrame - scene.startFrame}
                min={1}
                max={1800}
                suffix="frames"
                disabled={!editable}
                onChange={(value) => update(resizeScene(draftRef.current, scene.id, value))}
              />
              <p className="editor-panel-footnote">
                Duration changes retime every layer and audio interval together. Source media stays
                at 1× speed; source length is rechecked.
              </p>
              <label className="editor-field editor-color-field">
                <span>Background</span>
                <input
                  type="color"
                  value={/^#[0-9a-f]{6}$/i.test(scene.background) ? scene.background : '#30202e'}
                  disabled={!editable}
                  onChange={(event) => changeScene({ background: event.target.value })}
                />
                <code>{scene.background}</code>
              </label>
              <h4 className="editor-section-label">STORY ORDER</h4>
              <div className="editor-field-grid">
                <button
                  type="button"
                  disabled={!editable || draft.scenes[0]?.id === scene.id}
                  onClick={() => moveScene(-1)}
                >
                  ← Move earlier
                </button>
                <button
                  type="button"
                  disabled={!editable || draft.scenes[draft.scenes.length - 1]?.id === scene.id}
                  onClick={() => moveScene(1)}
                >
                  Move later →
                </button>
              </div>
              <p className="editor-panel-footnote">
                Scene order preserves each scene’s local timing and moves its text, source media and
                audio together.
              </p>
              <button
                type="button"
                className="editor-full-button"
                onClick={addText}
                disabled={!editable}
              >
                + Add text layer
              </button>
              <h4 className="editor-section-label">AUDIO EVENTS</h4>
              {scene.audio.length === 0 ? (
                <p className="editor-panel-footnote">
                  No audio event in this scene. Composition playback is silent.
                </p>
              ) : (
                scene.audio.map((event) => (
                  <div className="editor-audio-settings" key={event.id}>
                    <strong>{event.role === 'voice' ? 'Voice guide' : 'Music guide'}</strong>
                    <div className="editor-field-grid">
                      <NumberControl
                        label={`${event.role} start frame`}
                        value={event.startFrame}
                        min={scene.startFrame}
                        max={event.endFrame - 1}
                        disabled={!editable}
                        onChange={(value) =>
                          changeScene({
                            audio: scene.audio.map((item) =>
                              item.id === event.id
                                ? { ...item, startFrame: Math.round(value) }
                                : item,
                            ),
                          })
                        }
                      />
                      <NumberControl
                        label={`${event.role} end frame`}
                        value={event.endFrame}
                        min={event.startFrame + 1}
                        max={scene.endFrame}
                        disabled={!editable}
                        onChange={(value) =>
                          changeScene({
                            audio: scene.audio.map((item) =>
                              item.id === event.id
                                ? { ...item, endFrame: Math.round(value) }
                                : item,
                            ),
                          })
                        }
                      />
                    </div>
                    <NumberControl
                      label={`${event.role} gain`}
                      value={event.gain}
                      min={0}
                      max={2}
                      step={0.1}
                      disabled={!editable}
                      onChange={(value) =>
                        changeScene({
                          audio: scene.audio.map((item) =>
                            item.id === event.id ? { ...item, gain: value } : item,
                          ),
                        })
                      }
                    />
                    <audio
                      controls
                      preload="none"
                      src={
                        state.representations.find((item) => item.id === event.representationId)
                          ?.src
                      }
                      aria-label={`${event.role} reference audio`}
                    />
                    <small>Reference audio audition. A mixed soundtrack is simulated.</small>
                  </div>
                ))
              )}
            </>
          ) : (
            <p className="editor-panel-footnote">This composition has no scenes.</p>
          )}
        </aside>
      </div>
      <div className="editor-timeline" aria-label="Media timeline">
        <div className="editor-transport">
          <div className="editor-transport-buttons">
            <button
              type="button"
              className="editor-icon-button"
              aria-label="Go to first frame"
              onClick={() => {
                setPlaying(false);
                setFrame(0);
              }}
            >
              ↤
            </button>
            <button
              type="button"
              className="editor-play"
              aria-label={playing ? 'Pause composition' : 'Play composition'}
              onClick={() => {
                if (!playing && frame >= draft.totalFrames - 1) setFrame(0);
                setPlaying((value) => !value);
              }}
            >
              {playing ? 'Ⅱ' : '▶'}
            </button>
            <span className="editor-timecode">
              {secondsAtFrame(draft, frame).toFixed(2)}{' '}
              <span>/ {secondsAtFrame(draft, draft.totalFrames).toFixed(2)}s</span>
            </span>
          </div>
          <span className="editor-playback-note">
            Canvas playback · reference footage muted · no encoded render
          </span>
          <label className="editor-frame-input">
            Frame{' '}
            <input
              aria-label="Current frame"
              type="number"
              min={0}
              max={Math.max(0, draft.totalFrames - 1)}
              value={frame}
              onChange={(event) => {
                setPlaying(false);
                setFrame(
                  Math.max(
                    0,
                    Math.min(
                      Math.round(Number(event.target.value)),
                      Math.max(0, draft.totalFrames - 1),
                    ),
                  ),
                );
              }}
            />
          </label>
        </div>
        <div className="editor-timeline-grid">
          <div className="editor-track-name">STORY</div>
          <div className="editor-timeline-ruler">
            {Array.from({ length: 7 }, (_, index) => (
              <span key={index}>
                {secondsAtFrame(draft, Math.round((draft.totalFrames * index) / 6)).toFixed(1)}s
              </span>
            ))}
          </div>
          <div className="editor-track-name">
            SCENES <span>◇</span>
          </div>
          <div className="editor-track editor-scene-track">
            {draft.scenes.map((item, index) => (
              <button
                type="button"
                key={item.id}
                className={scene?.id === item.id ? 'is-active' : ''}
                style={{
                  left: `${(item.startFrame / Math.max(1, draft.totalFrames)) * 100}%`,
                  width: `${((item.endFrame - item.startFrame) / Math.max(1, draft.totalFrames)) * 100}%`,
                  background: item.background,
                }}
                onClick={() => {
                  setSelectedSceneId(item.id);
                  setSelectedInstanceId('');
                  setFrame(item.startFrame);
                  setPlaying(false);
                }}
              >
                <b>{String(index + 1).padStart(2, '0')}</b> {item.name}
              </button>
            ))}
            <i
              className="editor-playhead"
              style={{ left: `${(frame / Math.max(1, draft.totalFrames)) * 100}%` }}
            />
          </div>
          <div className="editor-track-name">
            TEXT <span>T</span>
          </div>
          <div className="editor-track editor-text-track">
            {draft.scenes.flatMap((item) =>
              item.instances
                .filter((layer) => layer.kind === 'text')
                .map((layer) => (
                  <button
                    type="button"
                    key={layer.id}
                    title={layer.text}
                    style={{
                      left: `${(layer.startFrame / Math.max(1, draft.totalFrames)) * 100}%`,
                      width: `${((layer.endFrame - layer.startFrame) / Math.max(1, draft.totalFrames)) * 100}%`,
                    }}
                    onClick={() => selectLayer(layer.id, item.id)}
                  >
                    {layer.text}
                  </button>
                )),
            )}
          </div>
          <div className="editor-track-name">
            AUDIO <span>≋</span>
          </div>
          <div className="editor-track editor-audio-track">
            {draft.scenes.flatMap((item) =>
              item.audio.map((event) => (
                <button
                  type="button"
                  key={event.id}
                  title={`${event.role}: frames ${event.startFrame}–${event.endFrame}, gain ${event.gain}`}
                  style={{
                    left: `${(event.startFrame / Math.max(1, draft.totalFrames)) * 100}%`,
                    width: `${((event.endFrame - event.startFrame) / Math.max(1, draft.totalFrames)) * 100}%`,
                    opacity: Math.max(0.25, Math.min(1, event.gain)),
                  }}
                  onClick={() => {
                    setSelectedSceneId(item.id);
                    setSelectedInstanceId('');
                    setFrame(event.startFrame);
                    setPlaying(false);
                  }}
                >
                  {event.role} · guide
                </button>
              )),
            )}
            {draft.scenes.every((item) => item.audio.length === 0) && (
              <span className="editor-empty-track">No audio events · intentional silence</span>
            )}
          </div>
          <div className="editor-track-name">SCRUB</div>
          <input
            className="editor-scrubber"
            type="range"
            min={0}
            max={Math.max(0, draft.totalFrames - 1)}
            value={frame}
            aria-label="Scrub composition timeline"
            onChange={(event) => {
              setPlaying(false);
              setFrame(Number(event.target.value));
            }}
          />
        </div>
      </div>
      {replacement && instance && scene && (
        <div
          className="editor-dialog-backdrop"
          onClick={(event) => {
            if (event.target === event.currentTarget) setReplacement(null);
          }}
        >
          <section
            ref={replacementDialogRef}
            className="editor-replacement-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="editor-replace-title"
          >
            <div className="editor-dialog-heading">
              <div>
                <span className="editor-eyebrow">A PRECISE CHANGE, A NEW REVISION</span>
                <h3 id="editor-replace-title">Replace {instance.name}</h3>
              </div>
              <button
                type="button"
                aria-label="Close replacement comparison"
                onClick={() => setReplacement(null)}
              >
                ×
              </button>
            </div>
            <div className="editor-replacement-body">
              <div className="editor-replacement-controls">
                <label className="editor-field">
                  <span>Ready, eligible replacement</span>
                  <select
                    value={replacement.representationId}
                    onChange={(event) =>
                      setReplacement({ ...replacement, representationId: event.target.value })
                    }
                  >
                    {candidates.map((item) => {
                      const version = state.assetVersions.find(
                        (value) => value.id === item.assetVersionId,
                      );
                      const asset = state.assets.find((value) => value.id === version?.assetId);
                      return (
                        <option key={item.id} value={item.id}>
                          {asset?.name || item.id} · {item.mediaType}
                        </option>
                      );
                    })}
                  </select>
                </label>
                <div className="editor-route">
                  <strong>✓ Local layer replacement</strong>
                  <p>
                    Updates this occurrence’s media reference. Position, size, other objects and
                    timing stay pinned.
                  </p>
                </div>
                <div className="editor-route editor-route-disabled">
                  <strong>Masked generative edit · unavailable</strong>
                  <p>No verified provider or protected-region measurement is connected.</p>
                </div>
                <h4 className="editor-section-label">KEEP UNCHANGED</h4>
                {['Background', 'Other objects', 'Timing', 'Camera'].map((property) => (
                  <label className="editor-protected-option" key={property}>
                    <input
                      type="checkbox"
                      checked={replacement.protectedProperties.includes(property)}
                      onChange={(event) =>
                        setReplacement({
                          ...replacement,
                          protectedProperties: event.target.checked
                            ? [...replacement.protectedProperties, property]
                            : replacement.protectedProperties.filter((item) => item !== property),
                        })
                      }
                    />
                    {property}
                  </label>
                ))}
                <p className="editor-panel-footnote">
                  Scope is the selected occurrence during frames [{instance.startFrame},{' '}
                  {instance.endFrame}). Its aspect ratio follows the current display box.
                </p>
              </div>
              <div className="editor-candidate-review">
                <div className="editor-comparison-grid">
                  <div>
                    <span>BEFORE · CURRENT DRAFT</span>
                    <CompositionPreview
                      composition={replacement.baseline}
                      state={state}
                      frame={Math.max(instance.startFrame, Math.min(frame, instance.endFrame - 1))}
                    />
                  </div>
                  <div>
                    <span>AFTER · {candidateAsset?.name || 'CANDIDATE'}</span>
                    {candidateComposition && (
                      <CompositionPreview
                        composition={candidateComposition}
                        state={state}
                        frame={Math.max(
                          instance.startFrame,
                          Math.min(frame, instance.endFrame - 1),
                        )}
                      />
                    )}
                  </div>
                </div>
                <div className="editor-evidence-note">
                  <strong>Simulated review · visual identity not evaluated</strong>
                  <p>
                    The local plan preserves all untouched layer values. This is structural
                    evidence, not pixel analysis, product certification or a measured generative
                    result. Review the candidate at delivery size before real production.
                  </p>
                </div>
              </div>
            </div>
            <div className="editor-dialog-footer">
              <p>Applying creates a changed draft. Previous output and approval remain intact.</p>
              <button type="button" onClick={() => setReplacement(null)}>
                Cancel
              </button>
              <button
                type="button"
                className="editor-primary"
                disabled={!editable || !candidateRepresentation}
                onClick={() => {
                  changeInstance(scene.id, instance.id, candidatePatch);
                  setReplacement(null);
                  setNotice(
                    'Replacement applied to the draft. Save a new revision, then create a new preview and review it. Previous approvals do not cover this edit.',
                  );
                }}
              >
                Apply to draft
              </button>
            </div>
          </section>
        </div>
      )}
    </section>
  );
}
