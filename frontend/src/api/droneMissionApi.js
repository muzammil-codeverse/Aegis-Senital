/**
 * API client for the Drone Patrol Mission Planner (Phase 45).
 * All missions are simulated-only. Operator review required.
 */

const BASE = '/api/drone-missions'

async function _request(path, options = {}) {
  const res = await fetch(path, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `Request failed: ${res.status}`)
  }
  return res.json()
}

export async function listMissions({ status, limit = 50, offset = 0 } = {}) {
  const params = new URLSearchParams({ limit, offset })
  if (status) params.set('status', status)
  return _request(`${BASE}?${params}`)
}

export async function getMission(missionId) {
  return _request(`${BASE}/${missionId}`)
}

export async function createMission(payload) {
  return _request(BASE, { method: 'POST', body: JSON.stringify(payload) })
}

export async function updateMission(missionId, payload) {
  return _request(`${BASE}/${missionId}`, { method: 'PATCH', body: JSON.stringify(payload) })
}

export async function deleteMission(missionId) {
  return _request(`${BASE}/${missionId}`, { method: 'DELETE' })
}

export async function startMission(missionId, payload = {}) {
  return _request(`${BASE}/${missionId}/start`, { method: 'POST', body: JSON.stringify({ mission_id: missionId, ...payload }) })
}

export async function pauseSession(sessionId) {
  return _request(`${BASE}/sessions/${sessionId}/pause`, { method: 'POST' })
}

export async function resumeSession(sessionId) {
  return _request(`${BASE}/sessions/${sessionId}/resume`, { method: 'POST' })
}

export async function cancelSession(sessionId) {
  return _request(`${BASE}/sessions/${sessionId}/cancel`, { method: 'POST' })
}

export async function getSessionStatus(sessionId) {
  return _request(`${BASE}/sessions/${sessionId}/status`)
}

export async function getSessionTelemetry(sessionId, { limit = 500, offset = 0 } = {}) {
  const params = new URLSearchParams({ limit, offset })
  return _request(`${BASE}/sessions/${sessionId}/telemetry?${params}`)
}

export async function getSessionEvents(sessionId, { limit = 200, offset = 0 } = {}) {
  const params = new URLSearchParams({ limit, offset })
  return _request(`${BASE}/sessions/${sessionId}/events?${params}`)
}

export async function getSessionReport(sessionId) {
  return _request(`${BASE}/sessions/${sessionId}/report`)
}
