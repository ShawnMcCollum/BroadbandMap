export type Route = 'map' | 'ask' | 'settings/ai' | 'diagnostics' | 'unknown';
export function routeFromHash(hash: string): Route {
  const value = hash.replace(/^#/, '').replace(/\/$/, '');
  if (value === '' || value === '/map') return 'map';
  if (value === '/ask') return 'ask';
  if (value === '/settings/ai') return 'settings/ai';
  if (value === '/diagnostics') return 'diagnostics';
  return 'unknown';
}
export function hashForRoute(route: Exclude<Route, 'unknown'>): string {
  return `#/${route}`;
}
type ImportMetaWithDashboard = ImportMeta & { env: { VITE_DASHBOARD_URL?: string } };
export function dashboardDestination(
  configured: string | undefined = (import.meta as ImportMetaWithDashboard).env.VITE_DASHBOARD_URL,
): {
  url?: string;
  valid: boolean;
} {
  const value = configured || 'http://localhost:8501/';
  try {
    const url = new URL(value);
    if (
      !['http:', 'https:'].includes(url.protocol) ||
      url.username ||
      url.password ||
      url.search ||
      url.hash
    )
      return { valid: false };
    return { valid: true, url: url.href };
  } catch {
    return { valid: false };
  }
}
