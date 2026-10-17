import { describe, expect, it } from 'vitest';
import { decodeCountyPage } from '../../api/counties';
import { countyPage, rollupPage, first } from '../../test-fixtures/api';
import { countyRows, formatCount, formatShare, servedShare } from './join';
describe('county joins and presentation', () => {
  it('keeps missing observations absent and unmatched observations readable', () => {
    const geo = decodeCountyPage(countyPage(['39001', '39003']));
    const row = first(rollupPage().results);
    const rows = countyRows(geo, [row, { ...row, code: '39005', served: 0, not_served: 100 }]);
    expect(rows.find((r) => r.code === '39001')).toMatchObject({
      name: 'Adams County',
      kind: 'observed',
    });
    expect(rows.find((r) => r.code === '39003')).toMatchObject({ kind: 'missing' });
    expect(rows.find((r) => r.code === '39003')).not.toHaveProperty('summary');
    expect(rows.find((r) => r.code === '39005')).toMatchObject({
      name: 'County GEOID 39005',
      kind: 'observed',
    });
  });
  it('joins string IDs without numeric coercion and preserves inputs', () => {
    const geo = decodeCountyPage(countyPage());
    first(geo.features).id = '01001';
    first(geo.features).properties.code = '01001';
    const row = { ...first(rollupPage().results), code: '01001' };
    const before = JSON.stringify([geo, row]);
    expect(countyRows(geo, [row])[0]?.kind).toBe('observed');
    expect(JSON.stringify([geo, row])).toBe(before);
  });
  it('formats exact counts and safe percentages', () => {
    expect(formatCount(4542350)).toBe('4,542,350');
    expect(formatShare(0, 100)).toBe('0.0%');
    expect(formatShare(100, 100)).toBe('100.0%');
    expect(servedShare(1, 0)).toBeNull();
    expect(servedShare(NaN, 100)).toBeNull();
    expect(formatShare(1, 0)).toBe('Unavailable');
  });
});
