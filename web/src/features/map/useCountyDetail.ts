import { useEffect, useRef, useState } from 'react';
import { fetchCountySummaryByCode } from '../../api/rollups';
import {
  ApiFailure,
  type Flag,
  type LoadState,
  type ReleaseSummary,
  type RollupPage,
} from '../../api/types';
export function useCountyDetail(
  release: ReleaseSummary | null,
  flag: Flag,
  code: string | null,
  version: string,
  rediscover: () => void,
) {
  const [retryId, setRetryId] = useState(0);
  const [result, setResult] = useState<{ key: string; state: LoadState<RollupPage> } | null>(null);
  const generation = useRef(0);
  const recovered = useRef('');
  const key = `${release?.as_of ?? ''}|${release?.processed_on ?? ''}|${flag}|${code ?? ''}|${version}|${String(retryId)}`;
  useEffect(() => {
    if (!release || !code) return;
    const id = ++generation.current,
      controller = new AbortController();
    void fetchCountySummaryByCode(release, flag, code, controller.signal)
      .then((data) => {
        if (!controller.signal.aborted && id === generation.current)
          setResult({ key, state: { kind: 'ready', data } });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted || id !== generation.current) return;
        const failure =
          error instanceof ApiFailure
            ? error
            : new ApiFailure('network', 'County detail could not be reached.');
        setResult({ key, state: { kind: 'failed', error: failure } });
        const recoveryKey = `${release.as_of}|${release.processed_on}|${flag}|${code}`;
        if (failure.status === 404 && recovered.current !== recoveryKey) {
          recovered.current = recoveryKey;
          rediscover();
        }
      });
    return () => {
      controller.abort();
      if (generation.current === id) generation.current = id + 1;
    };
  }, [release, flag, code, key, rediscover]);
  return {
    state: result?.key === key ? result.state : { kind: 'loading' as const },
    retry: () => {
      setRetryId((n) => n + 1);
    },
  };
}
