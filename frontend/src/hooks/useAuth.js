import { useCallback, useEffect, useSyncExternalStore } from 'react'
import { changePassword as changePasswordRequest, getMe, login as loginRequest, logout as logoutRequest } from '../api/authApi'
import { clearStoredToken, getStoredToken, setStoredToken } from '../api/client'
import { authStore } from '../state/authStore'

let bootstrapped = false
let refreshPromise = null

export function useAuth() {
  const snapshot = useSyncExternalStore(authStore.subscribe, authStore.getSnapshot, authStore.getSnapshot)

  const refreshMe = useCallback(async () => {
    if (refreshPromise) return refreshPromise
    authStore.setState({ loading: true, error: null })
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
        clearStoredToken()
        authStore.setState({
          user: null,
          token: null,
          permissions: [],
          authenticated: false,
          loading: false,
          error: error?.status === 401 ? null : (error?.message || 'Unable to load session'),
        })
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
    function handleUnauthorized() {
      authStore.expireSession()
      window.location.hash = 'login'
    }
    window.addEventListener('aegis-auth-unauthorized', handleUnauthorized)
    return () => window.removeEventListener('aegis-auth-unauthorized', handleUnauthorized)
  }, [refreshMe])

  const login = useCallback(async (username, password, { remember = true } = {}) => {
    authStore.setState({ loading: true, error: null })
    try {
      const payload = await loginRequest(username, password)
      setStoredToken(payload.access_token, { session: !remember })
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
        loading: false,
        error: error?.message || 'Login failed',
      })
      throw error
    }
  }, [])

  const logout = useCallback(async () => {
    try {
      if (getStoredToken()) await logoutRequest()
    } catch {
      // Local session cleanup still wins if the server is unavailable.
    }
    authStore.clearSession()
    window.location.hash = 'login'
  }, [])

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
    login,
    logout,
    refreshMe,
    changePassword,
    clearSessionNotice,
    hasPermission,
  }
}
