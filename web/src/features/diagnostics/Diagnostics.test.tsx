import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { Diagnostics } from './Diagnostics';

const body = { status: 'error', database: 'ok', redis: 'ok', worker: 'unreachable' };
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});
describe('Diagnostics', () => {
  it('shows a successful health report and retries non-503 HTTP failures', async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(new Response('{}', { status: 500 }))
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ status: 'ok', database: 'ok', redis: 'ok', worker: 'ok' }), {
          status: 200,
        }),
      );
    vi.stubGlobal('fetch', fetch);
    render(<Diagnostics active />);
    expect(await screen.findByText('✗ The API cannot be reached.')).toBeInTheDocument();
    fireEvent.click(screen.getByText('Retry'));
    expect(await screen.findByText('✓ API')).toBeInTheDocument();
    expect(screen.getByText('✓ PostGIS')).toBeInTheDocument();
  });
  it('preserves valid health 503 semantics and retries explicitly', async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(body), { status: 503 }))
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ ...body, worker: 'ok', status: 'ok' }), { status: 200 }),
      );
    vi.stubGlobal('fetch', fetch);
    render(<Diagnostics active />);
    expect(await screen.findByText('✗ Celery worker')).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledTimes(1);
  });
  it('does not publish a result after departure', () => {
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
    const { rerender } = render(<Diagnostics active />);
    rerender(<Diagnostics active={false} />);
    resolve(
      new Response(JSON.stringify({ status: 'ok', database: 'ok', redis: 'ok', worker: 'ok' }), {
        status: 200,
      }),
    );
    expect(screen.queryByText('✓ API')).not.toBeInTheDocument();
  });
});
