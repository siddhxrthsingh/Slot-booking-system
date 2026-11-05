/**
 * Resolves the WebSocket base URL (protocol + host, no trailing slash/path).
 *
 * If VITE_WS_BASE_URL is set (e.g. "wss://api.example.com"), it is used as-is —
 * required for production deployments where the frontend and backend are on
 * different hosts. Otherwise falls back to the current page's origin, switching
 * http(s) to ws(s), which works when a reverse proxy serves both on one host
 * (matches the Vite dev proxy behavior).
 */
export function getWsBaseUrl() {
  const configured = import.meta.env.VITE_WS_BASE_URL;
  if (configured) return configured.replace(/\/$/, '');

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.host}`;
}
