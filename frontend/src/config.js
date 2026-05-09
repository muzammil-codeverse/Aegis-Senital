export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'
export const WS_BASE_URL = import.meta.env.VITE_WS_BASE_URL || 'ws://localhost:8000'
export const REQUEST_TIMEOUT_MS = Number(import.meta.env.VITE_REQUEST_TIMEOUT_MS || 8000)
export const DASHBOARD_POLL_MS = Number(import.meta.env.VITE_DASHBOARD_POLL_MS || 10000)

export function buildWebSocketUrl(path, token) {
  const base = `${WS_BASE_URL.replace(/\/$/, '')}${path}`
  return token ? `${base}?token=${encodeURIComponent(token)}` : base
}
