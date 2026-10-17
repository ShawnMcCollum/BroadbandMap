import { asRecord, getJson, isIsoDate, nullableLink, requiredCount, resolvePageUrl } from './http';
import { ApiFailure, type ReleasePage, type ReleaseSummary, type StateSummary } from './types';

const ENDPOINT = '/api/v1/releases/';
function decodeState(value: unknown): StateSummary {
  const v = asRecord(value);
  if (
    typeof v.code !== 'string' ||
    typeof v.name !== 'string' ||
    typeof v.abbreviation !== 'string'
  )
    throw new ApiFailure('unexpected', 'The release response contains invalid state metadata.');
  return { code: v.code, name: v.name, abbreviation: v.abbreviation };
}
export function decodeRelease(value: unknown): ReleaseSummary {
  const v = asRecord(value);
  if (
    typeof v.filing_period !== 'string' ||
    !isIsoDate(v.as_of) ||
    !isIsoDate(v.processed_on) ||
    !Array.isArray(v.states)
  )
    throw new ApiFailure('unexpected', 'The API returned an invalid release.');
  return {
    filing_period: v.filing_period,
    as_of: v.as_of,
    processed_on: v.processed_on,
    states: v.states.map(decodeState),
  };
}
export function decodeReleasePage(value: unknown): ReleasePage {
  const v = asRecord(value);
  if (
    !requiredCount(v.count) ||
    !nullableLink(v.next) ||
    !nullableLink(v.previous) ||
    !Array.isArray(v.results)
  )
    throw new ApiFailure('unexpected', 'The API returned an invalid release page.');
  return {
    count: v.count,
    next: v.next,
    previous: v.previous,
    results: v.results.map(decodeRelease),
  };
}
export async function fetchReleases(signal?: AbortSignal): Promise<ReleaseSummary[]> {
  const rows: ReleaseSummary[] = [];
  const visited = new Set<string>();
  let url = `${ENDPOINT}?page_size=100`;
  for (;;) {
    const canonical = new URL(url, window.location.origin).href;
    if (visited.has(canonical))
      throw new ApiFailure('unexpected', 'The release list contains a pagination cycle.');
    visited.add(canonical);
    const page = await getJson(url, decodeReleasePage, signal);
    rows.push(...page.results);
    if (page.next === null) break;
    url = resolvePageUrl(page.next, ENDPOINT);
  }
  const unique = new Map<string, ReleaseSummary>();
  for (const row of rows) {
    const key = `${row.as_of}|${row.processed_on}`;
    const prior = unique.get(key);
    if (prior && JSON.stringify(prior) !== JSON.stringify(row))
      throw new ApiFailure(
        'unexpected',
        'The release list contains conflicting duplicate processing dates.',
      );
    unique.set(key, row);
  }
  return [...unique.values()].sort(
    (a, b) => b.as_of.localeCompare(a.as_of) || b.processed_on.localeCompare(a.processed_on),
  );
}
