import { clearStoredToken, getStoredToken, setStoredToken } from '../api/client'
import { allowClientTokenStorage } from '../config'

let state = {
  user: null,
  token: getStoredToken(),
  permissions: [],
  authenticated: false,
  authRequired: true,
  ready: false,
  loading: true,
  error: null,
  sessionExpired: false,
}

const listeners = new Set()

function emit() {
  for (const listener of listeners) listener()
}

export const authStore = {
  getSnapshot() {
    return state
  },
  subscribe(listener) {
    listeners.add(listener)
    return () => listeners.delete(listener)
  },
  setState(partial) {
    state = { ...state, ...partial }
    emit()
  },
  setSession({ token, user, permissions = [], authRequired = true }) {
    state = {
      ...state,
      token: token || getStoredToken(),
      user,
      permissions,
      authenticated: Boolean(user),
      authRequired,
      ready: true,
      loading: false,
      error: null,
      sessionExpired: false,
    }
    emit()
  },
  clearSession() {
    clearStoredToken()
    state = {
      ...state,
      token: null,
      user: null,
      permissions: [],
      authenticated: false,
      ready: true,
      loading: false,
      sessionExpired: false,
    }
    emit()
  },
  expireSession() {
    clearStoredToken()
    state = {
      ...state,
      token: null,
      user: null,
      permissions: [],
      authenticated: false,
      ready: true,
      loading: false,
      sessionExpired: true,
    }
    emit()
  },
  clearSessionNotice() {
    state = { ...state, sessionExpired: false }
    emit()
  },
}

window.addEventListener('aegis-auth-change', () => {
  if (!allowClientTokenStorage()) return
  const token = getStoredToken()
  if (token !== state.token) {
    authStore.setState({ token })
  }
})
