import { ApiFailure, type Problem, type ProblemField } from './types';

const TIMEOUT_MS = 30_000;
const requestIdPattern = /^[0-9a-f]{32}$/i;
const record = (v: unknown): v is Record<string, unknown> =>
  typeof v === 'object' && v !== null && !Array.isArray(v);
const str = (v: unknown): v is string => typeof v === 'string';

export function isIsoDate(value: unknown): value is string {
  if (!str(value) || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const date = new Date(`${value}T00:00:00.000Z`);
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === value;
}
export function asRecord(value: unknown): Record<string, unknown> {
  if (!record(value))
    throw new ApiFailure('unexpected', 'The API returned an unexpected response.');
  return value;
}
export function requiredCount(v: unknown): v is number {
  return Number.isSafeInteger(v) && (v as number) >= 0;
}
export function nullableLink(v: unknown): v is string | null {
  return v === null || (str(v) && v.length > 0);
}

function parseProblem(v: unknown, status: number): Problem | undefined {
  if (
    !record(v) ||
    v.status !== status ||
    !str(v.type) ||
    !str(v.title) ||
    !str(v.detail) ||
    !str(v.code) ||
    !str(v.request_id)
  )
    return;
  let errors: ProblemField[] | undefined;
  if ('errors' in v) {
    if (
      !Array.isArray(v.errors) ||
      !v.errors.every((e) => record(e) && str(e.pointer) && str(e.code) && str(e.message))
    )
      return;
    errors = v.errors as ProblemField[];
  }
  return {
    type: v.type,
    title: v.title,
    status,
    detail: v.detail,
    code: v.code,
    request_id: v.request_id,
    ...(errors ? { errors } : {}),
  };
}

function safeMessage(body: unknown, response: Response, contentType: string): ApiFailure {
  const headerId = response.headers.get('X-Request-ID');
  const headerValid = headerId && requestIdPattern.test(headerId) ? headerId : undefined;
  if (contentType === 'application/problem+json') {
    const problem = parseProblem(body, response.status);
    if (problem)
      return new ApiFailure(
        'problem',
        problem.detail,
        response.status,
        problem,
        headerValid ?? (requestIdPattern.test(problem.request_id) ? problem.request_id : undefined),
      );
  }
  return new ApiFailure(
    'http',
    `The API request failed (HTTP ${String(response.status)}).`,
    response.status,
    undefined,
    headerValid,
  );
}

export function resolvePageUrl(
  link: string,
  endpoint: string,
  base = window.location.origin,
): string {
  let endpointUrl: URL, target: URL;
  try {
    endpointUrl = new URL(endpoint, base);
    target = new URL(link, endpointUrl);
  } catch {
    throw new ApiFailure('unexpected', 'The API returned an unsafe pagination link.');
  }
  const endpointPath = endpointUrl.pathname;
  const rawPath = target.pathname;
  const inputPath = link.replace(/^[a-z][a-z0-9+.-]*:\/\/[^/?#]*/i, '').split(/[?#]/, 1)[0] ?? '';
  let decodedSegments: string[];
  try {
    decodedSegments = inputPath.split('/').map((part) => decodeURIComponent(part));
  } catch {
    throw new ApiFailure('unexpected', 'The API returned an unsafe pagination link.');
  }
  if (
    !['http:', 'https:'].includes(target.protocol) ||
    target.origin !== endpointUrl.origin ||
    target.pathname !== endpointPath ||
    target.username ||
    target.password ||
    target.hash ||
    /%2f|%5c/i.test(inputPath) ||
    decodedSegments.some((part) => part === '.' || part === '..') ||
    rawPath !== endpointPath ||
    (inputPath !== '' && inputPath.replace(/\/$/, '') !== endpointPath.replace(/\/$/, ''))
  ) {
    throw new ApiFailure('unexpected', 'The API returned an unsafe pagination link.');
  }
  return `${target.origin}${target.pathname}${target.search}`;
}

export async function getJson<T>(
  url: string,
  decoder: (body: unknown) => T,
  callerSignal?: AbortSignal,
): Promise<T> {
  let requestUrl: URL;
  try {
    requestUrl = new URL(url, window.location.origin);
  } catch {
    throw new ApiFailure('unexpected', 'The API request URL is invalid.');
  }
  if (
    requestUrl.origin !== window.location.origin ||
    !requestUrl.pathname.startsWith('/api/') ||
    requestUrl.username ||
    requestUrl.password ||
    requestUrl.hash
  )
    throw new ApiFailure('unexpected', 'The API request URL is outside this application.');
  const controller = new AbortController();
  const abortCaller = () => {
    controller.abort();
  };
  if (callerSignal?.aborted) throw new ApiFailure('cancelled', 'The request was cancelled.');
  callerSignal?.addEventListener('abort', abortCaller, { once: true });
  const transport = (async () => {
    const response = await fetch(requestUrl.href, {
      method: 'GET',
      cache: 'no-store',
      credentials: 'same-origin',
      redirect: 'error',
      signal: controller.signal,
      headers: { Accept: 'application/json, application/geo+json, application/problem+json' },
    });
    const type = ((response.headers.get('Content-Type') ?? '').split(';', 1)[0] ?? '')
      .trim()
      .toLowerCase();
    const headerId = response.headers.get('X-Request-ID');
    const requestId = headerId && requestIdPattern.test(headerId) ? headerId : undefined;
    if (!response.ok) {
      let body: unknown;
      if (type === 'application/problem+json') {
        try {
          body = await response.json();
        } catch {
          body = undefined;
        }
      }
      throw safeMessage(body, response, type);
    }
    if (type !== 'application/json' && type !== 'application/geo+json')
      throw new ApiFailure(
        'unexpected',
        'The API returned an unexpected content type.',
        response.status,
        undefined,
        requestId,
      );
    let body: unknown;
    try {
      body = await response.json();
    } catch {
      throw new ApiFailure(
        'unexpected',
        'The API returned invalid JSON.',
        response.status,
        undefined,
        requestId,
      );
    }
    try {
      return decoder(body);
    } catch (error) {
      if (error instanceof ApiFailure && !error.requestId) error.requestId = requestId;
      throw error;
    }
  })();
  // Attach a rejection handler immediately so ignored-abort transports cannot leak an unhandled rejection.
  const settledTransport = transport.catch((e: unknown) => {
    throw e instanceof ApiFailure ? e : new ApiFailure('network', 'The API could not be reached.');
  });
  let onCallerAbort: (() => void) | undefined;
  let rejectTimeout: (reason: ApiFailure) => void = () => {};
  const timeoutPromise = new Promise<never>((_, reject) => {
    rejectTimeout = reject;
  });
  const timer = setTimeout(() => {
    controller.abort();
    rejectTimeout(new ApiFailure('timeout', 'The request timed out.'));
  }, TIMEOUT_MS);
  try {
    return await Promise.race([
      settledTransport,
      timeoutPromise,
      ...(callerSignal
        ? [
            new Promise<never>((_, reject) => {
              onCallerAbort = () => {
                reject(new ApiFailure('cancelled', 'The request was cancelled.'));
              };
              callerSignal.addEventListener('abort', onCallerAbort, { once: true });
            }),
          ]
        : []),
    ]);
  } finally {
    clearTimeout(timer);
    if (onCallerAbort) callerSignal?.removeEventListener('abort', onCallerAbort);
    callerSignal?.removeEventListener('abort', abortCaller);
  }
}
