import { vi } from 'vitest';
type Listener = (event: { features?: { properties: { code: string } }[] }) => void;
export const mapConfig = { autoLoad: true, failConstruction: false };
export const maps: MockMap[] = [];
export class MockMap {
  listeners = new Map<string, Listener[]>();
  source = { setData: vi.fn().mockResolvedValue(undefined) };
  setFilter = vi.fn();
  setFeatureState = vi.fn();
  addLayer = vi.fn();
  addSource = vi.fn();
  addImage = vi.fn();
  addControl = vi.fn();
  setMaxBounds = vi.fn();
  fitBounds = vi.fn();
  resize = vi.fn();
  touchZoomRotate = { disableRotation: vi.fn() };
  remove = vi.fn(() => {
    this.listeners.clear();
  });
  constructor() {
    if (mapConfig.failConstruction) throw new Error('No WebGL');
    maps.push(this);
  }
  getBounds() {
    return { getWest: () => -84, getEast: () => -83.9, getSouth: () => 39, getNorth: () => 39.1 };
  }
  getSource() {
    return this.source;
  }
  on(type: string, layerOrListener: string | Listener, listener?: Listener) {
    const fn = typeof layerOrListener === 'string' ? listener : layerOrListener;
    if (!fn) return this;
    const key = typeof layerOrListener === 'string' ? `${type}:${layerOrListener}` : type;
    this.listeners.set(key, [...(this.listeners.get(key) ?? []), fn]);
    if (type === 'load' && mapConfig.autoLoad)
      queueMicrotask(() => {
        this.emit('load');
      });
    return this;
  }
  emit(key: string, code?: string) {
    for (const fn of this.listeners.get(key) ?? [])
      fn(code ? { features: [{ properties: { code } }] } : {});
  }
}
export const maplibre = {
  Map: MockMap,
  NavigationControl: vi.fn(),
  AttributionControl: vi.fn(),
  setWorkerUrl: vi.fn(),
};
export function resetMapMock() {
  maps.length = 0;
  mapConfig.autoLoad = true;
  mapConfig.failConstruction = false;
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe = vi.fn();
      disconnect = vi.fn();
    },
  );
}
