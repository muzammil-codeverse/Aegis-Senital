import { normalizeItemResponse, normalizeListResponse, request } from './client'

export async function listScenarios() {
  const payload = await request({ url: '/api/simulation/scenarios', method: 'GET' })
  return normalizeListResponse(payload)
}

export async function getScenario(scenarioId) {
  const payload = await request({
    url: `/api/simulation/scenarios/${encodeURIComponent(scenarioId)}`,
    method: 'GET',
  })
  return normalizeItemResponse(payload)
}

export async function getActiveScenarioRun() {
  const payload = await request({ url: '/api/simulation/scenarios/active', method: 'GET' })
  return payload || {}
}

export async function startScenario({ scenarioId, mode = 'step' }) {
  const payload = await request({
    url: '/api/simulation/scenarios/start',
    method: 'POST',
    data: { scenario_id: scenarioId, mode },
  })
  return payload || {}
}

export async function stepScenario() {
  const payload = await request({ url: '/api/simulation/scenarios/step', method: 'POST' })
  return payload || {}
}

export async function pauseScenario() {
  const payload = await request({ url: '/api/simulation/scenarios/pause', method: 'POST' })
  return payload || {}
}

export async function resumeScenario() {
  const payload = await request({ url: '/api/simulation/scenarios/resume', method: 'POST' })
  return payload || {}
}

export async function cancelScenario() {
  const payload = await request({ url: '/api/simulation/scenarios/cancel', method: 'POST' })
  return payload || {}
}

export async function resetScenario() {
  const payload = await request({ url: '/api/simulation/scenarios/reset', method: 'POST' })
  return payload || {}
}

export async function getRunStatus() {
  const payload = await request({ url: '/api/simulation/scenarios/run/status', method: 'GET' })
  return payload || {}
}

export async function getRunTimeline() {
  const payload = await request({ url: '/api/simulation/scenarios/run/timeline', method: 'GET' })
  return normalizeListResponse(payload)
}

// ---------------------------------------------------------------------------
// Phase 7 — Tracking / Route APIs
// ---------------------------------------------------------------------------

export async function getOperationalView(runId) {
  const payload = await request({
    url: `/api/simulation/scenarios/runs/${encodeURIComponent(runId)}/operational-view`,
    method: 'GET',
  })
  return payload?.item || null
}

export async function getSuspectPath(runId) {
  const payload = await request({
    url: `/api/simulation/scenarios/runs/${encodeURIComponent(runId)}/suspect-path`,
    method: 'GET',
  })
  return normalizeListResponse(payload)
}

export async function getCameraHandoffs(runId) {
  const payload = await request({
    url: `/api/simulation/scenarios/runs/${encodeURIComponent(runId)}/camera-handoffs`,
    method: 'GET',
  })
  return normalizeListResponse(payload)
}

export async function getDroneRoute(runId) {
  const payload = await request({
    url: `/api/simulation/scenarios/runs/${encodeURIComponent(runId)}/drone-route`,
    method: 'GET',
  })
  return payload || {}
}

export async function getFusedTracking(runId) {
  const payload = await request({
    url: `/api/simulation/scenarios/runs/${encodeURIComponent(runId)}/tracking`,
    method: 'GET',
  })
  return normalizeItemResponse(payload)
}
