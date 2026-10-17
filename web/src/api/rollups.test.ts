import { afterEach, describe, expect, it, vi } from 'vitest';
import { decodeRollupPage, fetchCountySummary, matchesSummary } from './rollups';
import { d25, rollupPage } from '../test-fixtures/api';
const response = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
afterEach(() => {
  vi.unstubAllGlobals();
});
describe('county summary readiness read', () => {
  it('rejects a coverage array instead of coercing it into a valid enum string', () => {
    expect(() =>
      decodeRollupPage({ ...rollupPage(), summary_coverage: ['stored_rollups_only'] }),
    ).toThrow();
  });
  it('pins both dates, state, flag and a single bounded page without following next', async () => {
    const fetch = vi.fn().mockResolvedValue(response(rollupPage()));
    vi.stubGlobal('fetch', fetch);
    const page = await fetchCountySummary(d25, 'wired');
    const url = new URL(String(fetch.mock.calls[0]?.[0]));
    expect(url.searchParams.get('as_of')).toBe(d25.as_of);
    expect(url.searchParams.get('processed_on')).toBe(d25.processed_on);
    expect(url.searchParams.get('state')).toBe('39');
    expect(url.searchParams.get('flag')).toBe('wired');
    expect(url.searchParams.get('page_size')).toBe('1');
    expect(page.next).not.toBeNull();
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(matchesSummary(page, d25, 'wired')).toBe(true);
  });
  it('rejects selection mismatches and malformed contracts', () => {
    const page = rollupPage();
    expect(
      matchesSummary({ ...page, selection: { ...page.selection, flag: 'any' } }, d25, 'wired'),
    ).toBe(false);
    expect(
      matchesSummary({ ...page, release: { ...d25, processed_on: '2026-09-30' } }, d25, 'wired'),
    ).toBe(false);
    expect(() =>
      decodeRollupPage({ ...page, threshold: { download_mbps: 100, upload_mbps: '20' } }),
    ).toThrow();
    expect(() => decodeRollupPage({ ...page, count: -1 })).toThrow();
    expect(() => decodeRollupPage({ ...page, summary_coverage: 'unknown' })).toThrow();
  });
});
