export const COMPONENTS = ['database', 'redis', 'worker'] as const;

export type Component = (typeof COMPONENTS)[number];

export type Health = { status: 'ok' | 'error' } & Record<Component, 'ok' | 'unreachable'>;

/** Fetch the backend health report. Throws if the API cannot be reached. */
export async function fetchHealth(signal?: AbortSignal): Promise<Health> {
  const response = await fetch('/api/health/', { signal });
  // A 503 still carries a health report in its body.
  if (!response.ok && response.status !== 503) {
    throw new Error(`Health check failed with HTTP ${String(response.status)}`);
  }
  return (await response.json()) as Health;
}
