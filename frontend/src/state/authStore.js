import { clearStoredToken, getStoredToken, setStoredToken } from '../api/client'

let state = {
  user: null,
  token: getStoredToken(),
  permissions: [],
  authenticated: false,
  authRequired: true,
  loading: true,
  error: null,
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
    if (token) setStoredToken(token)
    state = {
      ...state,
      token: token || getStoredToken(),
      user,
      permissions,
      authenticated: Boolean(user),
      authRequired,
      loading: false,
      error: null,
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
      loading: false,
    }
    emit()
  },
}

window.addEventListener('aegis-auth-change', () => {
  const token = getStoredToken()
  if (token !== state.token) {
    authStore.setState({ token })
  }
})
