import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import {
  Map as LibreMap,
  NavigationControl,
  AttributionControl,
  setWorkerUrl,
  type FilterSpecification,
  type GeoJSONSource,
} from 'maplibre-gl';
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
import 'maplibre-gl/dist/maplibre-gl.css';
import type { CountyCollection } from '../../api/types';
import { type CountyView, servedShare } from './join';
import { countyBounds, countyStyle, hatchImage, neutral, shareColor } from './style';

setWorkerUrl(workerUrl);
type Props = {
  geometry: CountyCollection | null;
  rows: CountyView[];
  ready: boolean;
  selected: string | null;
  onSelect: (code: string) => void;
  onHover: (code: string | null) => void;
};
// Max bounds must contain the fitted viewport, not just the county envelope.
// Otherwise MapLibre raises the zoom to fill a wide container and crops Ohio.
function fitOhio(map: LibreMap, geometry: CountyCollection) {
  const bounds = countyBounds(geometry);
  map.setMaxBounds(null);
  map.fitBounds(bounds, { padding: 24, duration: 0 });
  const view = map.getBounds();
  map.setMaxBounds([
    [Math.min(bounds[0][0], view.getWest()) - 1, Math.min(bounds[0][1], view.getSouth()) - 1],
    [Math.max(bounds[1][0], view.getEast()) + 1, Math.max(bounds[1][1], view.getNorth()) + 1],
  ]);
}
function applyValues(map: LibreMap, props: Props) {
  for (const row of props.rows)
    if (row.boundary)
      map.setFeatureState(
        { source: 'counties', id: row.code },
        {
          color:
            props.ready && row.kind === 'observed'
              ? shareColor(servedShare(row.summary.served, row.summary.locations))
              : neutral,
        },
      );
  // Filter on the string property: promoted IDs are not reliable in worker-side filters.
  map.setFilter('missing', [
    'in',
    ['get', 'code'],
    [
      'literal',
      props.ready ? props.rows.filter((r) => r.kind === 'missing').map((r) => r.code) : [],
    ],
  ]);
  const selected: FilterSpecification = ['==', ['get', 'code'], props.selected ?? ''];
  map.setFilter('selected-halo', selected);
  map.setFilter('selected', selected);
}
export function CountyMap(props: Props) {
  const container = useRef<HTMLDivElement>(null),
    mapRef = useRef<LibreMap | null>(null);
  const latest = useRef(props),
    sourceData = useRef<CountyCollection | null>(null),
    loaded = useRef(false);
  const [failed, setFailed] = useState(false),
    [retry, setRetry] = useState(0),
    [rendering, setRendering] = useState(true);
  const failureHandler = useRef<(() => void) | null>(null);
  const previous = useRef<Props | null>(null);
  const available = Boolean(props.geometry?.features.length);
  useLayoutEffect(() => {
    latest.current = props;
    const map = mapRef.current;
    if (!map || !loaded.current || !props.geometry) return;
    if (sourceData.current !== props.geometry) {
      void (map.getSource('counties') as GeoJSONSource)
        .setData(props.geometry)
        .then(() => {
          if (mapRef.current === map && loaded.current) applyValues(map, latest.current);
        })
        .catch(() => {
          if (mapRef.current === map) failureHandler.current?.();
        });
      sourceData.current = props.geometry;
    }
    applyValues(map, props);
    if (previous.current?.rows !== props.rows || previous.current.ready !== props.ready)
      map.setFilter('hover', ['==', ['get', 'code'], '']);
    previous.current = props;
  }, [props]);
  useEffect(() => {
    if (!available || !container.current) return;
    let map: LibreMap | undefined,
      removed = false,
      timer: ReturnType<typeof setTimeout> | undefined;
    let observer: ResizeObserver | undefined;
    const remove = () => {
      if (removed) return;
      removed = true;
      clearTimeout(timer);
      observer?.disconnect();
      loaded.current = false;
      mapRef.current = null;
      sourceData.current = null;
      failureHandler.current = null;
      map?.remove();
    };
    const fail = () => {
      if (!removed) {
        latest.current.onHover(null);
        remove();
        setFailed(true);
        setRendering(false);
      }
    };
    failureHandler.current = fail;
    try {
      map = new LibreMap({
        container: container.current,
        style: countyStyle(),
        minZoom: 5,
        maxZoom: 12,
        renderWorldCopies: false,
        dragRotate: false,
        pitchWithRotate: false,
        touchPitch: false,
        cooperativeGestures: true,
        attributionControl: false,
      });
      mapRef.current = map;
      map.touchZoomRotate.disableRotation();
      map.addControl(new NavigationControl({ showCompass: false }), 'top-right');
      map.addControl(
        new AttributionControl({
          compact: false,
          customAttribution: 'FCC National Broadband Map · Census TIGER/Line 2020 · MapLibre',
        }),
      );
      map.on('error', fail);
      map.on('webglcontextlost', fail);
      map.on('load', () => {
        if (!map || removed || !latest.current.geometry) return;
        try {
          const data = latest.current.geometry;
          map.addImage('missing-hatch', hatchImage());
          map.addSource('counties', { type: 'geojson', data, promoteId: 'code' });
          sourceData.current = data;
          map.addLayer({
            id: 'county-fill',
            type: 'fill',
            source: 'counties',
            paint: { 'fill-color': ['coalesce', ['feature-state', 'color'], neutral] },
          });
          map.addLayer({
            id: 'missing',
            type: 'fill',
            source: 'counties',
            paint: { 'fill-pattern': 'missing-hatch' },
          });
          for (const [id, color, width] of [
            ['county-outline', '#667887', 1],
            ['hover', '#40566b', 2],
            ['selected-halo', '#ffffff', 5],
            ['selected', '#172b3a', 3],
          ] as const)
            map.addLayer({
              id,
              type: 'line',
              source: 'counties',
              ...(id === 'county-outline' ? {} : { filter: ['==', ['get', 'code'], ''] }),
              paint: { 'line-color': color, 'line-width': width },
            });
          fitOhio(map, data);
          loaded.current = true;
          applyValues(map, latest.current);
          previous.current = latest.current;
          map.on('click', 'county-fill', (event) => {
            const code = event.features?.[0]?.properties.code as unknown;
            if (typeof code === 'string') latest.current.onSelect(code);
          });
          map.on('mousemove', 'county-fill', (event) => {
            const code = event.features?.[0]?.properties.code as unknown;
            if (typeof code === 'string' && map) {
              map.setFilter('hover', ['==', ['get', 'code'], code]);
              latest.current.onHover(code);
            }
          });
          map.on('mouseleave', 'county-fill', () => {
            if (!removed && map) {
              map.setFilter('hover', ['==', ['get', 'code'], '']);
              latest.current.onHover(null);
            }
          });
          clearTimeout(timer);
          setRendering(false);
        } catch {
          fail();
        }
      });
      observer = new ResizeObserver(() => {
        if (!removed && map) {
          map.resize();
          if (loaded.current && latest.current.geometry) fitOhio(map, latest.current.geometry);
        }
      });
      observer.observe(container.current);
      timer = setTimeout(fail, 30_000);
    } catch {
      fail();
    }
    return remove;
  }, [available, retry]);
  return (
    <div className="county-map-panel">
      {!failed && available && (
        <button
          className="fit-ohio"
          onClick={() => {
            if (mapRef.current && props.geometry) fitOhio(mapRef.current, props.geometry);
          }}
        >
          Fit Ohio
        </button>
      )}
      {failed && (
        <div className="notice" role="status">
          <p>Interactive map unavailable. Use the county selector and table below.</p>
          <button
            onClick={() => {
              setFailed(false);
              setRendering(true);
              setRetry((n) => n + 1);
            }}
          >
            Retry interactive map
          </button>
        </div>
      )}
      {!failed && available && rendering && <p role="status">Preparing interactive map…</p>}
      <div
        ref={container}
        className="county-map"
        role="region"
        aria-label="Ohio county interactive map; county selector and table provide an alternative"
        hidden={failed || !available}
      />
    </div>
  );
}
