import type { Flag, LoadState, ReleaseSummary, RollupPage } from '../../api/types';
import { type CountyView, formatCount, formatShare } from './join';
export function CountyDetail({
  county,
  ready,
  release,
  flag,
  diagnosis,
  retry,
  refresh,
}: {
  county: CountyView | undefined;
  ready: boolean;
  release: ReleaseSummary | null;
  flag: Flag;
  diagnosis: LoadState<RollupPage>;
  retry: () => void;
  refresh: () => void;
}) {
  return (
    <section
      className="county-detail"
      aria-labelledby="county-detail-title"
      aria-live="polite"
      aria-atomic="true"
    >
      <h2 id="county-detail-title">County detail</h2>
      {!county ? (
        <p>Select a county to see its detail.</p>
      ) : (
        <>
          <h3>{county.name}</h3>
          <p>GEOID: {county.code}</p>
          {!ready ? (
            <p>Current county values are loading or unavailable.</p>
          ) : county.kind === 'observed' ? (
            <dl>
              <dt>Locations</dt>
              <dd>{formatCount(county.summary.locations)}</dd>
              <dt>Served</dt>
              <dd>{formatCount(county.summary.served)}</dd>
              <dt>Not served</dt>
              <dd>{formatCount(county.summary.not_served)}</dd>
              <dt>Served share</dt>
              <dd>{formatShare(county.summary.served, county.summary.locations)}</dd>
            </dl>
          ) : (
            <>
              <p>No summary observation.</p>
              {diagnosis.kind === 'loading' && <p>Checking county coverage…</p>}
              {diagnosis.kind === 'failed' && (
                <div className="error">
                  <p>
                    {diagnosis.error.status === 503
                      ? 'County summaries are unavailable. An application operator may need to rebuild them.'
                      : diagnosis.error.message}
                  </p>
                  {diagnosis.error.requestId && <p>Request ID: {diagnosis.error.requestId}</p>}
                  <button onClick={retry}>Retry county detail</button>
                </div>
              )}
              {diagnosis.kind === 'ready' &&
                (diagnosis.data.summary_coverage === 'observed' ? (
                  <>
                    <p>County summaries changed. Refresh to update the map and table.</p>
                    <button onClick={refresh}>Refresh county summaries</button>
                  </>
                ) : (
                  <p>
                    {diagnosis.data.summary_coverage === 'no_observations'
                      ? 'No locations were observed in this area for this release.'
                      : 'This area is outside the loaded coverage of this release.'}
                  </p>
                ))}
            </>
          )}
          {release && (
            <p className="help">
              {flag} · {release.filing_period}; data period {release.as_of}; processed{' '}
              {release.processed_on}
            </p>
          )}
        </>
      )}
    </section>
  );
}
