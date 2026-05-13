import axios from 'axios'
import {
  API_BASE_URL,
  REQUEST_TIMEOUT_MS,
  CSRF_COOKIE_NAME,
  CSRF_HEADER_NAME,
  allowClientTokenStorage,
  readCookie,
} from '../config'

export const AUTH_TOKEN_KEY = 'aegis.accessToken'

export function getStoredToken() {
  if (!allowClientTokenStorage()) return null
  return window.localStorage.getItem(AUTH_TOKEN_KEY) || window.sessionStorage.getItem(AUTH_TOKEN_KEY)
}

export function setStoredToken(token, { session = false } = {}) {
  if (!allowClientTokenStorage()) {
    clearStoredToken()
    return null
  }
  if (!token) return clearStoredToken()
  const target = session ? window.sessionStorage : window.localStorage
  const other = session ? window.localStorage : window.sessionStorage
  other.removeItem(AUTH_TOKEN_KEY)
  target.setItem(AUTH_TOKEN_KEY, token)
  window.dispatchEvent(new CustomEvent('aegis-auth-change'))
}

export function clearStoredToken() {
  window.localStorage.removeItem(AUTH_TOKEN_KEY)
  window.sessionStorage.removeItem(AUTH_TOKEN_KEY)
  window.dispatchEvent(new CustomEvent('aegis-auth-change'))
}

/**
 * @typedef {Object} ApiListResponse
 * @property {Array} items
 * @property {number} count
 * @property {'ok'|'empty'|'error'} status
 * @property {string=} error
 */

/**
 * @typedef {Object} ApiItemResponse
 * @property {Object|null} item
 * @property {'ok'|'empty'|'not_found'|'error'} status
 * @property {string=} error
 */

export class ApiError extends Error {
  constructor(message, details = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = details.status
    this.kind = details.kind || 'unknown'
    this.details = details
  }
}

const AUTH_ENDPOINTS = new Set(['/api/auth/login', '/api/auth/me'])
let lastUnauthorizedEventAt = 0
const UNAUTHORIZED_EVENT_COOLDOWN_MS = 2500

export function classifyApiError(error) {
  const status = error?.response?.status
  if (!status) {
    return { kind: 'network', message: 'Backend unavailable. Check that the API is running.' }
  }
  if (status === 401) return { kind: 'unauthenticated', message: 'Please sign in to continue.' }
  if (status === 403) return { kind: 'forbidden', message: 'You do not have permission for this action.' }
  if (status === 404) return { kind: 'not_found', message: 'This endpoint is unavailable in the current runtime.' }
  if (status === 503) return { kind: 'unavailable', message: 'Service is currently degraded. Please retry shortly.' }
  if (status >= 500) return { kind: 'server_error', message: 'Server error. Please retry.' }
  return { kind: 'request_error', message: error?.response?.data?.detail || error?.message || 'Request failed' }
}

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: REQUEST_TIMEOUT_MS,
  withCredentials: true,
  headers: { Accept: 'application/json' },
})

apiClient.interceptors.request.use(config => {
  const token = getStoredToken()
  if (token) {
    config.headers = config.headers || {}
    config.headers.Authorization = `Bearer ${token}`
  }
  const method = String(config.method || 'get').toUpperCase()
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    const csrfToken = readCookie(CSRF_COOKIE_NAME)
    if (csrfToken) {
      config.headers = config.headers || {}
      config.headers[CSRF_HEADER_NAME] = csrfToken
    }
  }
  return config
})

apiClient.interceptors.response.use(
  response => response,
  error => {
    const status = error.response?.status
    const path = String(error.config?.url || '')
    const classification = classifyApiError(error)
    if (status === 401) {
      clearStoredToken()
      const isAuthEndpoint = AUTH_ENDPOINTS.has(path)
      const now = Date.now()
      if (!isAuthEndpoint && now - lastUnauthorizedEventAt > UNAUTHORIZED_EVENT_COOLDOWN_MS) {
        lastUnauthorizedEventAt = now
        window.dispatchEvent(new CustomEvent('aegis-auth-unauthorized'))
      }
    }
    const message =
      error.response?.data?.detail ||
      error.response?.data?.error ||
      classification.message
    throw new ApiError(message, {
      status,
      kind: classification.kind,
      url: error.config?.url,
      method: error.config?.method,
      payload: error.response?.data,
    })
  },
)

export async function request(config) {
  const response = await apiClient.request(config)
  return response.data
}

export function normalizeListResponse(payload, fallbackStatus = 'empty') {
  if (Array.isArray(payload)) {
    return { items: payload, count: payload.length, status: payload.length ? 'ok' : fallbackStatus }
  }
  const items = Array.isArray(payload?.items) ? payload.items : []
  return {
    items,
    count: Number.isFinite(payload?.count) ? payload.count : items.length,
    status: payload?.status || (items.length ? 'ok' : fallbackStatus),
  }
}

export function normalizeItemResponse(payload) {
  if (!payload || typeof payload !== 'object') {
    return { item: null, status: 'empty' }
  }
  if ('item' in payload) {
    return { item: payload.item ?? null, status: payload.status || (payload.item ? 'ok' : 'empty') }
  }
  return { item: payload, status: 'ok' }
}

export function normalizeError(error) {
  if (error instanceof ApiError) {
    return error.message
  }
  if (!error?.status) return 'Backend unavailable. Check that the API is running.'
  return error?.message || 'Request failed'
}
