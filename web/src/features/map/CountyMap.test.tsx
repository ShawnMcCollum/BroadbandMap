import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest';
import { StrictMode } from 'react';
import { CountyMap } from './CountyMap';
import { countyRows } from './join';
import { decodeCountyPage } from '../../api/counties';
import { countyPage, first, rollupPage } from '../../test-fixtures/api';
import { maps, mapConfig, resetMapMock } from '../../test-fixtures/maplibre';
vi.mock('maplibre-gl', async () => (await import('../../test-fixtures/maplibre')).maplibre);
beforeEach(resetMapMock);
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});
const geometry = decodeCountyPage(countyPage());
const props = () => ({
  geometry,
  rows: countyRows(geometry, rollupPage().results),
  ready: true,
  selected: null,
  onSelect: vi.fn(),
  onHover: vi.fn(),
});
describe('MapLibre lifecycle and selection', () => {
  it('updates styling without recreating the map or reprocessing geometry', async () => {
    const input = props(),
      view = render(<CountyMap {...input} />);
    await waitFor(() => {
      expect(first(maps).addSource).toHaveBeenCalledTimes(1);
    });
    const map = first(maps);
    view.rerender(<CountyMap {...input} ready={false} selected="39001" />);
    expect(maps).toHaveLength(1);
    expect(map.source.setData).not.toHaveBeenCalled();
    expect(map.setFeatureState).toHaveBeenLastCalledWith(
      { source: 'counties', id: '39001' },
      { color: '#e5e7eb' },
    );
    expect(map.setFilter).toHaveBeenCalledWith('selected', ['==', ['get', 'code'], '39001']);
    const refreshed = decodeCountyPage(countyPage());
    view.rerender(<CountyMap {...input} geometry={refreshed} />);
    expect(map.source.setData).toHaveBeenCalledWith(refreshed);
    expect(maps).toHaveLength(1);
    view.unmount();
    expect(map.remove).toHaveBeenCalledTimes(1);
    expect(map.listeners.size).toBe(0);
  });
  it('routes click and hover independently and offers explicit fit', async () => {
    const input = props();
    render(<CountyMap {...input} />);
    await waitFor(() => {
      expect(first(maps).addSource).toHaveBeenCalled();
    });
    const map = first(maps);
    act(() => {
      map.emit('mousemove:county-fill', '39001');
    });
    expect(input.onHover).toHaveBeenCalledWith('39001');
    expect(input.onSelect).not.toHaveBeenCalled();
    act(() => {
      map.emit('click:county-fill', '39001');
    });
    expect(input.onSelect).toHaveBeenCalledWith('39001');
    act(() => {
      map.emit('mouseleave:county-fill');
    });
    expect(input.onHover).toHaveBeenLastCalledWith(null);
    fireEvent.click(screen.getByText('Fit Ohio'));
    expect(map.fitBounds).toHaveBeenCalledTimes(2);
  });
  it('applies the latest props after delayed renderer load', () => {
    mapConfig.autoLoad = false;
    const input = props(),
      view = render(<CountyMap {...input} />);
    view.rerender(<CountyMap {...input} ready={false} selected="39001" />);
    act(() => {
      first(maps).emit('load');
    });
    expect(first(maps).setFeatureState).toHaveBeenLastCalledWith(
      { source: 'counties', id: '39001' },
      { color: '#e5e7eb' },
    );
  });
  it('retains hover outline through a preview rerender and clears it on data change', async () => {
    const input = props(),
      view = render(<CountyMap {...input} />);
    await waitFor(() => {
      expect(first(maps).addSource).toHaveBeenCalled();
    });
    const map = first(maps);
    act(() => {
      map.emit('mousemove:county-fill', '39001');
    });
    map.setFilter.mockClear();
    view.rerender(<CountyMap {...input} onHover={vi.fn()} />);
    expect(map.setFilter.mock.calls.filter((call) => call[0] === 'hover')).toHaveLength(0);
    view.rerender(<CountyMap {...input} ready={false} />);
    expect(map.setFilter).toHaveBeenCalledWith('hover', ['==', ['get', 'code'], '']);
  });
  it('keeps a usable failure message on construction failure and retries explicitly', async () => {
    mapConfig.failConstruction = true;
    render(<CountyMap {...props()} />);
    expect(await screen.findByText(/Interactive map unavailable/)).toBeInTheDocument();
    mapConfig.failConstruction = false;
    fireEvent.click(screen.getByText('Retry interactive map'));
    await waitFor(() => {
      expect(first(maps).addSource).toHaveBeenCalled();
    });
    expect(screen.queryByText(/Interactive map unavailable/)).not.toBeInTheDocument();
  });
  it.each(['error', 'webglcontextlost'])('removes the renderer on %s', async (event) => {
    const view = render(<CountyMap {...props()} />);
    await waitFor(() => {
      expect(first(maps).addSource).toHaveBeenCalled();
    });
    const map = first(maps);
    act(() => {
      map.emit(event);
    });
    expect(screen.getByText(/Interactive map unavailable/)).toBeInTheDocument();
    view.unmount();
    expect(map.remove).toHaveBeenCalledTimes(1);
  });
  it('bounds worker load time and cleans up StrictMode instances', () => {
    vi.useFakeTimers();
    mapConfig.autoLoad = false;
    const view = render(
      <StrictMode>
        <CountyMap {...props()} />
      </StrictMode>,
    );
    act(() => {
      vi.advanceTimersByTime(30000);
    });
    expect(screen.getByText(/Interactive map unavailable/)).toBeInTheDocument();
    view.unmount();
    for (const map of maps) expect(map.remove).toHaveBeenCalledTimes(1);
    expect(vi.getTimerCount()).toBe(0);
  });
});
