import { useEffect, useRef, useState } from 'react';
import { COMPONENTS, fetchHealth, type Health } from '../../health';

type State = { kind: 'loading' } | { kind: 'loaded'; health: Health } | { kind: 'failed' };
const LABELS = { database: 'PostGIS', redis: 'Redis', worker: 'Celery worker' } as const;
export function Diagnostics({ active }: { active: boolean }) {
  const [state, setState] = useState<State>({ kind: 'loading' });
  const [retry, setRetry] = useState(0);
  const identity = useRef(0);
  useEffect(() => {
    if (!active) return;
    const id = identity.current + 1;
    identity.current = id;
    const controller = new AbortController();
    fetchHealth(controller.signal)
      .then((health) => {
        if (!controller.signal.aborted && id === identity.current)
          setState({ kind: 'loaded', health });
      })
      .catch(() => {
        if (!controller.signal.aborted && id === identity.current) setState({ kind: 'failed' });
      });
    return () => {
      controller.abort();
      if (identity.current === id) identity.current = id + 1;
    };
  }, [active, retry]);
  return (
    <section>
      <h1 tabIndex={-1}>Diagnostics</h1>
      <p>Operational health of the API and its dependencies.</p>
      {state.kind === 'loading' && <p role="status">Checking the API…</p>}
      {state.kind === 'failed' && (
        <div role="alert">
          <p>✗ The API cannot be reached.</p>
          <button
            onClick={() => {
              setState({ kind: 'loading' });
              setRetry((n) => n + 1);
            }}
          >
            Retry
          </button>
        </div>
      )}
      {state.kind === 'loaded' && (
        <ul>
          <li>✓ API</li>
          {COMPONENTS.map((name) => (
            <li key={name}>
              {state.health[name] === 'ok' ? '✓' : '✗'} {LABELS[name]}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
