import { afterEach, describe, expect, it, vi } from 'vitest';
import { fetchReleases } from './releases';
import { d25, j25, releasePage } from '../test-fixtures/api';
const response = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
afterEach(() => {
  vi.unstubAllGlobals();
});
describe('release discovery', () => {
  it('reads all pages and sorts data period then processing date', async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(response(releasePage([j25], '?page=2&page_size=100')))
      .mockResolvedValueOnce(response(releasePage([d25])));
    vi.stubGlobal('fetch', fetch);
    expect(await fetchReleases()).toEqual([d25, j25]);
    expect(fetch).toHaveBeenCalledTimes(2);
  });
  it('does not return a partial catalog after page failure or malformed page', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(response(releasePage([d25], '?page=2')))
        .mockResolvedValueOnce(response({}, 502)),
    );
    await expect(fetchReleases()).rejects.toMatchObject({ kind: 'http' });
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(response(releasePage([d25], '?page=2')))
        .mockResolvedValueOnce(response({ count: 1 })),
    );
    await expect(fetchReleases()).rejects.toMatchObject({ kind: 'unexpected' });
  });
  it('rejects cycles and conflicting duplicate date pairs', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(response(releasePage([d25], '?page_size=100'))),
    );
    await expect(fetchReleases()).rejects.toMatchObject({
      kind: 'unexpected',
      message: 'The release list contains a pagination cycle.',
    });
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(response(releasePage([d25, { ...d25, filing_period: 'Different' }]))),
    );
    await expect(fetchReleases()).rejects.toMatchObject({ kind: 'unexpected' });
  });
  it('retains distinct processing versions and deduplicates identical copies', async () => {
    const other = { ...d25, processed_on: '2026-09-30' };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(releasePage([d25, other, d25]))));
    expect(await fetchReleases()).toEqual([other, d25]);
  });
});
