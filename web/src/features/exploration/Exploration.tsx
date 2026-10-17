import type { Flag, ReleaseSummary } from '../../api/types';
import type { useExploration } from './useExploration';

type Model = ReturnType<typeof useExploration>;
const flags: { value: Flag; label: string; source: string }[] = [
  { value: 'wired', label: 'Wired', source: 'wired_100_20' },
  { value: 'any', label: 'Any technology', source: 'any_100_20' },
  { value: 'terrestrial', label: 'Terrestrial', source: 'terrestrial_100_20' },
];
const releaseName = (r: ReleaseSummary) =>
  `${r.filing_period} · ${r.as_of} · processed ${r.processed_on}`;

export function Exploration({ model }: { model: Model }) {
  const { catalog, selection, selectedRelease, hasOhio, readiness } = model;
  const selectedFlag = selection?.flag ?? 'wired';
  const loadedStates =
    readiness?.loadedStates ?? selectedRelease?.states.map((s) => `${s.name} (${s.code})`) ?? [];
  const fieldErrors = readiness?.kind === 'failed' ? (readiness.error?.problem?.errors ?? []) : [];
  const releaseError = fieldErrors.filter(
    (e) => e.pointer === '/as_of' || e.pointer === '/processed_on',
  );
  const flagError = fieldErrors.filter((e) => e.pointer === '/flag');
  return (
    <section aria-labelledby="map-title">
      <h1 id="map-title" tabIndex={-1}>
        Ohio broadband map
      </h1>
      <p>Explore the selected 100 Mbps download / 20 Mbps upload service flag by county.</p>
      {catalog.loading && <p role="status">Loading releases…</p>}
      {!catalog.loading && catalog.error && (
        <div className="error" role="alert">
          <ErrorBox text="Could not load releases." error={catalog.error} retry={model.refresh} />
        </div>
      )}
      {!catalog.loading && !catalog.error && catalog.releases.length === 0 && (
        <div className="notice">
          <p>
            No data releases are loaded. Follow the README data-load instructions, then refresh.
          </p>
          <a href="https://github.com/ShawnMcCollum/BroadbandMap#load-the-ohio-data">
            README data-load instructions
          </a>{' '}
          <button
            onClick={() => {
              model.refresh();
            }}
          >
            Refresh
          </button>
        </div>
      )}
      {catalog.releases.length > 0 && (
        <>
          {model.selectionRequired && (
            <p role="status">This release is no longer loaded. Choose a release.</p>
          )}
          <div className="controls">
            <div>
              <label htmlFor="release">FCC data release</label>
              <select
                id="release"
                aria-invalid={releaseError.length > 0}
                aria-describedby={`release-help${releaseError.length ? ' release-error' : ''}`}
                value={
                  selectedRelease ? `${selectedRelease.as_of}|${selectedRelease.processed_on}` : ''
                }
                onChange={(e) => {
                  const r = catalog.releases.find(
                    (x) => `${x.as_of}|${x.processed_on}` === e.target.value,
                  );
                  if (r) model.selectRelease(r);
                }}
              >
                {!selectedRelease && <option value="">Choose a release</option>}
                {catalog.releases.map((r) => (
                  <option
                    key={`${r.as_of}|${r.processed_on}`}
                    value={`${r.as_of}|${r.processed_on}`}
                  >
                    {releaseName(r)}
                  </option>
                ))}
              </select>
              {selectedRelease && (
                <p className="help">
                  {selectedRelease.filing_period}; data period {selectedRelease.as_of}; processed{' '}
                  {selectedRelease.processed_on}
                </p>
              )}
              <p id="release-help" className="help">
                {selectedRelease
                  ? `Loaded states: ${loadedStates.join(', ') || 'none'}. Source: FCC National Broadband Map.`
                  : 'Choose a loaded data period and processing date.'}
              </p>
              {releaseError.length > 0 && (
                <p id="release-error" className="error-text">
                  {releaseError.map((e) => e.message).join(' ')}
                </p>
              )}
            </div>
            <div>
              <label htmlFor="flag">Technology flag</label>
              <select
                id="flag"
                aria-invalid={flagError.length > 0}
                aria-describedby={`flag-help${flagError.length ? ' flag-error' : ''}`}
                value={selectedFlag}
                disabled={!selection}
                onChange={(e) => {
                  model.selectFlag(e.target.value as Flag);
                }}
              >
                {flags.map((f) => (
                  <option key={f.value} value={f.value}>
                    {f.label}
                  </option>
                ))}
              </select>
              <p id="flag-help" className="help">
                Uses source field {flags.find((f) => f.value === selectedFlag)?.source}. Not served
                means this 100/20 flag is false, not a separate regulatory classification.
              </p>
              {flagError.length > 0 && (
                <p id="flag-error" className="error-text">
                  {flagError.map((e) => e.message).join(' ')}
                </p>
              )}
            </div>
          </div>
          <button
            onClick={() => {
              model.refresh();
            }}
          >
            Refresh
          </button>
          <p>State: Ohio. County boundaries: Census TIGER/Line 2020.</p>
          {!catalog.loading && selectedRelease && !hasOhio && (
            <p role="status">Ohio is not loaded for this release.</p>
          )}
          {hasOhio && !catalog.loading && (
            <SummaryStatus readiness={readiness} retry={model.refresh} />
          )}
        </>
      )}
    </section>
  );
}

function SummaryStatus({ readiness, retry }: { readiness: Model['readiness']; retry: () => void }) {
  if (!readiness || readiness.kind === 'loading')
    return <p role="status">Checking county summaries…</p>;
  if (readiness.kind === 'ohio-absent')
    return (
      <p role="status">
        Ohio is not loaded for this release. Loaded states:{' '}
        {readiness.loadedStates?.join(', ') || 'none'}.
      </p>
    );
  if (readiness.kind === 'ready')
    return (
      <div role="status">
        <p>County summary API responded for this selection.</p>
        <p>The county map and table will arrive in #73.</p>
        <p>
          {coverageText(readiness.summaryCoverage)} The bounded first page does not establish
          all-county completeness.
        </p>
      </div>
    );
  if (readiness.kind === 'empty')
    return (
      <div role="status">
        <p>No county summary rows were returned for this selection.</p>
        <p>{coverageText(readiness.summaryCoverage)}</p>
      </div>
    );
  const unavailable = readiness.error?.status === 503;
  const text = unavailable
    ? 'County summaries are unavailable. Try refreshing; an application operator may need to rebuild them.'
    : 'Could not check county summaries.';
  return (
    <div className="error" role="alert">
      <p>{text}</p>
      <ErrorBox text="" error={readiness.error} retry={retry} associatedFields />
    </div>
  );
}

function coverageText(coverage: string | undefined) {
  switch (coverage) {
    case 'stored_rollups_only':
      return 'Stored county summaries are available.';
    case 'observed':
      return 'The API reports observed summary coverage.';
    case 'no_observations':
      return 'The API reports no observations for this selection.';
    case 'outside_release_coverage':
      return 'This selection is outside the release coverage.';
    default:
      return 'The API returned coverage metadata.';
  }
}

function ErrorBox({
  text,
  error,
  retry,
  associatedFields = false,
}: {
  text: string;
  error?: {
    message: string;
    requestId?: string;
    problem?: { errors?: { pointer: string; message: string }[] };
  };
  retry: () => void;
  associatedFields?: boolean;
}) {
  const globalErrors = error?.problem?.errors?.filter(
    (e) => !associatedFields || !['/flag', '/as_of', '/processed_on'].includes(e.pointer),
  );
  return (
    <div>
      {text && <p>{text}</p>}
      {globalErrors?.length ? (
        <ul>
          {globalErrors.map((e, i) => (
            <li key={`${e.pointer}-${String(i)}`}>
              {e.pointer || 'Request'}: {e.message}
            </li>
          ))}
        </ul>
      ) : (
        !error?.problem?.errors?.length && error?.message && <p>{error.message}</p>
      )}
      {error?.requestId && <p>Request ID: {error.requestId}</p>}
      <button onClick={retry}>Retry</button>
    </div>
  );
}
