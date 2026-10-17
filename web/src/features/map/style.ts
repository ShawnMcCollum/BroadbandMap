import type { StyleSpecification } from 'maplibre-gl';
import type { CountyCollection } from '../../api/types';
export const bins = [
  { label: '0–<20%', color: '#eff3ff' },
  { label: '20–<40%', color: '#bdd7e7' },
  { label: '40–<60%', color: '#6baed6' },
  { label: '60–<80%', color: '#3182bd' },
  { label: '80–100%', color: '#08519c' },
];
export const neutral = '#e5e7eb';
export function shareColor(percent: number | null): string {
  return percent === null || !Number.isFinite(percent) || percent < 0 || percent > 100
    ? neutral
    : (bins[Math.min(4, Math.floor(percent / 20))]?.color ?? neutral);
}
export function countyBounds(data: CountyCollection): [[number, number], [number, number]] {
  let west = Infinity,
    south = Infinity,
    east = -Infinity,
    north = -Infinity;
  for (const f of data.features)
    for (const polygon of f.geometry.coordinates)
      for (const ring of polygon)
        for (const [x, y] of ring) {
          west = Math.min(west, x);
          east = Math.max(east, x);
          south = Math.min(south, y);
          north = Math.max(north, y);
        }
  return [
    [west, south],
    [east, north],
  ];
}
export function hatchImage() {
  const data = new Uint8Array(8 * 8 * 4);
  for (let y = 0; y < 8; y++)
    for (let x = 0; x < 8; x++) {
      const i = (y * 8 + x) * 4;
      if ((x + y) % 8 < 2) data.set([64, 86, 107, 180], i);
    }
  return { width: 8, height: 8, data };
}
export function countyStyle(): StyleSpecification {
  return {
    version: 8,
    sources: {},
    layers: [{ id: 'background', type: 'background', paint: { 'background-color': '#f6f8fa' } }],
  };
}
