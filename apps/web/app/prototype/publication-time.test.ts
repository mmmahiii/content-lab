import { describe, expect, it } from 'vitest';
import { zonedLocalToIso } from './publication-time';
describe('publication wall-clock conversion', () => {
  it('uses the selected timezone in summer and winter independently of the host', () => {
    expect(zonedLocalToIso('2026-09-09T12:00', 'Europe/London')).toBe('2026-09-09T11:00:00.000Z');
    expect(zonedLocalToIso('2026-09-09T12:00', 'America/New_York')).toBe(
      '2026-09-09T16:00:00.000Z',
    );
    expect(zonedLocalToIso('2026-01-09T12:00', 'Europe/London')).toBe('2026-01-09T12:00:00.000Z');
  });
  it('rejects impossible and ambiguous dates instead of silently changing them', () => {
    expect(() => zonedLocalToIso('2026-03-29T01:30', 'Europe/London')).toThrow('does not exist');
    expect(() => zonedLocalToIso('2026-10-25T01:30', 'Europe/London')).toThrow('occurs twice');
    expect(() => zonedLocalToIso('2026-02-30T12:00', 'UTC')).toThrow();
    expect(() => zonedLocalToIso('', 'UTC')).toThrow('complete');
  });
});
