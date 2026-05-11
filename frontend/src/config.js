export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'
export const WS_BASE_URL = import.meta.env.VITE_WS_BASE_URL || 'ws://localhost:8000'
export const REQUEST_TIMEOUT_MS = Number(import.meta.env.VITE_REQUEST_TIMEOUT_MS || 8000)
export const DASHBOARD_POLL_MS = Number(import.meta.env.VITE_DASHBOARD_POLL_MS || 10000)
export const AUTH_STORAGE_MODE = String(import.meta.env.VITE_AUTH_STORAGE_MODE || 'cookie').toLowerCase()
export const ALLOW_DEV_TOKEN_STORAGE = String(import.meta.env.VITE_ALLOW_DEV_TOKEN_STORAGE || 'false').toLowerCase() === 'true'
export const ALLOW_QUERY_TOKEN_WEBSOCKETS = String(import.meta.env.VITE_ALLOW_QUERY_TOKEN_WEBSOCKET || 'false').toLowerCase() === 'true'
export const CSRF_COOKIE_NAME = import.meta.env.VITE_CSRF_COOKIE_NAME || 'aegis_csrf_token'
export const CSRF_HEADER_NAME = import.meta.env.VITE_CSRF_HEADER_NAME || 'X-CSRF-Token'

export function allowClientTokenStorage() {
  return AUTH_STORAGE_MODE === 'token' || (import.meta.env.DEV && ALLOW_DEV_TOKEN_STORAGE)
}

export function authUsesCookieMode() {
  return !allowClientTokenStorage()
}

export function readCookie(name) {
  const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const match = document.cookie.match(new RegExp(`(?:^|; )${escaped}=([^;]*)`))
  return match ? decodeURIComponent(match[1]) : null
}

export function buildWebSocketUrl(path, token) {
  const base = `${WS_BASE_URL.replace(/\/$/, '')}${path}`
  return import.meta.env.DEV && ALLOW_QUERY_TOKEN_WEBSOCKETS && token
    ? `${base}?token=${encodeURIComponent(token)}`
    : base
}

export function buildWebSocketProtocols(token) {
  if (!token || (import.meta.env.DEV && ALLOW_QUERY_TOKEN_WEBSOCKETS)) {
    return undefined
  }
  return ['aegis.v1', `token.${token}`]
}
