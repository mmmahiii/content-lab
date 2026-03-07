import { describe, it, expect } from 'vitest';
import type { HealthResponse } from './types';

describe('types', () => {
  it('compiles', () => {
    const x: HealthResponse = { status: 'ok' };
    expect(x.status).toBe('ok');
  });
});
