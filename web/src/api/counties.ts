import { asRecord, getJson, nullableLink, requiredCount, resolvePageUrl } from './http';
import { ApiFailure, type CountyCollection, type CountyFeature, type CountyPage } from './types';

const ENDPOINT = '/api/v1/geographies/county/';
const invalid = () => new ApiFailure('unexpected', 'The API returned invalid county boundaries.');
function position(value: unknown): [number, number] {
  if (!Array.isArray(value) || value.length !== 2) throw invalid();
  const x: unknown = value[0],
    y: unknown = value[1];
  if (
    typeof x !== 'number' ||
    typeof y !== 'number' ||
    !Number.isFinite(x) ||
    !Number.isFinite(y) ||
    Math.abs(x) > 180 ||
    Math.abs(y) > 90
  )
    throw invalid();
  return [x, y];
}
function feature(value: unknown): CountyFeature {
  const v = asRecord(value),
    p = asRecord(v.properties),
    g = asRecord(v.geometry);
  if (
    v.type !== 'Feature' ||
    typeof v.id !== 'string' ||
    !/^39\d{3}$/.test(v.id) ||
    p.code !== v.id ||
    typeof p.name !== 'string' ||
    !p.name.trim() ||
    g.type !== 'MultiPolygon' ||
    !Array.isArray(g.coordinates) ||
    !g.coordinates.length
  )
    throw invalid();
  const coordinates = g.coordinates.map((polygon: unknown) => {
    if (!Array.isArray(polygon) || !polygon.length) throw invalid();
    return polygon.map((ring: unknown) => {
      if (!Array.isArray(ring) || ring.length < 4) throw invalid();
      const points = ring.map(position),
        first = points[0],
        last = points.at(-1);
      if (!first || !last || first[0] !== last[0] || first[1] !== last[1]) throw invalid();
      return points;
    });
  });
  return {
    type: 'Feature',
    id: v.id,
    properties: { code: v.id, name: p.name },
    geometry: { type: 'MultiPolygon', coordinates },
  };
}
export function decodeCountyPage(value: unknown): CountyPage {
  const v = asRecord(value);
  if (
    v.type !== 'FeatureCollection' ||
    v.state !== '39' ||
    v.boundary_vintage !== 2020 ||
    !requiredCount(v.count) ||
    !nullableLink(v.next) ||
    !nullableLink(v.previous) ||
    !Array.isArray(v.features)
  )
    throw invalid();
  return {
    type: 'FeatureCollection',
    state: '39',
    boundary_vintage: 2020,
    count: v.count,
    next: v.next,
    previous: v.previous,
    features: v.features.map(feature),
  };
}
export async function fetchCounties(state: '39', signal?: AbortSignal): Promise<CountyCollection> {
  for (const size of [100, 50, 25, 12, 6, 3, 1]) {
    try {
      const features: CountyFeature[] = [],
        visited = new Set<string>();
      let url = `${ENDPOINT}?state=${state}&page_size=${String(size)}`;
      let count: number | undefined;
      let lastId = '';
      for (;;) {
        if (signal?.aborted) throw new ApiFailure('cancelled', 'The request was cancelled.');
        const canonical = new URL(url, window.location.origin).href;
        if (visited.has(canonical)) throw invalid();
        visited.add(canonical);
        const page = await getJson(url, decodeCountyPage, signal);
        count ??= page.count;
        if (page.count !== count || (page.next !== null && !page.features.length)) throw invalid();
        for (const f of page.features) {
          if (f.id <= lastId) throw invalid();
          lastId = f.id;
          features.push(f);
        }
        if (features.length > count) throw invalid();
        if (page.next === null) {
          if (features.length !== count) throw invalid();
          return { type: 'FeatureCollection', state, boundary_vintage: 2020, count, features };
        }
        url = resolvePageUrl(page.next, ENDPOINT);
      }
    } catch (error) {
      const oversized =
        error instanceof ApiFailure &&
        error.status === 400 &&
        error.problem?.errors?.some(
          (e) => e.pointer === '/page_size' && e.code === 'geometry_payload_too_large',
        );
      if (!oversized) throw error;
      if (size === 1)
        throw new ApiFailure(
          'problem',
          'A county boundary exceeds the response size limit. Smaller pages cannot load it; contact an application operator.',
          error.status,
          error.problem,
          error.requestId,
        );
    }
  }
  throw invalid();
}
