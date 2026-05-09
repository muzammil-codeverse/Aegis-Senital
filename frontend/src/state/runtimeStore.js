const listeners = new Set()
const state = {
  metrics: {},
  health: { status: 'unknown', reasons: [] },
}

function emit() {
  listeners.forEach(listener => listener({ ...state }))
}

export const runtimeStore = {
  getSnapshot: () => ({ ...state }),
  subscribe(listener) {
    listeners.add(listener)
    return () => listeners.delete(listener)
  },
  setMetrics(metrics) {
    state.metrics = metrics && typeof metrics === 'object' ? metrics : {}
    emit()
  },
  setHealth(health) {
    state.health = health && typeof health === 'object' ? health : { status: 'unknown', reasons: [] }
    emit()
  },
}
