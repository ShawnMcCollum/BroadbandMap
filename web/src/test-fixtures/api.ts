import type { ReleaseSummary, RollupPage } from '../api/types';

export const d25: ReleaseSummary = {
  filing_period: 'D25',
  as_of: '2025-12-31',
  processed_on: '2026-09-29',
  states: [{ code: '39', name: 'Ohio', abbreviation: 'OH' }],
};
export const j25: ReleaseSummary = {
  filing_period: 'J25',
  as_of: '2025-06-30',
  processed_on: '2026-10-01',
  states: [{ code: '39', name: 'Ohio', abbreviation: 'OH' }],
};
export const releases = [d25, j25];
export function releasePage(rows = releases, next: string | null = null) {
  return { count: rows.length, next, previous: null, results: rows };
}
export function rollupPage(
  release = d25,
  rows = [
    {
      code: '39001',
      locations: 100,
      served: 70,
      not_served: 30,
      wired_100_20: 70,
      any_100_20: 90,
      terrestrial_100_20: 50,
    },
  ],
  coverage: RollupPage['summary_coverage'] = 'stored_rollups_only',
): RollupPage {
  return {
    boundary_vintage: 2020,
    count: rows.length ? 88 : 0,
    next: rows.length ? 'http://localhost/api/v1/served-unserved/rollups/?page=2' : null,
    previous: null,
    release,
    results: rows,
    selection: { level: 'county', state: '39', code: null, flag: 'wired' },
    summary_coverage: coverage,
    threshold: { download_mbps: 100, upload_mbps: 20 },
  };
}
export function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}
