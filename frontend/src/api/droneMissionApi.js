/**
 * API client for the Drone Patrol Mission Planner.
 * All calls go through the shared authenticated API client.
 */

import { normalizeItemResponse, normalizeListResponse, request } from './client'

const BASE = '/api/drone-missions'

export async function listMissions({ status, limit = 50, offset = 0 } = {}) {
  const params = { limit, offset }
  if (status) params.status = status
  return normalizeListResponse(await request({ url: BASE, method: 'GET', params }))
}

export async function getMission(missionId) {
  return normalizeItemResponse(await request({ url: `${BASE}/${encodeURIComponent(missionId)}`, method: 'GET' }))
}

export async function createMission(payload) {
  return normalizeItemResponse(await request({ url: BASE, method: 'POST', data: payload }))
}

export async function listCityMissionPresets() {
  return normalizeListResponse(await request({ url: `${BASE}/presets/city`, method: 'GET' }))
}

export async function importCityMissionPreset(presetName) {
  return normalizeItemResponse(await request({
    url: `${BASE}/presets/${encodeURIComponent(presetName)}/import`,
    method: 'POST',
  }))
}

export async function updateMission(missionId, payload) {
  return normalizeItemResponse(await request({
    url: `${BASE}/${encodeURIComponent(missionId)}`,
    method: 'PATCH',
    data: payload,
  }))
}

export async function deleteMission(missionId) {
  return request({ url: `${BASE}/${encodeURIComponent(missionId)}`, method: 'DELETE' })
}

export async function startMission(missionId, payload = {}) {
  return normalizeItemResponse(await request({
    url: `${BASE}/${encodeURIComponent(missionId)}/start`,
    method: 'POST',
    data: { mission_id: missionId, ...payload },
  }))
}

export async function pauseSession(sessionId) {
  return normalizeItemResponse(await request({ url: `${BASE}/sessions/${encodeURIComponent(sessionId)}/pause`, method: 'POST' }))
}

export async function resumeSession(sessionId) {
  return normalizeItemResponse(await request({ url: `${BASE}/sessions/${encodeURIComponent(sessionId)}/resume`, method: 'POST' }))
}

export async function cancelSession(sessionId) {
  return normalizeItemResponse(await request({ url: `${BASE}/sessions/${encodeURIComponent(sessionId)}/cancel`, method: 'POST' }))
}

export async function getSessionStatus(sessionId) {
  return normalizeItemResponse(await request({ url: `${BASE}/sessions/${encodeURIComponent(sessionId)}/status`, method: 'GET' }))
}

export async function getSessionTelemetry(sessionId, { limit = 500, offset = 0 } = {}) {
  return normalizeListResponse(await request({
    url: `${BASE}/sessions/${encodeURIComponent(sessionId)}/telemetry`,
    method: 'GET',
    params: { limit, offset },
  }))
}

export async function getSessionEvents(sessionId, { limit = 200, offset = 0 } = {}) {
  return normalizeListResponse(await request({
    url: `${BASE}/sessions/${encodeURIComponent(sessionId)}/events`,
    method: 'GET',
    params: { limit, offset },
  }))
}

export async function getSessionReport(sessionId) {
  return normalizeItemResponse(await request({ url: `${BASE}/sessions/${encodeURIComponent(sessionId)}/report`, method: 'GET' }))
}

export async function getSessionEvidenceBundle(sessionId) {
  return request({ url: `${BASE}/sessions/${encodeURIComponent(sessionId)}/evidence-bundle`, method: 'GET' })
}
