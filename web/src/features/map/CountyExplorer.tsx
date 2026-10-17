import { useEffect, useMemo, useState } from 'react';
import type { useExploration } from '../exploration/useExploration';
import { useCountyGeometry } from './useCountyGeometry';
import { useCountyDetail } from './useCountyDetail';
import { countyRows, formatShare } from './join';
import { bins } from './style';
import { CountyMap } from './CountyMap';
import { CountyTable } from './CountyTable';
import { CountyDetail } from './CountyDetail';

type Model = ReturnType<typeof useExploration>;
export function CountyExplorer({ model }: { model: Model }) {
  const { selection, selectedRelease, summaries, catalog } = model;
  const geometry = useCountyGeometry(!catalog.loading && model.hasOhio, model.refreshVersion);
  const [hover, setHover] = useState<{ code: string | null; version: string } | null>(null);
  const ready = Boolean(summaries && ['ready', 'empty'].includes(summaries.kind));
  const data = ready ? summaries?.data : undefined;
  const rows = useMemo(
    () => countyRows(geometry.geometry, data?.results ?? []),
    [geometry.geometry, data],
  );
  const county = rows.find((r) => r.code === selection?.county);
  const missingCode = ready && county?.kind === 'missing' && county.boundary ? county.code : null;
  const diagnosis = useCountyDetail(
    selectedRelease,
    selection?.flag ?? 'wired',
    missingCode,
    `${model.summaryVersion}:${summaries?.key ?? ''}`,
    model.rediscover,
  );
  const selectCounty = model.selectCounty;
  useEffect(() => {
    if (
      selection?.county &&
      geometry.state.kind === 'ready' &&
      ready &&
      !rows.some((r) => r.code === selection.county)
    )
      selectCounty(null);
  }, [selection?.county, geometry.state.kind, ready, rows, selectCounty]);
  const version = `${model.summaryVersion}:${summaries?.key ?? ''}:${summaries?.kind ?? ''}`;
  const preview = hover?.version === version ? rows.find((r) => r.code === hover.code) : undefined;
  const visible = Boolean(selectedRelease || geometry.geometry);
  return (
    <div className="county-explorer" hidden={!visible}>
      {model.hasOhio && !catalog.loading && (!summaries || summaries.kind === 'loading') && (
        <p role="status">Loading county summaries…</p>
      )}
      {summaries?.kind === 'failed' && (
        <div className="error" role="alert">
          <p>
            {summaries.error?.status === 503
              ? 'County summaries are unavailable. Try refreshing; an application operator may need to rebuild them.'
              : 'Could not load county summaries.'}
          </p>
          <p>{summaries.error?.message}</p>
          {summaries.error?.problem?.errors?.map((e, i) => (
            <p key={i}>
              {e.pointer || 'Request'}: {e.message}
            </p>
          ))}
          {summaries.error?.requestId && <p>Request ID: {summaries.error.requestId}</p>}
          <button onClick={model.retrySummaries}>Retry summaries</button>
        </div>
      )}
      {summaries?.kind === 'ohio-absent' && (
        <p role="status">
          Ohio is not loaded for this release. Loaded states:{' '}
          {summaries.loadedStates?.join(', ') || 'none'}.
        </p>
      )}
      {summaries?.kind === 'ready' && (
        <p role="status">County summaries loaded: {summaries.data?.count}.</p>
      )}
      {summaries?.kind === 'empty' && (
        <p role="status">
          No stored county summaries were returned. Select a county to check its coverage.
        </p>
      )}
      {visible && geometry.state.kind === 'loading' && (
        <p role="status">
          {geometry.geometry ? 'Refreshing county boundaries…' : 'Loading county boundaries…'}
        </p>
      )}
      {geometry.state.kind === 'failed' && (
        <div className="error" role="alert">
          <p>Could not load county boundaries.</p>
          <p>{geometry.state.error.message}</p>
          {geometry.state.error.requestId && <p>Request ID: {geometry.state.error.requestId}</p>}
          <button onClick={geometry.retry}>Retry boundaries</button>
        </div>
      )}
      {geometry.state.kind === 'ready' && !geometry.geometry?.features.length && (
        <p role="status">No county boundaries are available for Ohio.</p>
      )}
      <div className="county-selector">
        <label htmlFor="county">County</label>
        <select
          id="county"
          value={selection?.county ?? ''}
          disabled={!selection || !rows.length}
          onChange={(e) => {
            selectCounty(e.target.value || null);
          }}
        >
          <option value="">All counties</option>
          {rows.map((r) => (
            <option key={r.code} value={r.code}>
              {r.name} ({r.code})
            </option>
          ))}
        </select>
      </div>
      <div className="county-layout">
        <CountyDetail
          county={county}
          ready={ready}
          release={data?.release ?? selectedRelease}
          flag={selection?.flag ?? 'wired'}
          diagnosis={diagnosis.state}
          retry={diagnosis.retry}
          refresh={model.retrySummaries}
        />
        <CountyMap
          geometry={geometry.geometry}
          rows={rows}
          ready={ready}
          selected={selection?.county ?? null}
          onSelect={selectCounty}
          onHover={(code) => {
            setHover({ code, version });
          }}
        />
      </div>
      <section className="county-legend" aria-label="Served share legend">
        <h2>Served share (100/20 Mbps)</h2>
        <ul>
          {bins.map((bin) => (
            <li key={bin.label}>
              <span aria-hidden="true" style={{ background: bin.color }} />
              {bin.label}
            </li>
          ))}
          <li>
            <span className="missing-swatch" aria-hidden="true" />
            No summary observation
          </li>
        </ul>
        <p className="help">
          Gray boundaries during loading or failure have no current classification.
        </p>
      </section>
      <p className="county-preview">
        {preview
          ? `${preview.name}: ${ready && preview.kind === 'observed' ? `${formatShare(preview.summary.served, preview.summary.locations)} served` : 'current values unavailable'}`
          : 'Hover over a county for a preview, or use the county selector.'}
      </p>
      <p className="help">
        Source: <a href="https://broadbandmap.fcc.gov/">FCC National Broadband Map</a>. Boundaries:
        Census TIGER/Line 2020. Renderer: <a href="https://maplibre.org/">MapLibre</a> (
        <a href="/maplibre-LICENSE.txt">license</a>).{' '}
        {data?.release &&
          `${data.release.filing_period}; data period ${data.release.as_of}; processed ${data.release.processed_on}. Loaded states: ${data.release.states.map((s) => `${s.name} (${s.code})`).join(', ') || 'none'}.`}
      </p>
      <CountyTable
        rows={rows}
        ready={ready}
        county={selection?.county ?? null}
        select={selectCounty}
      />
    </div>
  );
}
