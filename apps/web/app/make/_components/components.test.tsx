// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { quickReelFixtures } from '@content-lab/reel-templates';

import { branchSet, hooks } from '../_lib/fixtures.test-data';
import type { RenderJobView } from '../_lib/types';
import { holdFrame } from './BuildStage';
import { ChoiceSheet } from './ChoiceSheet';
import { HookReel } from './HookReel';
import { KeyboardHelp } from './KeyboardHelp';
import { ShipScreen, type ShipScreenProps } from './ShipScreen';

vi.mock('./ReelPlayer', () => ({
  ReelPlayer: ({ timeline }: { timeline: { durationInFrames: number } }) => (
    <div data-testid="player" data-frames={timeline.durationInFrames} />
  ),
}));

afterEach(cleanup);
const timeline = quickReelFixtures.punchy;

describe('ChoiceSheet', () => {
  const cards = branchSet.energy.map((option, i) => ({ option, timeline: i === 2 ? undefined : timeline }));

  it('asks the story question and shows a live preview per card (or a shimmer while composing)', () => {
    render(
      <ChoiceSheet moment="energy" cards={cards} focused={0} onChoose={vi.fn()} onFocus={vi.fn()} onSurprise={vi.fn()} />,
    );
    expect(screen.getByRole('heading').textContent).toBe('Pick the energy');
    expect(screen.getAllByRole('radio')).toHaveLength(3);
    expect(screen.getAllByTestId('player')).toHaveLength(2);
    expect(screen.getByRole('radio', { name: /3\. Dramatic/ })).toBeTruthy();
  });

  it('a tap chooses that option; the current one is marked when changing one thing', () => {
    const onChoose = vi.fn();
    const onSurprise = vi.fn();
    render(
      <ChoiceSheet moment="energy" cards={cards} focused={1} current="chill" onChoose={onChoose} onFocus={vi.fn()} onSurprise={onSurprise} />,
    );
    fireEvent.click(screen.getByRole('radio', { name: /Fast & punchy/ }));
    expect(onChoose).toHaveBeenCalledWith('punchy');
    expect(screen.getByRole('radio', { name: /Chill/ }).getAttribute('aria-checked')).toBe('true');
    expect(screen.getByText('Now')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /Surprise me/ }));
    expect(onSurprise).toHaveBeenCalledOnce();
  });
});

describe('HookReel', () => {
  const base = {
    topic: 'crispy potatoes',
    focused: 0,
    visuals: [],
    source: 'fallback' as const,
    surprising: false,
    error: null,
    onFocus: vi.fn(),
    onChoose: vi.fn(),
    onSurprise: vi.fn(),
    onRetry: vi.fn(),
  };

  it('keeps something playing while hooks are written', () => {
    render(<HookReel {...base} hooks={null} />);
    expect(screen.getByTestId('hooks-loading')).toBeTruthy();
    expect(screen.getByTestId('player')).toBeTruthy();
    expect(screen.getByText('Writing hooks…')).toBeTruthy();
  });

  it('shows the hook mechanism, picks on tap, and moves to the next hook', () => {
    const onChoose = vi.fn();
    const onFocus = vi.fn();
    render(<HookReel {...base} hooks={hooks} onChoose={onChoose} onFocus={onFocus} />);
    expect(screen.getByText('Curiosity gap')).toBeTruthy();
    expect(screen.getByText('Offline hooks')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Use this hook' }));
    expect(onChoose).toHaveBeenCalledWith(0);
    fireEvent.click(screen.getByRole('button', { name: /Swipe up for another hook/ }));
    expect(onFocus).toHaveBeenCalledWith(1);
  });

  it('offers a retry when hook generation fails', () => {
    const onRetry = vi.fn();
    render(<HookReel {...base} hooks={null} error="API is not reachable." onRetry={onRetry} />);
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(onRetry).toHaveBeenCalledOnce();
  });
});

describe('ShipScreen', () => {
  const job = (over: Partial<RenderJobView>): RenderJobView => ({
    renderId: 'abc', status: 'rendering', progress: 0.42, error: null, durationSeconds: 12, width: 1080,
    height: 1920, fps: 30, overlayTraceStatus: null, videoUrl: null, traceUrl: null, ...over,
  });
  const props = (over: Partial<ShipScreenProps> = {}): ShipScreenProps => ({
    timeline,
    caption: 'Hook line\n\n#crispypotatoes',
    pageName: 'Crispy Kitchen',
    render: job({}),
    renderError: null,
    review: { status: 'idle' },
    choiceLabels: { structure: 'Quick breakdown', energy: 'Dramatic', ending: 'Big reveal' },
    onDownload: vi.fn(),
    onRetryRender: vi.fn(),
    onCopyCaption: vi.fn(),
    onSendToReview: vi.fn(),
    onRemix: vi.fn(),
    onChangeOne: vi.fn(),
    onRestart: vi.fn(),
    ...over,
  });

  it('shows render progress, then a real download link', () => {
    const { rerender } = render(<ShipScreen {...props()} />);
    expect(screen.getByRole('button', { name: /Rendering MP4 · 42%/ })).toBeTruthy();
    rerender(<ShipScreen {...props({ render: job({ status: 'done', progress: 1, videoUrl: '/api/quick-reel/renders/abc/video' }) })} />);
    const link = screen.getByRole('link', { name: /Download MP4/ });
    expect(link.getAttribute('href')).toBe('/api/quick-reel/renders/abc/video?download=1');
  });

  it('offers a retry when the render fails', () => {
    const onRetryRender = vi.fn();
    render(<ShipScreen {...props({ render: job({ status: 'failed', error: 'Overlay render trace failed for #1' }), onRetryRender })} />);
    expect(screen.getByText('Overlay render trace failed for #1')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /Retry MP4 render/ }));
    expect(onRetryRender).toHaveBeenCalledOnce();
  });

  it('wires caption, review, remix and change-one-thing', () => {
    const p = props();
    const { rerender } = render(<ShipScreen {...p} />);
    fireEvent.click(screen.getByRole('button', { name: /Copy caption/ }));
    fireEvent.click(screen.getByRole('button', { name: /Send to Review/ }));
    fireEvent.click(screen.getByRole('button', { name: /Remix/ }));
    fireEvent.click(screen.getByRole('button', { name: /Change one thing/ }));
    fireEvent.click(screen.getByRole('button', { name: /Energy Dramatic/ }));
    expect(p.onCopyCaption).toHaveBeenCalledOnce();
    expect(p.onSendToReview).toHaveBeenCalledOnce();
    expect(p.onRemix).toHaveBeenCalledOnce();
    expect(p.onChangeOne).toHaveBeenCalledWith('energy');
    rerender(<ShipScreen {...p} review={{ status: 'sent', reelId: 'r1' }} />);
    const sent = screen.getByRole('button', { name: /In review/ }) as HTMLButtonElement;
    expect(sent.disabled).toBe(true);
    expect(screen.getByText(/Saved to Crispy Kitchen/)).toBeTruthy();
  });
});

describe('BuildStage holdFrame', () => {
  it('holds on the last frame before the caption starts to fade', () => {
    const t = quickReelFixtures.dramatic;
    const hook = t.overlays[0];
    // Dramatic exits over 12 frames: hold 13 frames before the end of the hook.
    expect(holdFrame(t, { startFrame: hook.startFrame, endFrame: hook.endFrame })).toBe(hook.endFrame - 13);
    expect(holdFrame(t, { startFrame: 10, endFrame: 11 })).toBe(10);
  });
});

describe('KeyboardHelp', () => {
  it('lists the keys for the current step', () => {
    render(<KeyboardHelp phase={{ name: 'choosing', moment: 'ending' }} />);
    expect(screen.getByText('Pick a card')).toBeTruthy();
    expect(screen.getAllByText(/^[123]$/)).toHaveLength(3);
  });
});
