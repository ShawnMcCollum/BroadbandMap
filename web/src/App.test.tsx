import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { StrictMode } from 'react';
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest';
import { App } from './App';
import { resetMapMock } from './test-fixtures/maplibre';
vi.mock('maplibre-gl', async () => (await import('./test-fixtures/maplibre')).maplibre);
import { d25, j25, releasePage, rollupPage, deferred, countyPage } from './test-fixtures/api';
beforeEach(resetMapMock);

const response = (body: unknown, status = 200, type = 'application/json') =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': type } });
const inputUrl = (input: RequestInfo | URL) =>
  new URL(
    typeof input === 'string' ? input : input instanceof URL ? input.href : input.url,
    window.location.origin,
  ).href;
function setupFetch(
  summary: (url: URL) => Response | Promise<Response> = () => response(rollupPage()),
) {
  const calls: URL[] = [];
  const fetch = vi.fn((input: RequestInfo | URL) => {
    const url = new URL(inputUrl(input));
    if (url.pathname.endsWith('/geographies/county/'))
      return Promise.resolve(response(countyPage()));
    calls.push(url);
    if (url.pathname === '/api/health/')
      return Promise.resolve(response({ status: 'ok', database: 'ok', redis: 'ok', worker: 'ok' }));
    if (url.pathname.endsWith('/releases/')) return Promise.resolve(response(releasePage()));
    return Promise.resolve(summary(url));
  });
  vi.stubGlobal('fetch', fetch);
  return { fetch, calls };
}
afterEach(() => {
  // Reset without queuing a hashchange event into the next mounted application.
  window.history.replaceState(null, '', window.location.pathname + window.location.search);
  document.title = '';
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('application shell and exploration', () => {
  it('loads complete release versions, pins dates, loads complete summaries and retains provenance', async () => {
    const { calls } = setupFetch((url) =>
      response({
        ...rollupPage(url.searchParams.get('as_of') === j25.as_of ? j25 : d25),
        selection: { level: 'county', state: '39', code: null, flag: url.searchParams.get('flag') },
      }),
    );
    render(<App />);
    expect(screen.getByText('Loading releases…')).toBeInTheDocument();
    expect(await screen.findByText('County summaries loaded: 1.')).toBeInTheDocument();
    expect(screen.getByLabelText('FCC data release')).toHaveValue(
      `${d25.as_of}|${d25.processed_on}`,
    );
    expect(
      screen.getByRole('option', { name: /2025-12-31 · processed 2026-09-29/ }),
    ).toBeInTheDocument();
    expect(screen.getAllByText(/Loaded states: Ohio \(39\)/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/FCC National Broadband Map/).length).toBeGreaterThan(0);
    const summary = calls.find((url) => url.pathname.endsWith('/rollups/'));
    expect(summary).toBeDefined();
    if (!summary) throw new Error('Expected a county summary request.');
    expect(summary.searchParams.get('as_of')).toBe(d25.as_of);
    expect(summary.searchParams.get('processed_on')).toBe(d25.processed_on);
    expect(summary.searchParams.get('page_size')).toBe('100');
    expect(screen.getByRole('table')).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: '100' })).toBeInTheDocument();
  });
  it('keeps release and flag controls as the single selection owner', async () => {
    const { calls } = setupFetch((url) =>
      response({
        ...rollupPage(url.searchParams.get('as_of') === j25.as_of ? j25 : d25),
        selection: { level: 'county', state: '39', code: null, flag: url.searchParams.get('flag') },
      }),
    );
    render(<App />);
    await screen.findByText('County summaries loaded: 1.');
    fireEvent.change(screen.getByLabelText('FCC data release'), {
      target: { value: `${j25.as_of}|${j25.processed_on}` },
    });
    await waitFor(() =>
      expect(screen.getByLabelText('FCC data release')).toHaveValue(
        `${j25.as_of}|${j25.processed_on}`,
      ),
    );
    fireEvent.change(screen.getByLabelText('Technology flag'), {
      target: { value: 'terrestrial' },
    });
    await waitFor(() => {
      expect(
        calls.some(
          (u) =>
            u.searchParams.get('as_of') === j25.as_of &&
            u.searchParams.get('processed_on') === j25.processed_on &&
            u.searchParams.get('flag') === 'terrestrial' &&
            u.searchParams.get('state') === '39',
        ),
      ).toBe(true);
    });
    expect(screen.getByText(/terrestrial_100_20/)).toBeInTheDocument();
  });
  it('shows empty releases guidance without requesting summaries', async () => {
    const fetch = vi.fn().mockResolvedValue(response(releasePage([])));
    vi.stubGlobal('fetch', fetch);
    render(<App />);
    expect(await screen.findByText(/No data releases are loaded/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'README data-load instructions' })).toHaveAttribute(
      'href',
      expect.stringContaining('#load-the-ohio-data'),
    );
    expect(fetch).toHaveBeenCalledTimes(1);
  });
  it('does not fall back to an older Ohio release when latest lacks Ohio', async () => {
    const latest = { ...d25, states: [{ code: '54', name: 'West Virginia', abbreviation: 'WV' }] };
    const fetch = vi.fn((input: RequestInfo | URL) =>
      new URL(inputUrl(input)).pathname.endsWith('/releases/')
        ? Promise.resolve(response(releasePage([latest, j25])))
        : Promise.resolve(response(rollupPage())),
    );
    vi.stubGlobal('fetch', fetch);
    render(<App />);
    expect(await screen.findByText('Ohio is not loaded for this release.')).toBeInTheDocument();
    expect(screen.getByLabelText('FCC data release')).toHaveValue(
      `${latest.as_of}|${latest.processed_on}`,
    );
    expect(fetch).toHaveBeenCalledTimes(1);
    fireEvent.change(screen.getByLabelText('FCC data release'), {
      target: { value: `${j25.as_of}|${j25.processed_on}` },
    });
    await waitFor(() => {
      expect(
        fetch.mock.calls.filter((c) => !inputUrl(c[0]).includes('/geographies/')),
      ).toHaveLength(2);
    });
  });
  it('distinguishes empty and unavailable summary reads and supports explicit retry', async () => {
    const { fetch } = setupFetch((url) => {
      const body = rollupPage(d25, [], 'stored_rollups_only');
      if (
        url.searchParams.get('page_size') === '100' &&
        fetch.mock.calls.filter((c) => inputUrl(c[0]).includes('/rollups/')).length === 1
      )
        return response({}, 503, 'text/html');
      return response(body);
    });
    render(<App />);
    expect(await screen.findByText(/County summaries are unavailable/)).toBeInTheDocument();
    fireEvent.click(screen.getByText('Retry summaries'));
    expect(
      await screen.findByText(
        'No stored county summaries were returned. Select a county to check its coverage.',
      ),
    ).toBeInTheDocument();
  });
  it('switches hash routes, updates title, preserves map selection and keeps diagnostics contract', async () => {
    setupFetch();
    render(<App />);
    await screen.findByText('County summaries loaded: 1.');
    window.location.hash = '#/ask';
    fireEvent(window, new HashChangeEvent('hashchange'));
    expect(await screen.findByRole('heading', { name: 'Ask (stub)' })).toBeInTheDocument();
    expect(document.title).toContain('Ask (stub)');
    window.location.hash = '#/diagnostics';
    fireEvent(window, new HashChangeEvent('hashchange'));
    const health = await screen.findByText('✓ API');
    expect(health).toBeInTheDocument();
  });
  it('ignores stale summary success after selecting a different release even if transport ignores abort', async () => {
    let resolveA!: (value: Response) => void;
    const fetch = vi.fn((input: RequestInfo | URL) => {
      const url = new URL(inputUrl(input));
      if (url.pathname.endsWith('/geographies/county/'))
        return Promise.resolve(response(countyPage()));
      if (url.pathname === '/api/health/')
        return Promise.resolve(
          response({ status: 'ok', database: 'ok', redis: 'ok', worker: 'ok' }),
        );
      if (url.pathname.endsWith('/releases/')) return Promise.resolve(response(releasePage()));
      if (url.searchParams.get('as_of') === d25.as_of)
        return new Promise<Response>((resolve) => {
          resolveA = resolve;
        });
      return Promise.resolve(
        response({
          ...rollupPage(j25),
          selection: { level: 'county', state: '39', code: null, flag: 'wired' },
        }),
      );
    });
    vi.stubGlobal('fetch', fetch);
    render(<App />);
    await screen.findByText('Loading county summaries…');
    fireEvent.change(await screen.findByLabelText('FCC data release'), {
      target: { value: `${j25.as_of}|${j25.processed_on}` },
    });
    expect(await screen.findByText('County summaries loaded: 1.')).toBeInTheDocument();
    resolveA(response(rollupPage(d25)));
    await waitFor(() =>
      expect(screen.getByText('County summaries loaded: 1.')).toBeInTheDocument(),
    );
    expect(screen.getByLabelText('FCC data release')).toHaveValue(
      `${j25.as_of}|${j25.processed_on}`,
    );
  });
  it('shows route-specific not-found content', async () => {
    render(<App />);
    window.location.hash = '#/nonesuch';
    fireEvent(window, new HashChangeEvent('hashchange'));
    expect(await screen.findByRole('heading', { name: 'Page not found' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Return to the map' })).toHaveAttribute(
      'href',
      '#/map',
    );
  });

  it('associates structured flag/date errors and preserves global pointers and request ID', async () => {
    const errors = [
      { pointer: '/flag', code: 'invalid', message: 'Choose a supported flag.' },
      { pointer: '/as_of', code: 'invalid', message: 'Choose a loaded date.' },
      { pointer: '', code: 'invalid', message: 'The selection needs attention.' },
      { pointer: '/future', code: 'invalid', message: 'A related field is invalid.' },
    ];
    const problem = {
      type: 'about:blank',
      title: 'Invalid request',
      status: 400,
      detail: 'Please correct the selection.',
      code: 'invalid',
      request_id: 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
      errors,
    };
    setupFetch(
      () =>
        new Response(JSON.stringify(problem), {
          status: 400,
          headers: {
            'Content-Type': 'application/problem+json',
            'X-Request-ID': 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
          },
        }),
    );
    render(<App />);
    expect(await screen.findByText('Choose a supported flag.')).toBeInTheDocument();
    expect(screen.getByLabelText('Technology flag')).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByLabelText('Technology flag')).toHaveAttribute(
      'aria-describedby',
      'flag-help flag-error',
    );
    expect(screen.getByLabelText('FCC data release')).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByText('Request: The selection needs attention.')).toBeInTheDocument();
    expect(screen.getByText('/future: A related field is invalid.')).toBeInTheDocument();
    expect(screen.getByText('Request ID: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa')).toBeInTheDocument();
    expect(screen.queryByText(/<html/i)).not.toBeInTheDocument();
  });

  it('shows safe messages for malformed content and network failure', async () => {
    let call = 0;
    const fetch = vi.fn((input: RequestInfo | URL) => {
      const url = new URL(inputUrl(input));
      if (url.pathname.endsWith('/geographies/county/'))
        return Promise.resolve(response(countyPage()));
      if (url.pathname.endsWith('/releases/')) return Promise.resolve(response(releasePage()));
      call += 1;
      if (call === 1)
        return Promise.resolve(
          new Response('<html>private traceback</html>', {
            status: 502,
            headers: { 'Content-Type': 'text/html' },
          }),
        );
      return Promise.reject(new Error('private socket detail'));
    });
    vi.stubGlobal('fetch', fetch);
    render(<App />);
    expect(await screen.findByText('The API request failed (HTTP 502).')).toBeInTheDocument();
    expect(screen.queryByText(/private traceback|private socket detail/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByText('Retry summaries'));
    expect(await screen.findByText('The API could not be reached.')).toBeInTheDocument();
  });

  it('refreshes the complete catalog but keeps the selected release date pair', async () => {
    let catalogCount = 0;
    const fetch = vi.fn((input: RequestInfo | URL) => {
      const url = new URL(inputUrl(input));
      if (url.pathname.endsWith('/geographies/county/'))
        return Promise.resolve(response(countyPage()));
      if (url.pathname.endsWith('/releases/')) {
        catalogCount += 1;
        return Promise.resolve(
          response(
            releasePage(
              catalogCount > 1 ? [{ ...d25, processed_on: '2026-10-02' }, d25, j25] : [d25, j25],
            ),
          ),
        );
      }
      return Promise.resolve(
        response({
          ...rollupPage(url.searchParams.get('as_of') === j25.as_of ? j25 : d25),
          selection: {
            level: 'county',
            state: '39',
            code: null,
            flag: url.searchParams.get('flag'),
          },
        }),
      );
    });
    vi.stubGlobal('fetch', fetch);
    render(<App />);
    await screen.findByText('County summaries loaded: 1.');
    fireEvent.change(screen.getByLabelText('FCC data release'), {
      target: { value: `${j25.as_of}|${j25.processed_on}` },
    });
    await waitFor(() => {
      expect(screen.getByLabelText('FCC data release')).toHaveValue(
        `${j25.as_of}|${j25.processed_on}`,
      );
    });
    fireEvent.click(screen.getByText('Refresh'));
    await waitFor(() => {
      expect(screen.getByLabelText('FCC data release')).toHaveValue(
        `${j25.as_of}|${j25.processed_on}`,
      );
    });
    await waitFor(() => {
      expect(fetch.mock.calls.some((c) => inputUrl(c[0]).includes(`as_of=${j25.as_of}`))).toBe(
        true,
      );
    });
  });

  it('keeps a deleted release unselected across repeated refreshes', async () => {
    let catalogCount = 0;
    const fetch = vi.fn((input: RequestInfo | URL) => {
      const url = new URL(inputUrl(input));
      if (url.pathname.endsWith('/geographies/county/'))
        return Promise.resolve(response(countyPage()));
      if (url.pathname.endsWith('/releases/')) {
        catalogCount += 1;
        return Promise.resolve(response(releasePage(catalogCount === 1 ? [d25, j25] : [j25])));
      }
      return Promise.resolve(response(rollupPage()));
    });
    vi.stubGlobal('fetch', fetch);
    render(<App />);
    await screen.findByText('County summaries loaded: 1.');
    fireEvent.click(screen.getByText('Refresh'));
    expect(
      await screen.findByText('This release is no longer loaded. Choose a release.'),
    ).toBeInTheDocument();
    expect(screen.getByLabelText('FCC data release')).toHaveValue('');
    expect(screen.getByLabelText('Technology flag')).toBeDisabled();
    expect(screen.getByText(/Uses source field wired_100_20/)).toBeInTheDocument();
    const summariesBefore = fetch.mock.calls.filter((c) =>
      inputUrl(c[0]).includes('/rollups/'),
    ).length;
    fireEvent.click(screen.getByText('Refresh'));
    await waitFor(() => {
      expect(catalogCount).toBe(3);
    });
    expect(screen.getByLabelText('FCC data release')).toHaveValue('');
    expect(fetch.mock.calls.filter((c) => inputUrl(c[0]).includes('/rollups/'))).toHaveLength(
      summariesBefore,
    );
  });

  it('rediscovers once after summary 404, preserves its request ID, then stops', async () => {
    let summaryCalls = 0;
    const problem = {
      type: 'about:blank',
      title: 'Not found',
      status: 404,
      detail: 'Summary is not available.',
      code: 'not_found',
      request_id: 'cccccccccccccccccccccccccccccccc',
    };
    const fetch = vi.fn((input: RequestInfo | URL) => {
      const url = new URL(inputUrl(input));
      if (url.pathname.endsWith('/geographies/county/'))
        return Promise.resolve(response(countyPage()));
      if (url.pathname.endsWith('/releases/')) return Promise.resolve(response(releasePage()));
      summaryCalls += 1;
      return summaryCalls === 1
        ? Promise.resolve(
            new Response(JSON.stringify(problem), {
              status: 404,
              headers: { 'Content-Type': 'application/problem+json' },
            }),
          )
        : Promise.resolve(response(rollupPage()));
    });
    vi.stubGlobal('fetch', fetch);
    render(<App />);
    expect(
      await screen.findByText('Request ID: cccccccccccccccccccccccccccccccc'),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(fetch.mock.calls.filter((c) => inputUrl(c[0]).includes('/releases/'))).toHaveLength(2);
    });
    expect(summaryCalls).toBe(1);
    fireEvent.click(screen.getByText('Refresh'));
    expect(await screen.findByText('County summaries loaded: 1.')).toBeInTheDocument();
    expect(summaryCalls).toBe(2);
  });

  it('does not resurrect A summaries during A→B→A reads or on map re-entry in StrictMode', async () => {
    const pending: Array<{ release: string | null; resolve: (value: Response) => void }> = [];
    let summaryCalls = 0;
    const fetch = vi.fn((input: RequestInfo | URL) => {
      const url = new URL(inputUrl(input));
      if (url.pathname.endsWith('/geographies/county/'))
        return Promise.resolve(response(countyPage()));
      if (url.pathname.endsWith('/releases/')) return Promise.resolve(response(releasePage()));
      summaryCalls += 1;
      if (summaryCalls === 1) return Promise.resolve(response(rollupPage()));
      return new Promise<Response>((resolve) => {
        pending.push({ release: url.searchParams.get('as_of'), resolve });
      });
    });
    vi.stubGlobal('fetch', fetch);
    render(
      <StrictMode>
        <App />
      </StrictMode>,
    );
    await screen.findByText('County summaries loaded: 1.');
    fireEvent.change(screen.getByLabelText('FCC data release'), {
      target: { value: `${j25.as_of}|${j25.processed_on}` },
    });
    await waitFor(() => {
      expect(pending.some((p) => p.release === j25.as_of)).toBe(true);
    });
    expect(screen.getByText('Loading county summaries…')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('FCC data release'), {
      target: { value: `${d25.as_of}|${d25.processed_on}` },
    });
    await waitFor(() => {
      expect(pending.filter((p) => p.release === d25.as_of)).toHaveLength(1);
    });
    expect(screen.getByText('Loading county summaries…')).toBeInTheDocument();
    fireEvent.click(screen.getByText('Ask (stub)'));
    fireEvent.click(screen.getByText('Map'));
    await waitFor(() => {
      expect(summaryCalls).toBeGreaterThan(3);
    });
    expect(screen.getByText('Loading county summaries…')).toBeInTheDocument();
  });
});

describe('review regressions', () => {
  it('renders separate processing versions discovered on multiple release pages', async () => {
    const latest = { ...d25, processed_on: '2026-09-30' };
    const calls: URL[] = [];
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        const url = new URL(inputUrl(input));
        if (url.pathname.endsWith('/geographies/county/'))
          return Promise.resolve(response(countyPage()));
        calls.push(url);
        if (url.pathname.endsWith('/releases/')) {
          return Promise.resolve(
            response(
              url.searchParams.get('page') === '2'
                ? { ...releasePage([latest]), count: 3 }
                : { ...releasePage([j25, d25], '?page=2&page_size=100'), count: 3 },
            ),
          );
        }
        const release = url.searchParams.get('processed_on') === latest.processed_on ? latest : d25;
        return Promise.resolve(response(rollupPage(release)));
      }),
    );
    render(<App />);
    await screen.findByText('County summaries loaded: 1.');
    expect(screen.getByLabelText('FCC data release').querySelectorAll('option')).toHaveLength(3);
    expect(screen.getByLabelText('FCC data release')).toHaveValue(
      `${latest.as_of}|${latest.processed_on}`,
    );
    expect(screen.getByLabelText('Technology flag')).toHaveValue('wired');
    expect(
      screen.getByRole('option', { name: /2025-12-31 · processed 2026-09-29/ }),
    ).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('FCC data release'), {
      target: { value: `${d25.as_of}|${d25.processed_on}` },
    });
    await screen.findByText('County summaries loaded: 1.');
    const summaries = calls.filter((url) => url.pathname.endsWith('/rollups/'));
    expect(summaries.map((url) => url.searchParams.get('processed_on'))).toEqual([
      latest.processed_on,
      d25.processed_on,
    ]);
    expect(calls.filter((url) => url.pathname.endsWith('/releases/'))).toHaveLength(2);
  });

  it('uses the current summary coverage rather than stale catalog states', async () => {
    const changed = { ...d25, states: [{ code: '54', name: 'West Virginia', abbreviation: 'WV' }] };
    setupFetch(() => response(rollupPage(changed, [], 'stored_rollups_only')));
    render(<App />);
    await screen.findByText(/Ohio is not loaded for this release/);
    expect(
      screen.getByText(/Loaded states: West Virginia \(54\).*Source: FCC National Broadband Map/),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Loaded states: Ohio/)).not.toBeInTheDocument();
    expect(screen.queryByText('County summaries loaded: 1.')).not.toBeInTheDocument();
  });

  it('retains catalog field errors without controls and clears old errors during Retry', async () => {
    const pending = deferred<Response>();
    const problem = {
      type: 'about:blank',
      title: 'Bad Request',
      status: 400,
      code: 'validation_error',
      detail: 'Request validation failed.',
      request_id: 'dddddddddddddddddddddddddddddddd',
      errors: [{ pointer: '/as_of', code: 'invalid', message: 'Supply a complete date pair.' }],
    };
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(response(problem, 400, 'application/problem+json'))
        .mockImplementationOnce(() => pending.promise),
    );
    render(<App />);
    await screen.findByText('/as_of: Supply a complete date pair.');
    fireEvent.click(screen.getByText('Retry'));
    expect(screen.getByText('Loading releases…')).toBeInTheDocument();
    expect(screen.queryByText('Could not load releases.')).not.toBeInTheDocument();
    await act(async () => {
      pending.resolve(response(releasePage([])));
      await pending.promise;
    });
    expect(await screen.findByText(/No data releases are loaded/)).toBeInTheDocument();
  });

  it('shows a fresh map-entry 404 after earlier success and retries a new selection', async () => {
    let missing = false;
    const { calls } = setupFetch((url) =>
      missing
        ? response(
            {
              type: 'about:blank',
              title: 'Not Found',
              status: 404,
              code: 'not_found',
              detail: 'The requested resource was not found.',
              request_id: 'eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee',
            },
            404,
            'application/problem+json',
          )
        : response(rollupPage(url.searchParams.get('as_of') === j25.as_of ? j25 : d25)),
    );
    render(<App />);
    await screen.findByText('County summaries loaded: 1.');
    fireEvent.click(screen.getByRole('link', { name: 'Ask (stub)' }));
    await screen.findByRole('heading', { name: 'Ask (stub)' });
    missing = true;
    fireEvent.click(screen.getByRole('link', { name: 'Map' }));
    await screen.findByText('Request ID: eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee');
    expect(screen.queryByText('Loading county summaries…')).not.toBeInTheDocument();
    expect(calls.filter((url) => url.pathname.endsWith('/rollups/'))).toHaveLength(2);
    missing = false;
    fireEvent.change(screen.getByLabelText('FCC data release'), {
      target: { value: `${j25.as_of}|${j25.processed_on}` },
    });
    await screen.findByText('County summaries loaded: 1.');
    fireEvent.change(screen.getByLabelText('FCC data release'), {
      target: { value: `${d25.as_of}|${d25.processed_on}` },
    });
    await screen.findByText('County summaries loaded: 1.');
    expect(calls.filter((url) => url.pathname.endsWith('/rollups/'))).toHaveLength(4);
  });

  it('ignores a late rejected read and aborts a pending read on unmount', async () => {
    const pendingA = deferred<Response>();
    const pendingB = deferred<Response>();
    const signals: AbortSignal[] = [];
    let holdB = false;
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL, options?: RequestInit) => {
        const url = new URL(inputUrl(input));
        if (url.pathname.endsWith('/geographies/county/'))
          return Promise.resolve(response(countyPage()));
        if (url.pathname.endsWith('/releases/')) return Promise.resolve(response(releasePage()));
        if (url.searchParams.get('as_of') === d25.as_of || holdB) {
          if (options?.signal) signals.push(options.signal);
          return holdB ? pendingB.promise : pendingA.promise;
        }
        return Promise.resolve(response(rollupPage(j25)));
      }),
    );
    const view = render(<App />);
    await screen.findByText('Loading county summaries…');
    fireEvent.change(screen.getByLabelText('FCC data release'), {
      target: { value: `${j25.as_of}|${j25.processed_on}` },
    });
    await screen.findByText('County summaries loaded: 1.');
    expect(signals[0]?.aborted).toBe(true);
    await act(async () => {
      pendingA.reject(new Error('private late transport failure'));
      await pendingA.promise.catch(() => undefined);
    });
    expect(screen.queryByText('Could not load county summaries.')).not.toBeInTheDocument();
    holdB = true;
    fireEvent.click(screen.getByText('Refresh'));
    await waitFor(() => {
      expect(signals).toHaveLength(2);
    });
    view.unmount();
    expect(signals[1]?.aborted).toBe(true);
    await act(async () => {
      pendingB.resolve(response(rollupPage(j25)));
      await pendingB.promise;
    });
    expect(screen.queryByRole('main')).not.toBeInTheDocument();
  });
});
