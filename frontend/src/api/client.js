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

const SESSION_VALIDATION_ENDPOINT = '/api/auth/me'
let lastScopedAuthEventAt = 0
const SCOPED_AUTH_EVENT_COOLDOWN_MS = 2500

function responseErrorMessage(data) {
  if (!data || typeof data !== 'object') return null
  if (typeof data.detail === 'string') return data.detail
  if (data.detail && typeof data.detail === 'object') {
    if (typeof data.detail.detail === 'string') return data.detail.detail
    if (typeof data.detail.message === 'string') return data.detail.message
    if (typeof data.detail.error === 'string') return data.detail.error
  }
  if (typeof data.error === 'string') return data.error
  if (typeof data.message === 'string') return data.message
  return null
}

function requestPath(config = {}) {
  const rawUrl = String(config.url || '')
  try {
    return new URL(rawUrl, API_BASE_URL).pathname
  } catch {
    return rawUrl.split('?')[0]
  }
}

function dispatchApiEvent(name, detail = {}) {
  window.dispatchEvent(new CustomEvent(name, { detail }))
}

export function classifyApiError(error) {
  const status = error?.response?.status
  if (!status) {
    return { kind: 'network', message: 'Runtime data temporarily unavailable.' }
  }
  if (status === 401) return { kind: 'unauthenticated', message: 'Please sign in to continue.' }
  if (status === 403) return { kind: 'forbidden', message: 'You do not have permission for this action.' }
  if (status === 404) return { kind: 'not_found', message: 'This endpoint is unavailable in the current runtime.' }
  if (status === 503) return { kind: 'unavailable', message: 'Service is currently degraded. Please retry shortly.' }
  if (status >= 500) return { kind: 'server_error', message: 'Server error. Please retry.' }
  return { kind: 'request_error', message: responseErrorMessage(error?.response?.data) || error?.message || 'Request failed' }
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
    const path = requestPath(error.config)
    const classification = classifyApiError(error)
    if (status === 401) {
      if (path === SESSION_VALIDATION_ENDPOINT) {
        clearStoredToken()
        dispatchApiEvent('aegis-session-expired', { url: path })
      } else {
        const now = Date.now()
        if (now - lastScopedAuthEventAt > SCOPED_AUTH_EVENT_COOLDOWN_MS) {
          lastScopedAuthEventAt = now
          dispatchApiEvent('aegis-api-unauthorized', {
            url: path,
            method: error.config?.method,
            status,
          })
        }
      }
    } else if (status === 403) {
      dispatchApiEvent('aegis-access-denied', {
        url: path,
        method: error.config?.method,
        status,
      })
    } else if (!status) {
      dispatchApiEvent('aegis-service-unavailable', {
        url: path,
        method: error.config?.method,
        kind: classification.kind,
      })
    }
    const message = responseErrorMessage(error.response?.data) || classification.message
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
  if (!error?.status) return 'Runtime data temporarily unavailable.'
  return error?.message || 'Request failed'
}
