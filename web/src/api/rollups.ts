import { asRecord, getJson, isIsoDate, nullableLink, requiredCount } from './http';
import {
  ApiFailure,
  type Flag,
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
export async function fetchCountySummary(
  release: ReleaseSummary,
  flag: Flag,
  signal?: AbortSignal,
): Promise<RollupPage> {
  const query = new URLSearchParams({
    level: 'county',
    state: '39',
    flag,
    as_of: release.as_of,
    processed_on: release.processed_on,
    page_size: '1',
  });
  return getJson(`${ENDPOINT}?${query.toString()}`, decodeRollupPage, signal);
}
export function matchesSummary(page: RollupPage, release: ReleaseSummary, flag: Flag): boolean {
  return (
    page.release.as_of === release.as_of &&
    page.release.processed_on === release.processed_on &&
    page.selection.level === 'county' &&
    page.selection.state === '39' &&
    page.selection.code === null &&
    page.selection.flag === flag &&
    page.threshold.download_mbps === 100 &&
    page.threshold.upload_mbps === 20 &&
    isIsoDate(page.release.as_of)
  );
}
