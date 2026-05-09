const listeners = new Set()
const state = {
  alerts: [],
  selectedAlertId: null,
}

function emit() {
  listeners.forEach(listener => listener({ ...state }))
}

export const alertStore = {
  getSnapshot: () => ({ ...state }),
  subscribe(listener) {
    listeners.add(listener)
    return () => listeners.delete(listener)
  },
  setAlerts(alerts) {
    state.alerts = Array.isArray(alerts) ? alerts.slice(0, 250) : []
    emit()
  },
  selectAlert(alertId) {
    state.selectedAlertId = alertId || null
    emit()
  },
}
