import { type CountyView, formatCount, formatShare } from './join';
export function CountyTable({
  rows,
  ready,
  county,
  select,
}: {
  rows: CountyView[];
  ready: boolean;
  county: string | null;
  select: (code: string) => void;
}) {
  return (
    <div
      className="county-table-scroll"
      role="region"
      aria-label="County summary table"
      tabIndex={0}
    >
      <table>
        <caption>Ohio county Served / Not served (100/20 Mbps) summaries</caption>
        <thead>
          <tr>
            {[
              'County',
              'GEOID',
              'Locations',
              'Served',
              'Not served',
              'Served share',
              'Selection',
            ].map((h) => (
              <th key={h} scope="col">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.code} aria-selected={county === row.code}>
              <th scope="row">
                {row.name}
                {!row.boundary && <small>Boundary unavailable</small>}
              </th>
              <td>{row.code}</td>
              {ready && row.kind === 'observed' ? (
                <>
                  <td>{formatCount(row.summary.locations)}</td>
                  <td>{formatCount(row.summary.served)}</td>
                  <td>{formatCount(row.summary.not_served)}</td>
                  <td>{formatShare(row.summary.served, row.summary.locations)}</td>
                </>
              ) : (
                <td colSpan={4}>{ready ? 'No summary observation' : 'Loading or unavailable'}</td>
              )}
              <td>
                <button
                  onClick={() => {
                    select(row.code);
                  }}
                  aria-pressed={county === row.code}
                >
                  Select {row.name}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
