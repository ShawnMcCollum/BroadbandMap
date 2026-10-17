import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  decodeRollupPage,
  fetchCountySummaries,
  fetchCountySummaryByCode,
  matchesSummary,
} from './rollups';
import { d25, j25, rollupPage, first } from '../test-fixtures/api';
const response = (body: unknown) =>
  new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } });
afterEach(() => vi.unstubAllGlobals());
const row = first(rollupPage().results);
describe('complete county summaries', () => {
  it('pins context, follows pages, and returns all rows without page links', async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(response({ ...rollupPage(), count: 2, next: '?page=2' }))
      .mockResolvedValueOnce(
        response({ ...rollupPage(d25, [{ ...row, code: '39003' }]), count: 2 }),
      );
    vi.stubGlobal('fetch', fetch);
    const data = await fetchCountySummaries(d25, 'wired');
    expect(data.results.map((r) => r.code)).toEqual(['39001', '39003']);
    const url = new URL(String(fetch.mock.calls[0]?.[0]));
    expect(url.searchParams.get('as_of')).toBe(d25.as_of);
    expect(url.searchParams.get('processed_on')).toBe(d25.processed_on);
    expect(url.searchParams.get('page_size')).toBe('100');
    expect(url.searchParams.get('state')).toBe('39');
    expect(data).not.toHaveProperty('next');
  });
  it.each([
    { count: 2 },
    { next: 'https://evil.test/api/v1/served-unserved/rollups/' },
    { release: j25 },
    { threshold: { download_mbps: 25, upload_mbps: 3 } },
    { boundary_vintage: 2010 },
    { summary_coverage: ['stored_rollups_only'] },
    { results: [{ ...row, locations: 0 }] },
    { results: [{ ...row, any_100_20: 101 }] },
    { results: [{ ...row, served: 69 }] },
    { results: [{ ...row, not_served: 29 }] },
    { results: [{ ...row, code: 39001 }] },
    { results: [{ ...row, locations: Number.MAX_SAFE_INTEGER + 1 }] },
  ])('rejects invalid context/counts/collection %j', async (patch) => {
    const fetch = vi.fn().mockResolvedValue(response({ ...rollupPage(), ...patch }));
    vi.stubGlobal('fetch', fetch);
    await expect(fetchCountySummaries(d25, 'wired')).rejects.toThrow();
    expect(fetch).toHaveBeenCalledTimes(1);
  });
  it.each(['duplicate', 'changed', 'failure', 'cycle'])(
    'discards a successful first page after %s',
    async (kind) => {
      const first = { ...rollupPage(), count: 2, next: '?page=2' };
      const second = {
        ...rollupPage(d25, [{ ...row, code: kind === 'duplicate' ? '39001' : '39003' }]),
        count: kind === 'changed' ? 3 : 2,
        next: kind === 'cycle' ? '?page=2' : null,
      };
      vi.stubGlobal(
        'fetch',
        vi
          .fn()
          .mockResolvedValueOnce(response(first))
          .mockResolvedValueOnce(
            kind === 'failure' ? new Response('bad', { status: 503 }) : response(second),
          ),
      );
      await expect(fetchCountySummaries(d25, 'wired')).rejects.toThrow();
    },
  );
  it('accepts empty stored collections without diagnosing coverage', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(rollupPage(d25, []))));
    expect((await fetchCountySummaries(d25, 'wired')).results).toEqual([]);
  });
  it('rejects malformed generic pages and mismatched selections', () => {
    expect(() => decodeRollupPage({ ...rollupPage(), summary_coverage: ['observed'] })).toThrow();
    expect(matchesSummary(rollupPage(), d25, 'any')).toBe(false);
  });
});
describe('selected missing county diagnosis', () => {
  it.each(['no_observations', 'outside_release_coverage'] as const)(
    'resolves %s through exact code',
    async (coverage) => {
      const body = rollupPage(d25, [], coverage);
      body.selection.code = '39001';
      const fetch = vi.fn().mockResolvedValue(response(body));
      vi.stubGlobal('fetch', fetch);
      expect((await fetchCountySummaryByCode(d25, 'wired', '39001')).summary_coverage).toBe(
        coverage,
      );
      expect(new URL(String(fetch.mock.calls[0]?.[0])).searchParams.get('code')).toBe('39001');
    },
  );
  it('accepts a newly observed row but rejects inconsistent exact coverage', async () => {
    const body = rollupPage(d25, undefined, 'observed');
    body.selection.code = '39001';
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(response(body))
      .mockResolvedValueOnce(response({ ...body, summary_coverage: 'no_observations' }));
    vi.stubGlobal('fetch', fetch);
    expect((await fetchCountySummaryByCode(d25, 'wired', '39001')).count).toBe(1);
    await expect(fetchCountySummaryByCode(d25, 'wired', '39001')).rejects.toThrow();
  });
});
