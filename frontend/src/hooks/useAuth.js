import { useCallback, useEffect, useSyncExternalStore } from 'react'
import { changePassword as changePasswordRequest, getMe, login as loginRequest, logout as logoutRequest } from '../api/authApi'
import { clearStoredToken, getStoredToken, setStoredToken } from '../api/client'
import { authUsesCookieMode, readCookie, CSRF_COOKIE_NAME } from '../config'
import { authStore } from '../state/authStore'

let bootstrapped = false
let refreshPromise = null

export function useAuth() {
  const snapshot = useSyncExternalStore(authStore.subscribe, authStore.getSnapshot, authStore.getSnapshot)

  const refreshMe = useCallback(async () => {
    if (refreshPromise) return refreshPromise
    // Token mode: no stored token means not logged in yet — show login, not "session expired".
    if (!authUsesCookieMode() && !getStoredToken()) {
      authStore.setState({ user: null, token: null, permissions: [], authenticated: false, ready: true, loading: false, error: null, sessionExpired: false })
      return null
    }
    // Cookie mode: no token AND no CSRF cookie means no session.
    if (authUsesCookieMode() && !getStoredToken() && !readCookie(CSRF_COOKIE_NAME)) {
      authStore.setState({ user: null, token: null, permissions: [], authenticated: false, ready: true, loading: false, error: null })
      return null
    }
    authStore.setState({ loading: true, ready: false, error: null })
    refreshPromise = getMe()
      .then(payload => {
        authStore.setSession({
          token: getStoredToken(),
          user: payload.user,
          permissions: payload.permissions || [],
          authRequired: payload.auth_required !== false,
        })
        return payload.user
      })
      .catch(error => {
        if (error?.status === 401 || error?.details?.status === 401) {
          // Only mark session as truly expired if we had a stored token that was rejected.
          if (getStoredToken()) {
            authStore.expireSession()
          } else {
            authStore.setState({ user: null, token: null, permissions: [], authenticated: false, ready: true, loading: false, error: null, sessionExpired: false })
          }
        } else {
          authStore.setState({
            loading: false,
            ready: true,
            error: error?.message || 'Session validation temporarily unavailable',
          })
        }
        return null
      })
      .finally(() => {
        refreshPromise = null
      })
    return refreshPromise
  }, [])

  useEffect(() => {
    if (!bootstrapped) {
      bootstrapped = true
      refreshMe()
    }
    function handleSessionExpired() {
      authStore.expireSession()
      window.location.hash = 'login'
    }
    window.addEventListener('aegis-session-expired', handleSessionExpired)
    return () => window.removeEventListener('aegis-session-expired', handleSessionExpired)
  }, [refreshMe])

  const login = useCallback(async (username, password, { remember = true } = {}) => {
    authStore.setState({ loading: true, ready: false, error: null })
    try {
      const payload = await loginRequest(username, password)
      if (payload.access_token) {
        setStoredToken(payload.access_token, { session: !remember })
      } else if (authUsesCookieMode()) {
        clearStoredToken()
      }
      authStore.setSession({
        token: payload.access_token,
        user: payload.user,
        permissions: payload.permissions || [],
        authRequired: true,
      })
      return payload.user
    } catch (error) {
      clearStoredToken()
      authStore.setState({
        user: null,
        token: null,
        permissions: [],
        authenticated: false,
        ready: true,
        loading: false,
        error: error?.message || 'Login failed',
      })
      throw error
    }
  }, [])

  const logout = useCallback(async () => {
    try {
      if (snapshot.authenticated || getStoredToken()) await logoutRequest()
    } catch {
      // Local session cleanup still wins if the server is unavailable.
    }
    authStore.clearSession()
    window.location.hash = 'login'
  }, [snapshot.authenticated])

  const changePassword = useCallback(async (currentPassword, newPassword) => {
    const payload = await changePasswordRequest(currentPassword, newPassword)
    authStore.setState({ user: payload.item || snapshot.user, error: null })
    return payload
  }, [snapshot.user])

  const clearSessionNotice = useCallback(() => {
    authStore.clearSessionNotice()
  }, [])

  const hasPermission = useCallback((permission) => {
    if (!permission) return true
    if (permission === 'admin') return snapshot.user?.role === 'admin'
    const permissions = snapshot.permissions || []
    return permissions.includes('*') || permissions.includes(permission)
  }, [snapshot.permissions, snapshot.user?.role])

  return {
    ...snapshot,
    ready: snapshot.ready || !snapshot.loading,
    isAuthenticated: snapshot.authenticated,
    login,
    logout,
    refreshMe,
    changePassword,
    clearSessionNotice,
    hasPermission,
  }
}
