import { useCallback, useEffect, useReducer, useRef, useState } from 'react';
import {
  ApiFailure,
  type Flag,
  type ReleaseSummary,
  type RollupPage,
  type Selection,
} from '../../api/types';
import { fetchReleases } from '../../api/releases';
import { fetchCountySummary, matchesSummary } from '../../api/rollups';

type ExplorationState = {
  releases: ReleaseSummary[];
  catalogError?: ApiFailure;
  selection: Selection | null;
  selectionRequired: boolean;
};
type ExplorationAction =
  | { type: 'catalog-success'; releases: ReleaseSummary[] }
  | { type: 'catalog-error'; error: ApiFailure }
  | { type: 'select-release'; release: ReleaseSummary }
  | { type: 'select-flag'; flag: Flag };
type Readiness = {
  key: string;
  catalogKey: string;
  kind: 'loading' | 'ready' | 'empty' | 'ohio-absent' | 'failed';
  summaryCoverage?: RollupPage['summary_coverage'];
  boundaryVintage?: number | null;
  loadedStates?: string[];
  error?: ApiFailure;
};
const keyOf = (r: ReleaseSummary, flag: Flag) => `${r.as_of}|${r.processed_on}|39|${flag}|`;
function reducer(state: ExplorationState, action: ExplorationAction): ExplorationState {
  if (action.type === 'catalog-success') {
    const { releases } = action;
    if (!state.selection && !state.selectionRequired) {
      const first = releases[0];
      return {
        ...state,
        releases,
        catalogError: undefined,
        selection: first
          ? {
              as_of: first.as_of,
              processed_on: first.processed_on,
              state: '39',
              flag: 'wired',
              county: null,
            }
          : null,
      };
    }
    const selected = state.selection;
    const stillLoaded = selected
      ? releases.some((r) => r.as_of === selected.as_of && r.processed_on === selected.processed_on)
      : true;
    return {
      ...state,
      releases,
      catalogError: undefined,
      ...(!stillLoaded && state.selection ? { selection: null, selectionRequired: true } : {}),
    };
  } else if (action.type === 'catalog-error')
    return { ...state, releases: [], catalogError: action.error };
  else if (action.type === 'select-release')
    return {
      ...state,
      selectionRequired: false,
      selection: {
        as_of: action.release.as_of,
        processed_on: action.release.processed_on,
        state: '39',
        flag: state.selection?.flag ?? 'wired',
        county: state.selection?.county ?? null,
      },
    };
  else
    return {
      ...state,
      selection: state.selection ? { ...state.selection, flag: action.flag } : null,
    };
}

export function useExploration(active: boolean, activationKey: number) {
  const [state, dispatch] = useReducer(reducer, {
    releases: [],
    selection: null,
    selectionRequired: false,
  });
  const [refreshId, setRefreshId] = useState(0);
  const [settledCatalogKey, setSettledCatalogKey] = useState<string | null>(null);
  const [readiness, setReadiness] = useState<Readiness | null>(null);
  const [settled404, setSettled404] = useState<{ key: string; error: ApiFailure } | null>(null);
  const catalogGeneration = useRef(0);
  const summaryGeneration = useRef(0);
  const refresh = useCallback(() => {
    setReadiness(null);
    setSettled404(null);
    setRefreshId((n) => n + 1);
  }, []);
  const requestKey = `${String(activationKey)}:${String(refreshId)}`;
  const catalogLoading = active && settledCatalogKey !== requestKey;

  useEffect(() => {
    if (!active) return;
    const generation = catalogGeneration.current + 1;
    catalogGeneration.current = generation;
    const controller = new AbortController();
    void fetchReleases(controller.signal)
      .then((releases) => {
        if (controller.signal.aborted || generation !== catalogGeneration.current) return;
        dispatch({ type: 'catalog-success', releases });
        setSettledCatalogKey(requestKey);
      })
      .catch((error: unknown) => {
        if (
          controller.signal.aborted ||
          generation !== catalogGeneration.current ||
          (error instanceof ApiFailure && error.kind === 'cancelled')
        )
          return;
        dispatch({
          type: 'catalog-error',
          error:
            error instanceof ApiFailure
              ? error
              : new ApiFailure('network', 'The release list could not be reached.'),
        });
        setSettledCatalogKey(requestKey);
      });
    return () => {
      controller.abort();
      if (catalogGeneration.current === generation) catalogGeneration.current = generation + 1;
    };
  }, [active, requestKey]);

  const { selection } = state;
  const selectedRelease = selection
    ? (state.releases.find(
        (r) => r.as_of === selection.as_of && r.processed_on === selection.processed_on,
      ) ?? null)
    : null;
  const hasOhio = Boolean(selectedRelease?.states.some((s) => s.code === '39'));
  const currentKey = selectedRelease && selection ? keyOf(selectedRelease, selection.flag) : '';
  useEffect(() => {
    const generation = summaryGeneration.current + 1;
    summaryGeneration.current = generation;
    if (!active || catalogLoading || !selectedRelease || !hasOhio || !selection) return;
    const controller = new AbortController();
    const key = keyOf(selectedRelease, selection.flag);
    if (settled404?.key === key)
      return () => {
        controller.abort();
        summaryGeneration.current = summaryGeneration.current + 1;
      };
    const catalogKey = requestKey;
    void fetchCountySummary(selectedRelease, selection.flag, controller.signal)
      .then((page) => {
        if (controller.signal.aborted || generation !== summaryGeneration.current) return;
        if (!matchesSummary(page, selectedRelease, selection.flag))
          throw new ApiFailure(
            'unexpected',
            'The county summary response did not match the selected release and flag.',
          );
        const loadedStates = page.release.states.map((state) => `${state.name} (${state.code})`);
        const ohioLoaded = page.release.states.some((state) => state.code === '39');
        setReadiness({
          kind: !ohioLoaded ? 'ohio-absent' : page.results.length ? 'ready' : 'empty',
          key,
          catalogKey,
          summaryCoverage: page.summary_coverage,
          boundaryVintage: page.boundary_vintage,
          loadedStates,
        });
      })
      .catch((error: unknown) => {
        if (
          controller.signal.aborted ||
          generation !== summaryGeneration.current ||
          (error instanceof ApiFailure && error.kind === 'cancelled')
        )
          return;
        const failure =
          error instanceof ApiFailure
            ? error
            : new ApiFailure('network', 'County summaries could not be reached.');
        if (failure.status === 404) {
          setSettled404({ key, error: failure });
          setRefreshId((n) => n + 1);
          return;
        }
        setReadiness({ kind: 'failed', key, catalogKey, error: failure });
      });
    return () => {
      controller.abort();
      if (summaryGeneration.current === generation) summaryGeneration.current = generation + 1;
    };
  }, [
    active,
    catalogLoading,
    currentKey,
    settled404,
    selectedRelease,
    selection,
    hasOhio,
    requestKey,
  ]);

  const selectRelease = (release: ReleaseSummary) => {
    setReadiness(null);
    setSettled404(null);
    dispatch({ type: 'select-release', release });
  };
  const selectFlag = (flag: Flag) => {
    setReadiness(null);
    setSettled404(null);
    dispatch({ type: 'select-flag', flag });
  };
  let currentReadiness: Readiness | null = null;
  if (active && !catalogLoading && currentKey) {
    // A fresh 404 must take precedence over a result retained from an earlier visit.
    if (settled404?.key === currentKey) {
      currentReadiness = {
        kind: 'failed',
        key: currentKey,
        catalogKey: requestKey,
        error: settled404.error,
      };
    } else if (readiness?.key === currentKey && readiness.catalogKey === requestKey) {
      currentReadiness = readiness;
    } else {
      currentReadiness = { kind: 'loading', key: currentKey, catalogKey: requestKey };
    }
  }
  return {
    catalog: { releases: state.releases, error: state.catalogError, loading: catalogLoading },
    selection,
    selectedRelease,
    hasOhio,
    selectionRequired: state.selectionRequired,
    readiness: currentReadiness,
    selectRelease,
    selectFlag,
    refresh,
  };
}
