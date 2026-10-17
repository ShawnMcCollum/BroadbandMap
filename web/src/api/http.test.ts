import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiFailure } from './types';
import { getJson, resolvePageUrl } from './http';
import { decodeReleasePage } from './releases';

const decode = (v: unknown) => v;
const json = (
  body: unknown,
  status = 200,
  type = 'application/json; charset=utf-8',
  headers?: HeadersInit,
) => {
  const responseHeaders = new Headers(headers);
  responseHeaders.set('Content-Type', type);
  return new Response(JSON.stringify(body), { status, headers: responseHeaders });
};
afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
  vi.restoreAllMocks();
});
describe('HTTP boundary', () => {
  it('uses same-origin no-store GET settings and accepts JSON / GeoJSON media types', async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(json({ ok: true }))
      .mockResolvedValueOnce(
        json(
          { type: 'FeatureCollection', features: [] },
          200,
          'application/geo+json; charset=utf-8',
        ),
      );
    vi.stubGlobal('fetch', fetch);
    expect(await getJson('/api/v1/releases/', decode)).toEqual({ ok: true });
    expect(await getJson('/api/v1/geographies/county/', decode)).toEqual({
      type: 'FeatureCollection',
      features: [],
    });
    expect(fetch.mock.calls[0]?.[1]).toMatchObject({
      method: 'GET',
      cache: 'no-store',
      credentials: 'same-origin',
      redirect: 'error',
    });
  });
  it.each([
    ['text/html', '<html>bad</html>'],
    ['application/json', '{not-json'],
    ['application/problem+json', '{bad problem'],
  ])('fails safely for invalid %s responses', async (type, body) => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(new Response(body, { status: 502, headers: { 'Content-Type': type } })),
    );
    await expect(getJson('/api/v1/releases/', decode)).rejects.toMatchObject({ kind: 'http' });
  });
  it('uses safe problem detail and prefers a valid header request id', async () => {
    const problem = {
      type: 'about:blank',
      title: 'Invalid',
      status: 400,
      detail: '<safe text>',
      code: 'invalid',
      request_id: 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
      errors: [
        { pointer: '/flag', code: 'invalid', message: 'Choose a valid flag.' },
        { pointer: '', code: 'invalid', message: 'General issue.' },
      ],
    };
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        json(problem, 400, 'application/problem+json; charset=utf-8', {
          'X-Request-ID': 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
        }),
      ),
    );
    await expect(getJson('/api/v1/releases/', decode)).rejects.toMatchObject({
      kind: 'problem',
      status: 400,
      message: '<safe text>',
      requestId: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      problem: { errors: problem.errors },
    });
  });
  it('falls back for problem status mismatch and hides response content', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        json(
          {
            type: 'about:blank',
            title: 'Secret',
            status: 500,
            detail: 'traceback',
            code: 'oops',
            request_id: 'not-valid',
          },
          400,
          'application/problem+json',
        ),
      ),
    );
    await expect(getJson('/api/v1/releases/', decode)).rejects.toMatchObject({
      kind: 'http',
      message: 'The API request failed (HTTP 400).',
      requestId: undefined,
    });
  });
  it('uses a valid body request ID when the header is invalid and omits invalid IDs', async () => {
    const problem = {
      type: 'about:blank',
      title: 'Invalid',
      status: 400,
      detail: 'Correct the request.',
      code: 'invalid',
      request_id: 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
    };
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          json(problem, 400, 'application/problem+json', { 'X-Request-ID': 'not-a-request-id' }),
        ),
    );
    await expect(getJson('/api/v1/releases/', decode)).rejects.toMatchObject({
      requestId: problem.request_id,
    });
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        json({ ...problem, request_id: 'bad' }, 400, 'application/problem+json', {
          'X-Request-ID': 'also-bad',
        }),
      ),
    );
    await expect(getJson('/api/v1/releases/', decode)).rejects.toMatchObject({
      requestId: undefined,
    });
  });
  it('rejects malformed successful JSON', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          new Response('{bad', { status: 200, headers: { 'Content-Type': 'application/json' } }),
        ),
    );
    await expect(getJson('/api/v1/releases/', decode)).rejects.toMatchObject({
      kind: 'unexpected',
      message: 'The API returned invalid JSON.',
    });
  });
  it('settles a pre-aborted request and an abort during body parsing', async () => {
    const preAborted = new AbortController();
    preAborted.abort();
    const fetch = vi.fn();
    vi.stubGlobal('fetch', fetch);
    await expect(getJson('/api/v1/releases/', decode, preAborted.signal)).rejects.toMatchObject({
      kind: 'cancelled',
    });
    expect(fetch).not.toHaveBeenCalled();
    let resolveBody!: (value: unknown) => void;
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve({
          ok: true,
          status: 200,
          headers: new Headers({ 'Content-Type': 'application/json' }),
          json: () =>
            new Promise<unknown>((resolve) => {
              resolveBody = resolve;
            }),
        } as Response),
      ),
    );
    const controller = new AbortController();
    const pending = getJson('/api/v1/releases/', decode, controller.signal);
    await vi.waitFor(() => {
      expect(resolveBody).toBeDefined();
    });
    controller.abort();
    await expect(pending).rejects.toMatchObject({ kind: 'cancelled' });
    resolveBody({ late: true });
  });
  it('settles cancellation and deadline even when fetch ignores abort', async () => {
    vi.useFakeTimers();
    let resolve!: (response: Response) => void;
    vi.stubGlobal(
      'fetch',
      vi.fn(
        () =>
          new Promise<Response>((r) => {
            resolve = r;
          }),
      ),
    );
    const controller = new AbortController();
    const cancelled = getJson('/api/v1/releases/', decode, controller.signal);
    controller.abort();
    await expect(cancelled).rejects.toMatchObject({ kind: 'cancelled' });
    const timed = getJson('/api/v1/releases/', decode);
    const timeoutAssertion = expect(timed).rejects.toMatchObject({ kind: 'timeout' });
    await vi.advanceTimersByTimeAsync(30_001);
    await timeoutAssertion;
    resolve(json({ late: true }));
  });
  it('rejects network errors without leaking transport details', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('socket secret')));
    await expect(getJson('/api/v1/releases/', decode)).rejects.toMatchObject({
      kind: 'network',
      message: 'The API could not be reached.',
    });
  });
  it('rejects arbitrary URL origins before fetch', async () => {
    const fetch = vi.fn();
    vi.stubGlobal('fetch', fetch);
    await expect(getJson('http://backend:8000/api/v1/releases/', decode)).rejects.toMatchObject({
      kind: 'unexpected',
    });
    expect(fetch).not.toHaveBeenCalled();
  });
  it.each(['type', 'json', 'shape'])(
    'retains request IDs for a malformed success %s',
    async (kind) => {
      const requestId = 'ffffffffffffffffffffffffffffffff';
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue(
          new Response(kind === 'json' ? '{broken' : JSON.stringify({ count: 0 }), {
            headers: {
              'Content-Type': kind === 'type' ? 'text/html' : 'application/json',
              'X-Request-ID': requestId,
            },
          }),
        ),
      );
      await expect(getJson('/api/v1/releases/', decodeReleasePage)).rejects.toMatchObject({
        kind: 'unexpected',
        requestId,
      });
    },
  );
  it('rejects credentials and fragments on initial API URLs before fetching', async () => {
    const fetch = vi.fn();
    vi.stubGlobal('fetch', fetch);
    const credentialUrl = new URL('/api/v1/releases/', window.location.origin);
    credentialUrl.username = 'example';
    credentialUrl.password = 'example';
    await expect(getJson(credentialUrl.href, decode)).rejects.toMatchObject({ kind: 'unexpected' });
    await expect(getJson('/api/v1/releases/#fragment', decode)).rejects.toMatchObject({
      kind: 'unexpected',
    });
    expect(fetch).not.toHaveBeenCalled();
  });
});

describe('pagination URL policy', () => {
  const endpoint = 'http://localhost:5173/api/v1/served-unserved/rollups/';
  it('resolves endpoint-relative links and preserves opaque query bytes', () => {
    expect(resolvePageUrl('?cursor=a%2Bb+%3D&page=2', endpoint)).toBe(
      'http://localhost:5173/api/v1/served-unserved/rollups/?cursor=a%2Bb+%3D&page=2',
    );
    expect(
      resolvePageUrl('http://localhost:5173/api/v1/served-unserved/rollups/?page=2', endpoint),
    ).toBe('http://localhost:5173/api/v1/served-unserved/rollups/?page=2');
    expect(resolvePageUrl('/api/v1/served-unserved/rollups/?page=2', endpoint)).toBe(
      `${endpoint}?page=2`,
    );
    const locations = 'http://localhost:5173/api/v1/served-unserved/locations/';
    expect(resolvePageUrl('?cursor=a%2Bb+%3D&as_of=2025-12-31', locations)).toBe(
      `${locations}?cursor=a%2Bb+%3D&as_of=2025-12-31`,
    );
  });
  it.each([
    'http://backend:8000/api/v1/served-unserved/rollups/?page=2',
    'http://localhost:8000/api/v1/served-unserved/rollups/?page=2',
    'http://localhost:5173/api/v1/releases/',
    'https://localhost:5173/api/v1/served-unserved/rollups/',
    '//evil.example/api/v1/served-unserved/rollups/',
    'http://u:p@localhost:5173/api/v1/served-unserved/rollups/',
    '?page=2#frag',
    '../rollups/?page=2',
    '/api/v1/served-unserved%2frollups/?page=2',
    '/api/v1/served-unserved/%2e%2e/releases/',
    '/api/v1/served-unserved/%2e/rollups/',
  ])('rejects unsafe pagination link %s', (link) => {
    expect(() => resolvePageUrl(link, endpoint)).toThrow(ApiFailure);
  });
});
