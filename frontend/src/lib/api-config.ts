/**
 * API and WebSocket URL configuration.
 * - In dev: VITE_API_URL is empty, requests go through Vite proxy (relative paths)
 * - In production (Vercel): VITE_API_URL points to external backend
 */
const apiUrl = import.meta.env.VITE_API_URL || '';

/** Base URL for REST API calls (e.g., "" in dev, "https://api.example.com" in prod) */
export function getApiBaseUrl(): string {
  return apiUrl;
}

/** Base URL for WebSocket connections */
export function getWsBaseUrl(): string {
  if (apiUrl) {
    // Production: convert http(s) URL to ws(s)
    return apiUrl.replace(/^http/, 'ws');
  }
  // Dev: use current host with appropriate protocol
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.host}`;
}
