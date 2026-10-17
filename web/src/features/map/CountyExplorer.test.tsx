import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest';
import { App } from '../../App';
import { countyPage, d25, deferred, first, releasePage, rollupPage } from '../../test-fixtures/api';
import { maps, resetMapMock } from '../../test-fixtures/maplibre';
vi.mock('maplibre-gl', async () => (await import('../../test-fixtures/maplibre')).maplibre);
const response = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
beforeEach(() => {
  resetMapMock();
  window.history.replaceState(null, '', window.location.pathname);
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});
function setup(
  options: {
    missing?: boolean;
    geoFailed?: boolean;
    summaryFailed?: boolean;
    diagnosis?: string;
  } = {},
) {
  const calls: URL[] = [];
  const fetch = vi.fn((input: RequestInfo | URL) => {
    const url = new URL(
      typeof input === 'string' ? input : input instanceof URL ? input.href : input.url,
    );
    calls.push(url);
    if (url.pathname.endsWith('/releases/')) return Promise.resolve(response(releasePage()));
    if (url.pathname.endsWith('/geographies/county/'))
      return Promise.resolve(
        options.geoFailed
          ? new Response('bad', { status: 502 })
          : response(countyPage(['39001', '39003'])),
      );
    if (options.summaryFailed) return Promise.resolve(new Response('bad', { status: 503 }));
    const code = url.searchParams.get('code');
    if (code) {
      if (options.diagnosis === '503' || options.diagnosis === '404')
        return Promise.resolve(new Response('unavailable', { status: Number(options.diagnosis) }));
      const body = rollupPage(
        d25,
        options.diagnosis === 'observed' ? rollupPage().results : [],
        options.diagnosis === 'observed'
          ? 'observed'
          : options.diagnosis === 'outside'
            ? 'outside_release_coverage'
            : 'no_observations',
      );
      body.selection.code = code;
      return Promise.resolve(response(body));
    }
    const flag = url.searchParams.get('flag') ?? 'wired';
    const release = {
      ...d25,
      as_of: url.searchParams.get('as_of') ?? d25.as_of,
      processed_on: url.searchParams.get('processed_on') ?? d25.processed_on,
      filing_period: url.searchParams.get('as_of') === d25.as_of ? 'D25' : 'J25',
    };
    const row = first(rollupPage().results),
      served = flag === 'any' ? 90 : flag === 'terrestrial' ? 50 : 70;
    const body = rollupPage(
      release,
      options.missing ? [] : [{ ...row, served, not_served: 100 - served }],
    );
    body.selection.flag = flag as 'wired';
    return Promise.resolve(response(body));
  });
  vi.stubGlobal('fetch', fetch);
  return { fetch, calls };
}
describe('county exploration', () => {
  it('keeps selector, table, detail and renderer aligned without new geometry or summary reads for county changes', async () => {
    const { calls } = setup();
    render(<App />);
    await screen.findByText('County summaries loaded: 1.');
    await screen.findByRole('option', { name: 'Adams County (39001)' });
    const selector = screen.getByLabelText('County');
    selector.focus();
    fireEvent.change(selector, { target: { value: '39001' } });
    const detail = screen.getByRole('region', { name: 'County detail' });
    expect(within(detail).getByText('70.0%')).toBeInTheDocument();
    expect(selector).toHaveFocus();
    expect(calls.filter((u) => u.pathname.endsWith('/rollups/'))).toHaveLength(1);
    const map = first(maps);
    act(() => {
      map.emit('mousemove:county-fill', '39003');
    });
    expect(selector).toHaveValue('39001');
    fireEvent.change(screen.getByLabelText('Technology flag'), { target: { value: 'any' } });
    await waitFor(() => expect(within(detail).getByText('90.0%')).toBeInTheDocument());
    expect(calls.filter((u) => u.pathname.includes('/geographies/'))).toHaveLength(1);
    expect(maps).toHaveLength(1);
    fireEvent.change(selector, { target: { value: '' } });
    expect(within(detail).getByText('Select a county to see its detail.')).toBeInTheDocument();
  });
  it.each(['missing', 'outside'])('diagnoses only the selected %s county', async (diagnosis) => {
    const { calls } = setup({ missing: true, diagnosis });
    render(<App />);
    await screen.findByText(/No stored county summaries/);
    await screen.findByRole('option', { name: 'Adams County (39001)' });
    expect(calls.some((u) => u.searchParams.has('code'))).toBe(false);
    fireEvent.change(screen.getByLabelText('County'), { target: { value: '39001' } });
    await screen.findByText(
      diagnosis === 'outside'
        ? 'This area is outside the loaded coverage of this release.'
        : 'No locations were observed in this area for this release.',
    );
    expect(calls.filter((u) => u.searchParams.has('code'))).toHaveLength(1);
    expect(screen.queryByText('0.0%')).not.toBeInTheDocument();
  });
  it('keeps summary counts usable after geometry failure', async () => {
    setup({ geoFailed: true });
    render(<App />);
    await screen.findByText('Could not load county boundaries.');
    expect(
      await screen.findByRole('button', { name: 'Select County GEOID 39001' }),
    ).toBeInTheDocument();
    expect(within(screen.getByRole('table')).getByText('70.0%')).toBeInTheDocument();
  });
  it('keeps newly observed diagnostic counts out of the table until an explicit refresh', async () => {
    const options = { missing: true, diagnosis: 'observed' };
    const { calls } = setup(options);
    render(<App />);
    await screen.findByRole('option', { name: 'Adams County (39001)' });
    fireEvent.change(screen.getByLabelText('County'), { target: { value: '39001' } });
    await screen.findByText('County summaries changed. Refresh to update the map and table.');
    expect(screen.queryByText('70.0%')).not.toBeInTheDocument();
    options.missing = false;
    fireEvent.click(screen.getByText('Refresh county summaries'));
    await waitFor(() => {
      expect(within(screen.getByRole('table')).getByText('70.0%')).toBeInTheDocument();
    });
    expect(calls.filter((u) => u.pathname.includes('/geographies/'))).toHaveLength(1);
  });
  it('explains unavailable selected rollups without inventing zeros', async () => {
    setup({ missing: true, diagnosis: '503' });
    render(<App />);
    await screen.findByRole('option', { name: 'Adams County (39001)' });
    fireEvent.change(screen.getByLabelText('County'), { target: { value: '39001' } });
    await screen.findByText(
      'County summaries are unavailable. An application operator may need to rebuild them.',
    );
    expect(screen.getByText('Retry county detail')).toBeInTheDocument();
    expect(screen.queryByText('0.0%')).not.toBeInTheDocument();
  });
  it('rediscovers once after missing-detail 404 and stops the automatic recovery', async () => {
    const { calls } = setup({ missing: true, diagnosis: '404' });
    render(<App />);
    await screen.findByRole('option', { name: 'Adams County (39001)' });
    fireEvent.change(screen.getByLabelText('County'), { target: { value: '39001' } });
    await screen.findByText('The API request failed (HTTP 404).');
    await waitFor(() => {
      expect(calls.filter((u) => u.pathname.endsWith('/releases/'))).toHaveLength(2);
    });
    expect(calls.filter((u) => u.searchParams.has('code'))).toHaveLength(2);
  });
  it('rereads boundaries on full Refresh but reuses the renderer', async () => {
    const { calls } = setup();
    render(<App />);
    await screen.findByRole('option', { name: 'Adams County (39001)' });
    await waitFor(() => {
      expect(first(maps).addSource).toHaveBeenCalled();
    });
    fireEvent.click(screen.getByRole('button', { name: 'Refresh' }));
    await waitFor(() => {
      expect(calls.filter((u) => u.pathname.includes('/geographies/'))).toHaveLength(2);
    });
    await screen.findByText('County summaries loaded: 1.');
    expect(maps).toHaveLength(1);
  });
  it('ignores a late diagnostic for the previously selected county', async () => {
    const { fetch } = setup({ missing: true });
    const pending = deferred<Response>();
    const original = fetch.getMockImplementation();
    if (!original) throw new Error('Expected fetch mock');
    fetch.mockImplementation((input) => {
      const url = new URL(
        typeof input === 'string' ? input : input instanceof URL ? input.href : input.url,
      );
      return url.searchParams.get('code') === '39001' ? pending.promise : original(input);
    });
    render(<App />);
    await screen.findByRole('option', { name: 'Adams County (39001)' });
    fireEvent.change(screen.getByLabelText('County'), { target: { value: '39001' } });
    await screen.findByText('Checking county coverage…');
    fireEvent.change(screen.getByLabelText('County'), { target: { value: '39003' } });
    await screen.findByText('No locations were observed in this area for this release.');
    const body = rollupPage(d25, [], 'outside_release_coverage');
    body.selection.code = '39001';
    await act(async () => {
      pending.resolve(response(body));
      await pending.promise;
    });
    expect(
      screen.queryByText('This area is outside the loaded coverage of this release.'),
    ).not.toBeInTheDocument();
    expect(screen.getByLabelText('County')).toHaveValue('39003');
  });
  it('keeps named counties usable without fabricating counts after summary failure', async () => {
    setup({ summaryFailed: true });
    render(<App />);
    await screen.findByText(/County summaries are unavailable/);
    expect(await screen.findByRole('button', { name: 'Select Adams County' })).toBeInTheDocument();
    expect(screen.queryByText('70.0%')).not.toBeInTheDocument();
  });
  it('aborts obsolete geometry on departure and ignores its late result', async () => {
    const pending = deferred<Response>();
    let signal: AbortSignal | undefined;
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const url = new URL(
          typeof input === 'string' ? input : input instanceof URL ? input.href : input.url,
        );
        if (url.pathname.endsWith('/releases/')) return Promise.resolve(response(releasePage()));
        if (url.pathname.includes('/geographies/')) {
          signal = init?.signal ?? undefined;
          return pending.promise;
        }
        return Promise.resolve(response(rollupPage()));
      }),
    );
    const view = render(<App />);
    await screen.findByText('County summaries loaded: 1.');
    await waitFor(() => {
      expect(signal).toBeDefined();
    });
    view.unmount();
    expect(signal?.aborted).toBe(true);
    await act(async () => {
      pending.resolve(response(countyPage()));
      await pending.promise;
    });
    expect(maps).toHaveLength(0);
  });
});
