import { asRecord, getJson, isIsoDate, nullableLink, requiredCount, resolvePageUrl } from './http';
import {
  ApiFailure,
  type Flag,
  type CountySummaries,
  type ReleaseSummary,
  type RollupPage,
  type RollupRow,
  type SummaryLevel,
} from './types';
import { decodeRelease } from './releases';

const ENDPOINT = '/api/v1/served-unserved/rollups/';
const FLAGS: Flag[] = ['wired', 'any', 'terrestrial'];
const LEVELS: SummaryLevel[] = [
  'county',
  'tract',
  'block_group',
  'block',
  'h3_res8',
  'place',
  'county_subdivision',
];
function decodeRow(value: unknown): RollupRow {
  const v = asRecord(value);
  if (
    typeof v.code !== 'string' ||
    !requiredCount(v.locations) ||
    v.locations < 1 ||
    !requiredCount(v.served) ||
    !requiredCount(v.not_served) ||
    !requiredCount(v.wired_100_20) ||
    !requiredCount(v.any_100_20) ||
    !requiredCount(v.terrestrial_100_20)
  )
    throw new ApiFailure('unexpected', 'The county summary response contains an invalid row.');
  return {
    code: v.code,
    locations: v.locations,
    served: v.served,
    not_served: v.not_served,
    wired_100_20: v.wired_100_20,
    any_100_20: v.any_100_20,
    terrestrial_100_20: v.terrestrial_100_20,
  };
}
export function decodeRollupPage(value: unknown): RollupPage {
  const v = asRecord(value);
  const s = asRecord(v.selection);
  const t = asRecord(v.threshold);
  const coverage = [
    'stored_rollups_only',
    'observed',
    'no_observations',
    'outside_release_coverage',
  ];
  if (
    !requiredCount(v.count) ||
    !nullableLink(v.next) ||
    !nullableLink(v.previous) ||
    !Array.isArray(v.results) ||
    (v.boundary_vintage !== null && !Number.isSafeInteger(v.boundary_vintage)) ||
    !FLAGS.includes(s.flag as Flag) ||
    !LEVELS.includes(s.level as SummaryLevel) ||
    (s.state !== null && typeof s.state !== 'string') ||
    (s.code !== null && typeof s.code !== 'string') ||
    !Number.isSafeInteger(t.download_mbps) ||
    !Number.isSafeInteger(t.upload_mbps) ||
    typeof v.summary_coverage !== 'string' ||
    !coverage.includes(v.summary_coverage)
  )
    throw new ApiFailure('unexpected', 'The API returned an invalid county summary page.');
  const release = decodeRelease(v.release);
  return {
    boundary_vintage: v.boundary_vintage as number | null,
    count: v.count,
    next: v.next,
    previous: v.previous,
    release,
    results: v.results.map(decodeRow),
    selection: {
      level: s.level as SummaryLevel,
      state: s.state,
      code: s.code,
      flag: s.flag as Flag,
    },
    summary_coverage: v.summary_coverage as RollupPage['summary_coverage'],
    threshold: { download_mbps: t.download_mbps as number, upload_mbps: t.upload_mbps as number },
  };
}
function queryFor(release: ReleaseSummary, flag: Flag, code?: string) {
  return new URLSearchParams({
    level: 'county',
    state: '39',
    flag,
    as_of: release.as_of,
    processed_on: release.processed_on,
    page_size: '100',
    ...(code ? { code } : {}),
  });
}
export function matchesSummary(
  page: RollupPage,
  release: ReleaseSummary,
  flag: Flag,
  code: string | null = null,
): boolean {
  return (
    page.release.as_of === release.as_of &&
    page.release.processed_on === release.processed_on &&
    page.selection.level === 'county' &&
    page.selection.state === '39' &&
    page.release.filing_period === release.filing_period &&
    page.boundary_vintage === 2020 &&
    page.selection.code === code &&
    page.selection.flag === flag &&
    page.threshold.download_mbps === 100 &&
    page.threshold.upload_mbps === 20 &&
    isIsoDate(page.release.as_of)
  );
}
function validateCountyPage(
  page: RollupPage,
  release: ReleaseSummary,
  flag: Flag,
  code: string | null,
) {
  if (
    !matchesSummary(page, release, flag, code) ||
    page.results.some(
      (row) =>
        !/^39\d{3}$/.test(row.code) ||
        (code !== null && row.code !== code) ||
        row.served !== row[`${flag}_100_20`] ||
        row.served + row.not_served !== row.locations ||
        [row.any_100_20, row.wired_100_20, row.terrestrial_100_20].some((n) => n > row.locations),
    )
  )
    throw new ApiFailure(
      'unexpected',
      'The county summaries did not match the selected release, flag or counts.',
    );
}
export async function fetchCountySummaries(
  release: ReleaseSummary,
  flag: Flag,
  signal?: AbortSignal,
): Promise<CountySummaries> {
  const rows: RollupRow[] = [],
    visited = new Set<string>();
  let url = `${ENDPOINT}?${queryFor(release, flag).toString()}`;
  let first: RollupPage | undefined;
  let lastCode = '';
  for (;;) {
    if (signal?.aborted) throw new ApiFailure('cancelled', 'The request was cancelled.');
    const canonical = new URL(url, window.location.origin).href;
    if (visited.has(canonical))
      throw new ApiFailure('unexpected', 'County summaries contain a pagination cycle.');
    visited.add(canonical);
    const page = await getJson(url, decodeRollupPage, signal);
    validateCountyPage(page, release, flag, null);
    first ??= page;
    if (
      page.summary_coverage !== 'stored_rollups_only' ||
      page.count !== first.count ||
      JSON.stringify(page.release) !== JSON.stringify(first.release) ||
      (page.next !== null && !page.results.length)
    )
      throw new ApiFailure(
        'unexpected',
        'County summaries changed while loading. Refresh to try again.',
      );
    for (const row of page.results) {
      if (row.code <= lastCode)
        throw new ApiFailure(
          'unexpected',
          'County summaries contain duplicate or unordered counties.',
        );
      lastCode = row.code;
      rows.push(row);
    }
    if (rows.length > first.count)
      throw new ApiFailure('unexpected', 'County summary counts are inconsistent.');
    if (page.next === null) {
      if (rows.length !== first.count)
        throw new ApiFailure('unexpected', 'The county summary collection is incomplete.');
      return {
        count: first.count,
        results: rows,
        release: first.release,
        selection: first.selection,
        threshold: first.threshold,
        boundary_vintage: first.boundary_vintage,
        summary_coverage: first.summary_coverage,
      };
    }
    url = resolvePageUrl(page.next, ENDPOINT);
  }
}
export async function fetchCountySummaryByCode(
  release: ReleaseSummary,
  flag: Flag,
  code: string,
  signal?: AbortSignal,
): Promise<RollupPage> {
  const page = await getJson(
    `${ENDPOINT}?${queryFor(release, flag, code).toString()}`,
    decodeRollupPage,
    signal,
  );
  validateCountyPage(page, release, flag, code);
  if (
    page.next !== null ||
    page.previous !== null ||
    page.count !== page.results.length ||
    !(
      (page.count === 1 && page.summary_coverage === 'observed') ||
      (page.count === 0 &&
        ['no_observations', 'outside_release_coverage'].includes(page.summary_coverage))
    )
  )
    throw new ApiFailure('unexpected', 'The county detail response has inconsistent coverage.');
  return page;
}
