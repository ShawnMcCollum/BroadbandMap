import { afterEach, describe, expect, it, vi } from 'vitest';
import { decodeCountyPage, fetchCounties } from './counties';
import { countyPage, first } from '../test-fixtures/api';
const response = (body: unknown) =>
  new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/geo+json' } });
const oversized = () =>
  new Response(
    JSON.stringify({
      type: 'about:blank',
      title: 'Invalid',
      detail: 'Too large',
      status: 400,
      code: 'invalid',
      request_id: 'a'.repeat(32),
      errors: [
        {
          pointer: '/page_size',
          code: 'geometry_payload_too_large',
          message: 'Request fewer features.',
        },
      ],
    }),
    { status: 400, headers: { 'Content-Type': 'application/problem+json' } },
  );
afterEach(() => vi.unstubAllGlobals());
describe('county boundaries', () => {
  it('preserves coordinates and follows all pages before returning complete geometry', async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(response({ ...countyPage(['39001'], '?page=2'), count: 2 }))
      .mockResolvedValueOnce(response({ ...countyPage(['39003']), count: 2 }));
    vi.stubGlobal('fetch', fetch);
    const data = await fetchCounties('39');
    expect(data.features.map((f) => f.id)).toEqual(['39001', '39003']);
    expect(data.features[0]?.geometry).toEqual(countyPage().features[0]?.geometry);
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(data).not.toHaveProperty('next');
  });
  it.each(['id', 'code', 'state', 'vintage', 'name', 'type', 'ring', 'open', 'position', 'empty'])(
    'rejects malformed %s',
    (kind) => {
      const data = countyPage(),
        f = first(data.features);
      const altered: unknown =
        kind === 'id'
          ? { ...data, features: [{ ...f, id: 39001 }] }
          : kind === 'code'
            ? { ...data, features: [{ ...f, properties: { ...f.properties, code: '39003' } }] }
            : kind === 'state'
              ? { ...data, state: '54' }
              : kind === 'vintage'
                ? { ...data, boundary_vintage: 2010 }
                : kind === 'name'
                  ? { ...data, features: [{ ...f, properties: { ...f.properties, name: '' } }] }
                  : kind === 'type'
                    ? { ...data, type: 'Polygon' }
                    : {
                        ...data,
                        features: [
                          {
                            ...f,
                            geometry: {
                              type: 'MultiPolygon',
                              coordinates:
                                kind === 'empty'
                                  ? []
                                  : kind === 'ring'
                                    ? [[[[1, 2]]]]
                                    : kind === 'open'
                                      ? [
                                          [
                                            [
                                              [1, 2],
                                              [2, 3],
                                              [3, 4],
                                              [4, 5],
                                            ],
                                          ],
                                        ]
                                      : [
                                          [
                                            [
                                              [181, 2],
                                              [2, 3],
                                              [3, 4],
                                              [181, 2],
                                            ],
                                          ],
                                        ],
                            },
                          },
                        ],
                      };
      expect(() => decodeCountyPage(altered)).toThrow();
    },
  );
  it.each(['duplicates', 'count', 'cycle', 'unsafe', 'nonjson'])(
    'rejects %s collections without partial success',
    async (kind) => {
      const fetch = vi
        .fn()
        .mockResolvedValueOnce(
          response({
            ...countyPage(
              ['39001'],
              kind === 'unsafe' ? 'http://backend:8000/api/v1/geographies/county/' : '?page=2',
            ),
            count: 2,
          }),
        )
        .mockResolvedValueOnce(
          kind === 'nonjson'
            ? new Response('private', { headers: { 'Content-Type': 'text/html' } })
            : response({
                ...countyPage([kind === 'duplicates' ? '39001' : '39003']),
                count: kind === 'count' ? 3 : 2,
                next: kind === 'cycle' ? '?page=2' : null,
              }),
        );
      vi.stubGlobal('fetch', fetch);
      await expect(fetchCounties('39')).rejects.toThrow();
      if (kind === 'unsafe') expect(fetch).toHaveBeenCalledTimes(1);
    },
  );
  it('discards partial attempt and restarts page one at a smaller size', async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(
        response({ ...countyPage(['39001'], '?page=2&page_size=100'), count: 2 }),
      )
      .mockResolvedValueOnce(oversized())
      .mockResolvedValueOnce(response(countyPage(['39001', '39003'])));
    vi.stubGlobal('fetch', fetch);
    expect((await fetchCounties('39')).count).toBe(2);
    expect(new URL(String(fetch.mock.calls[2]?.[0])).searchParams.get('page_size')).toBe('50');
    expect(new URL(String(fetch.mock.calls[2]?.[0])).searchParams.has('page')).toBe(false);
  });
  it('stops at one oversized feature after seven attempts, preserving the request ID', async () => {
    const fetch = vi.fn().mockImplementation(() => Promise.resolve(oversized()));
    vi.stubGlobal('fetch', fetch);
    await expect(fetchCounties('39')).rejects.toMatchObject({
      requestId: 'a'.repeat(32),
    });
    expect(
      fetch.mock.calls.map((c) => new URL(String(c[0])).searchParams.get('page_size')),
    ).toEqual(['100', '50', '25', '12', '6', '3', '1']);
  });
  it('does not retry unrelated failures', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response('bad', { status: 400 }));
    vi.stubGlobal('fetch', fetch);
    await expect(fetchCounties('39')).rejects.toThrow();
    expect(fetch).toHaveBeenCalledTimes(1);
  });
  it('aborts pagination before requesting a subsequent page', async () => {
    const controller = new AbortController();
    const fetch = vi.fn().mockImplementation(() => {
      controller.abort();
      return Promise.resolve(response({ ...countyPage(['39001'], '?page=2'), count: 2 }));
    });
    vi.stubGlobal('fetch', fetch);
    await expect(fetchCounties('39', controller.signal)).rejects.toMatchObject({
      kind: 'cancelled',
    });
    expect(fetch).toHaveBeenCalledTimes(1);
  });
  it('accepts an empty known state and multipart closed rings', async () => {
    const data = countyPage(),
      f = first(data.features);
    const multipart = {
      ...data,
      features: [
        {
          ...f,
          geometry: {
            ...f.geometry,
            coordinates: [...f.geometry.coordinates, ...f.geometry.coordinates],
          },
        },
      ],
    };
    expect(decodeCountyPage(multipart).features[0]?.geometry.coordinates).toHaveLength(2);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(countyPage([]))));
    expect((await fetchCounties('39')).features).toEqual([]);
  });
});
