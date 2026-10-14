import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { App } from './App';

function mockFetch(status: number, body: unknown) {
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.resolve(new Response(JSON.stringify(body), { status }))),
  );
}

describe('App', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('shows every component as connected', async () => {
    mockFetch(200, { status: 'ok', database: 'ok', redis: 'ok', worker: 'ok' });

    render(<App />);

    expect(await screen.findByText('✓ API')).toBeInTheDocument();
    expect(screen.getByText('✓ PostGIS')).toBeInTheDocument();
    expect(screen.getByText('✓ Redis')).toBeInTheDocument();
    expect(screen.getByText('✓ Celery worker')).toBeInTheDocument();
  });

  it('marks an unreachable component as failed', async () => {
    mockFetch(503, { status: 'error', database: 'ok', redis: 'ok', worker: 'unreachable' });

    render(<App />);

    expect(await screen.findByText('✗ Celery worker')).toBeInTheDocument();
    expect(screen.getByText('✓ PostGIS')).toBeInTheDocument();
  });

  it('reports an unreachable API', async () => {
    mockFetch(502, {});
    vi.spyOn(console, 'error').mockImplementation(() => undefined);

    render(<App />);

    expect(await screen.findByText('✗ The API cannot be reached.')).toBeInTheDocument();
  });
});
