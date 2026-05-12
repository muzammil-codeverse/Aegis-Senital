import { vi } from 'vitest'

export function createMockRuntimeStatus(overrides = {}) {
  return {
    loading: false,
    error: null,
    overall: 'ok',
    generatedAt: Date.now(),
    byKey: {},
    items: [
      { key: 'system', label: 'Backend', status: 'ok', summary: 'Backend health' },
      { key: 'database', label: 'Database', status: 'ok', summary: 'Database healthy' },
      { key: 'redis', label: 'Redis', status: 'ok', summary: 'Redis healthy' },
      { key: 'droneSimulation', label: 'Drone Simulation', status: 'ok', summary: 'Simulated session active' },
      { key: 'droneMission', label: 'Drone Mission', status: 'ok', summary: '1 simulated mission(s) active or staged' },
      { key: 'droneFusion', label: 'Drone Fusion', status: 'ok', summary: 'Fusion service reachable' },
      { key: 'investigation', label: 'Investigation', status: 'ok', summary: 'No pending hypothesis reviews' },
      { key: 'modelGovernance', label: 'Model Governance', status: 'ok', summary: 'Governance checks available' },
      { key: 'llm', label: 'OpenAI / LLM', status: 'ok', summary: 'LLM status available' },
    ],
    refresh: vi.fn(),
    ...overrides,
  }
}

export function createDegradedRuntimeStatus() {
  return createMockRuntimeStatus({
    overall: 'degraded',
    items: [
      { key: 'system', label: 'Backend', status: 'degraded', summary: 'Some subsystems unavailable' },
      { key: 'droneSimulation', label: 'Drone Simulation', status: 'critical', summary: 'Drone runtime unavailable' },
    ],
  })
}
