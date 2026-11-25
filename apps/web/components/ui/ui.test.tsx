// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { Button } from './button';
import { Chip } from './chip';
import { Kbd } from './kbd';
import { PhoneFrame } from './phone-frame';
import { StoryBars } from './story-bars';

afterEach(cleanup);

describe('design system primitives', () => {
  it('Button renders a typed button with variants, or its child with asChild', () => {
    const onClick = vi.fn();
    render(
      <>
        <Button variant="accent" onClick={onClick}>
          Go
        </Button>
        <Button asChild variant="ghost">
          <a href="/make">Make</a>
        </Button>
      </>,
    );
    const button = screen.getByRole('button', { name: 'Go' });
    expect(button.getAttribute('type')).toBe('button');
    expect(button.className).toContain('bg-accent');
    fireEvent.click(button);
    expect(onClick).toHaveBeenCalledOnce();
    const link = screen.getByRole('link', { name: 'Make' });
    expect(link.getAttribute('href')).toBe('/make');
    expect(link.getAttribute('type')).toBeNull();
  });

  it('Chip exposes its selected state', () => {
    render(<Chip selected>Crispy Kitchen</Chip>);
    expect(screen.getByRole('button', { name: 'Crispy Kitchen' }).getAttribute('aria-pressed')).toBe('true');
  });

  it('StoryBars fills each segment and reports overall progress', () => {
    render(<StoryBars progress={[1, 0.5, 0, 2]} />);
    const fills = screen.getAllByTestId('story-bar-fill').map((el) => (el as HTMLElement).style.width);
    expect(fills).toEqual(['100%', '50%', '0%', '100%']);
    expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBe('88');
  });

  it('PhoneFrame renders its content and an optional aside', () => {
    render(
      <PhoneFrame aside={<Kbd>Enter</Kbd>}>
        <p>reel</p>
      </PhoneFrame>,
    );
    expect(screen.getByTestId('phone-frame').textContent).toBe('reel');
    expect(screen.getByText('Enter').tagName).toBe('KBD');
  });
});
