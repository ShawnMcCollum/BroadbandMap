import { describe, expect, it } from 'vitest';
import { dashboardDestination, routeFromHash } from './navigation';
describe('navigation', () => {
  it.each([
    ['', 'map'],
    ['#/map', 'map'],
    ['#/ask', 'ask'],
    ['#/settings/ai', 'settings/ai'],
    ['#/diagnostics', 'diagnostics'],
    ['#/other', 'unknown'],
  ] as const)('maps %s to %s', (hash, expected) => {
    expect(routeFromHash(hash)).toBe(expected);
  });
  it('validates configured dashboard URLs and keeps deployment paths', () => {
    expect(dashboardDestination('https://example.test/analyst/')).toEqual({
      valid: true,
      url: 'https://example.test/analyst/',
    });
    for (const value of [
      'javascript:alert(1)',
      'https://user:pass@example.test/',
      'https://example.test/?x=1',
      'https://example.test/#/map',
      'not a url',
    ])
      expect(dashboardDestination(value)).toEqual({ valid: false });
    expect(dashboardDestination('')).toEqual({ valid: true, url: 'http://localhost:8501/' });
  });
});
