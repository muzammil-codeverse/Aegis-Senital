const listeners = new Set()
const state = {
  incidents: [],
  selectedIncidentId: null,
}

function emit() {
  listeners.forEach(listener => listener({ ...state }))
}

export const incidentStore = {
  getSnapshot: () => ({ ...state }),
  subscribe(listener) {
    listeners.add(listener)
    return () => listeners.delete(listener)
  },
  setIncidents(incidents) {
    state.incidents = Array.isArray(incidents) ? incidents.slice(0, 250) : []
    emit()
  },
  selectIncident(incidentId) {
    state.selectedIncidentId = incidentId || null
    emit()
  },
}
