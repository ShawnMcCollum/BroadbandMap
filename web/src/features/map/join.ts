import type { CountyCollection, CountyFeature, RollupRow } from '../../api/types';

export type CountyView = { code: string; name: string; boundary?: CountyFeature } & (
  { kind: 'observed'; summary: RollupRow } | { kind: 'missing'; summary?: never }
);
export function countyRows(
  boundaries: CountyCollection | null,
  summaries: RollupRow[],
): CountyView[] {
  const features = new Map(boundaries?.features.map((f) => [f.id, f]) ?? []);
  const rows = new Map(summaries.map((r) => [r.code, r]));
  return [...new Set([...features.keys(), ...rows.keys()])]
    .map((code) => {
      const boundary = features.get(code),
        summary = rows.get(code);
      const base = { code, name: boundary?.properties.name ?? `County GEOID ${code}`, boundary };
      return summary
        ? { ...base, kind: 'observed' as const, summary }
        : { ...base, kind: 'missing' as const };
    })
    .sort((a, b) => a.name.localeCompare(b.name) || a.code.localeCompare(b.code));
}
export function servedShare(served: number, locations: number): number | null {
  return Number.isFinite(served) &&
    Number.isFinite(locations) &&
    locations > 0 &&
    served >= 0 &&
    served <= locations
    ? (served / locations) * 100
    : null;
}
export const formatCount = (value: number) => value.toLocaleString('en-US');
export const formatShare = (served: number, locations: number) => {
  const value = servedShare(served, locations);
  return value === null ? 'Unavailable' : `${value.toFixed(1)}%`;
};
