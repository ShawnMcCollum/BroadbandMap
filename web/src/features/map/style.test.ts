import { describe, expect, it } from 'vitest';
import { bins, countyBounds, neutral, shareColor } from './style';
import { decodeCountyPage } from '../../api/counties';
import { countyPage } from '../../test-fixtures/api';
describe('served share scale and bounds', () => {
  it.each([0, 20, 40, 60, 80, 100])('classifies the unrounded %s percent endpoint', (percent) => {
    expect(shareColor(percent)).toBe(bins[Math.min(4, percent / 20)]?.color);
  });
  it('does not classify rounded labels or missing observations as zero', () => {
    expect(shareColor(19.999)).toBe(bins[0]?.color);
    expect(shareColor(null)).toBe(neutral);
    expect(shareColor(NaN)).toBe(neutral);
  });
  it('derives bounds from unchanged coordinates', () => {
    expect(countyBounds(decodeCountyPage(countyPage()))).toEqual([
      [-84, 39],
      [-83.9, 39.1],
    ]);
  });
});
