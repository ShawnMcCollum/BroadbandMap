import { useEffect, useRef, useState } from 'react';
import { routeFromHash, type Route } from './navigation';
import { dashboardDestination } from './navigation';
import { useExploration } from './features/exploration/useExploration';
import { Exploration } from './features/exploration/Exploration';
import { Diagnostics } from './features/diagnostics/Diagnostics';

const titles: Record<Route, string> = {
  map: 'Ohio broadband map | BroadbandMap',
  ask: 'Ask (stub) | BroadbandMap',
  'settings/ai': 'AI settings | BroadbandMap',
  diagnostics: 'Diagnostics | BroadbandMap',
  unknown: 'Page not found | BroadbandMap',
};

export function App() {
  const [route, setRoute] = useState<Route>(() => routeFromHash(window.location.hash));
  const [mapActivation, setMapActivation] = useState(0);
  const model = useExploration(route === 'map', mapActivation);
  const dashboard = dashboardDestination();
  useEffect(() => {
    const onHash = () => {
      const next = routeFromHash(window.location.hash);
      setRoute(next);
      if (next === 'map') setMapActivation((n) => n + 1);
    };
    window.addEventListener('hashchange', onHash);
    return () => {
      window.removeEventListener('hashchange', onHash);
    };
  }, []);
  useEffect(() => {
    document.title = titles[route];
  }, [route]);
  const priorRoute = useRef<Route | null>(null);
  useEffect(() => {
    if (priorRoute.current !== null && priorRoute.current !== route)
      document.querySelector<HTMLElement>('main h1')?.focus();
    priorRoute.current = route;
  }, [route]);
  return (
    <>
      <a
        className="skip-link"
        href="#main"
        onClick={(event) => {
          event.preventDefault();
          document.getElementById('main')?.focus();
        }}
      >
        Skip to main content
      </a>
      <header className="site-header">
        <a className="brand" href="#/map">
          BroadbandMap
        </a>
        <nav aria-label="Main navigation">
          <a href="#/map" aria-current={route === 'map' ? 'page' : undefined}>
            Map
          </a>
          {dashboard.valid && dashboard.url ? (
            <span className="external-nav">
              <a href={dashboard.url}>Analyst dashboard</a>
              <small>Opens the other app with default filters.</small>
            </span>
          ) : (
            <span className="nav-invalid">
              Analyst dashboard link unavailable. Configure VITE_DASHBOARD_URL with a
              browser-reachable HTTP(S) base URL without credentials, query, or hash.
            </span>
          )}
          <a href="#/ask" aria-current={route === 'ask' ? 'page' : undefined}>
            Ask (stub)
          </a>
          <a href="#/settings/ai" aria-current={route === 'settings/ai' ? 'page' : undefined}>
            AI settings
          </a>
        </nav>
      </header>
      <main id="main" tabIndex={-1}>
        {route === 'map' && <Exploration model={model} />}
        {route === 'ask' && (
          <section>
            <h1 tabIndex={-1}>Ask (stub)</h1>
            <p>
              The question panel is not available yet. See the planned work in{' '}
              <a href="https://github.com/ShawnMcCollum/BroadbandMap/issues/77">#77</a>.
            </p>
          </section>
        )}
        {route === 'settings/ai' && (
          <section>
            <h1 tabIndex={-1}>AI settings</h1>
            <p>
              AI settings are not available yet. See the planned work in{' '}
              <a href="https://github.com/ShawnMcCollum/BroadbandMap/issues/76">#76</a>.
            </p>
          </section>
        )}
        {route === 'diagnostics' && <Diagnostics active />}
        {route === 'unknown' && (
          <section>
            <h1 tabIndex={-1}>Page not found</h1>
            <p>This page is not part of BroadbandMap.</p>
            <a href="#/map">Return to the map</a>
          </section>
        )}
      </main>
      <footer>
        <a href="#/diagnostics" aria-current={route === 'diagnostics' ? 'page' : undefined}>
          Diagnostics
        </a>
      </footer>
    </>
  );
}
