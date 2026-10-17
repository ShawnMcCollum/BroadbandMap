import { useEffect, useRef, useState } from 'react';
import { fetchCounties } from '../../api/counties';
import { ApiFailure, type CountyCollection, type LoadState } from '../../api/types';

export function useCountyGeometry(enabled: boolean, refreshVersion: number) {
  const [retryId, setRetryId] = useState(0);
  const [settled, setSettled] = useState<{
    key: string;
    state: LoadState<CountyCollection>;
  } | null>(null);
  const [geometry, setGeometry] = useState<CountyCollection | null>(null);
  const generation = useRef(0);
  const completed = useRef<string | null>(null);
  const key = `${String(refreshVersion)}:${String(retryId)}`;
  useEffect(() => {
    if (!enabled || completed.current === key) return;
    const id = ++generation.current,
      controller = new AbortController();
    void fetchCounties('39', controller.signal)
      .then((data) => {
        if (controller.signal.aborted || id !== generation.current) return;
        completed.current = key;
        setGeometry(data);
        setSettled({ key, state: { kind: 'ready', data } });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted || id !== generation.current) return;
        setSettled({
          key,
          state: {
            kind: 'failed',
            error:
              error instanceof ApiFailure
                ? error
                : new ApiFailure('network', 'County boundaries could not be reached.'),
          },
        });
      });
    return () => {
      controller.abort();
      if (generation.current === id) generation.current = id + 1;
    };
  }, [enabled, key]);
  return {
    geometry,
    state: settled?.key === key ? settled.state : { kind: 'loading' as const },
    retry: () => {
      setRetryId((n) => n + 1);
    },
  };
}
