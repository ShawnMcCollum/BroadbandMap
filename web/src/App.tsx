import { useEffect, useState } from 'react';

import { COMPONENTS, fetchHealth, type Health } from './health';

type State = { kind: 'loading' } | { kind: 'loaded'; health: Health } | { kind: 'failed' };

const LABELS = { database: 'PostGIS', redis: 'Redis', worker: 'Celery worker' } as const;

export function App() {
  const [state, setState] = useState<State>({ kind: 'loading' });

  useEffect(() => {
    const controller = new AbortController();
    fetchHealth(controller.signal)
      .then((health) => {
        setState({ kind: 'loaded', health });
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          console.error(error);
          setState({ kind: 'failed' });
        }
      });
    return () => {
      controller.abort();
    };
  }, []);

  return (
    <main>
      <h1>BroadbandMap: stack check</h1>
      {state.kind === 'loading' && <p>Checking the API…</p>}
      {state.kind === 'failed' && <p>✗ The API cannot be reached.</p>}
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
    </main>
  );
}
