import { useCallback, useEffect, useMemo, useState } from 'react'
import { normalizeError } from '../api/client'
import { useAuth } from './useAuth'

export const AUTH_CHECKING_MESSAGE = 'Checking session...'
export const AUTH_REQUIRED_MESSAGE = 'Sign in required'

export function authGateFor(auth, permission, enabled = true) {
  const ready = Boolean(auth.ready ?? !auth.loading)
  const authenticated = Boolean(auth.authenticated)
  const permitted = permission ? auth.hasPermission(permission) : true

  if (!enabled) {
    return { enabled: false, ready, authenticated, permitted, reason: 'disabled', message: null }
  }
  if (!ready) {
    return { enabled: false, ready, authenticated, permitted: false, reason: 'checking', message: AUTH_CHECKING_MESSAGE }
  }
  if (!authenticated) {
    return { enabled: false, ready, authenticated, permitted: false, reason: 'unauthenticated', message: AUTH_REQUIRED_MESSAGE }
  }
  if (!permitted) {
    return { enabled: false, ready, authenticated, permitted: false, reason: 'forbidden', message: 'Permission denied' }
  }
  return { enabled: true, ready, authenticated, permitted: true, reason: null, message: null }
}

export function useAuthGate(permission, { enabled = true } = {}) {
  const auth = useAuth()
  const ready = auth.ready
  const loading = auth.loading
  const authenticated = auth.authenticated
  const hasPermission = auth.hasPermission
  return useMemo(
    () => authGateFor({ ready, loading, authenticated, hasPermission }, permission, enabled),
    [authenticated, enabled, hasPermission, loading, permission, ready],
  )
}

export function useAuthenticatedQuery({
  enabled = true,
  permission,
  pollMs = 0,
  initialData = null,
  queryFn,
  onData,
  normalize = value => value,
  errorPrefix = null,
} = {}) {
  const gate = useAuthGate(permission, { enabled })
  const [data, setData] = useState(initialData)
  const [loading, setLoading] = useState(Boolean(enabled))
  const [error, setError] = useState(null)

  const refresh = useCallback(async () => {
    if (!gate.enabled) {
      setLoading(gate.reason === 'checking')
      setError(gate.reason && gate.reason !== 'disabled' && gate.reason !== 'checking' ? gate.message : null)
      return initialData
    }
    setLoading(true)
    try {
      const result = normalize(await queryFn())
      setData(result)
      onData?.(result)
      setError(null)
      return result
    } catch (err) {
      const message = normalizeError(err)
      setError(errorPrefix ? `${errorPrefix}: ${message}` : message)
      return initialData
    } finally {
      setLoading(false)
    }
  }, [errorPrefix, gate.enabled, gate.message, gate.reason, initialData, normalize, onData, queryFn])

  useEffect(() => {
    const initialTimer = window.setTimeout(refresh, 0)
    if (!gate.enabled || !pollMs) {
      return () => window.clearTimeout(initialTimer)
    }
    const timer = window.setInterval(refresh, pollMs)
    return () => {
      window.clearTimeout(initialTimer)
      window.clearInterval(timer)
    }
  }, [gate.enabled, pollMs, refresh])

  return {
    data,
    loading,
    error,
    refresh,
    authGate: gate,
  }
}
