import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AUTH_TOKEN_KEY, ApiError, apiClient, classifyApiError, normalizeError } from './client'

describe('api client error classification', () => {
  beforeEach(() => {
    window.localStorage.clear()
    window.sessionStorage.clear()
    vi.restoreAllMocks()
  })

  it('classifies network failures cleanly', () => {
    const classified = classifyApiError({ message: 'Network Error' })
    expect(classified.kind).toBe('network')
    expect(classified.message.toLowerCase()).toContain('temporarily unavailable')
  })

  it('classifies auth and permission errors', () => {
    expect(classifyApiError({ response: { status: 401 } }).kind).toBe('unauthenticated')
    expect(classifyApiError({ response: { status: 403 } }).kind).toBe('forbidden')
  })

  it('normalizes ApiError output for user-safe messaging', () => {
    const err = new ApiError('Please sign in to continue.', { status: 401, kind: 'unauthenticated' })
    expect(normalizeError(err)).toBe('Please sign in to continue.')
  })

  it('does not clear session token for non-auth 401 responses', async () => {
    const unauthorized = vi.fn()
    window.addEventListener('aegis-api-unauthorized', unauthorized)
    window.localStorage.setItem(AUTH_TOKEN_KEY, 'token-value')

    expect(() => apiClient.interceptors.response.handlers[0].rejected({
      response: { status: 401, data: { detail: 'Unauthorized for widget' } },
      config: { url: '/api/preflight/latest', method: 'get' },
    })).toThrow(ApiError)

    expect(window.localStorage.getItem(AUTH_TOKEN_KEY)).toBe('token-value')
    expect(unauthorized).toHaveBeenCalledTimes(1)
    window.removeEventListener('aegis-api-unauthorized', unauthorized)
  })

  it('/api/auth/me 401 clears session token and emits session expiration', async () => {
    const expired = vi.fn()
    window.addEventListener('aegis-session-expired', expired)
    window.localStorage.setItem(AUTH_TOKEN_KEY, 'token-value')

    expect(() => apiClient.interceptors.response.handlers[0].rejected({
      response: { status: 401, data: { detail: 'Invalid or expired token' } },
      config: { url: '/api/auth/me', method: 'get' },
    })).toThrow(ApiError)

    expect(window.localStorage.getItem(AUTH_TOKEN_KEY)).toBeNull()
    expect(expired).toHaveBeenCalledTimes(1)
    window.removeEventListener('aegis-session-expired', expired)
  })

  it('403 responses do not clear session token', async () => {
    const denied = vi.fn()
    window.addEventListener('aegis-access-denied', denied)
    window.localStorage.setItem(AUTH_TOKEN_KEY, 'token-value')

    expect(() => apiClient.interceptors.response.handlers[0].rejected({
      response: { status: 403, data: { detail: 'Insufficient permission' } },
      config: { url: '/api/preflight/run', method: 'post' },
    })).toThrow(ApiError)

    expect(window.localStorage.getItem(AUTH_TOKEN_KEY)).toBe('token-value')
    expect(denied).toHaveBeenCalledTimes(1)
    window.removeEventListener('aegis-access-denied', denied)
  })
})
