import { normalizeItemResponse, normalizeListResponse, request } from './client'

export async function listFusionObservations(params = {}) {
  return normalizeListResponse(await request({ url: '/api/drone-fusion/observations', method: 'GET', params }))
}

export async function runCorrelation(body = {}) {
  return normalizeListResponse(await request({ url: '/api/drone-fusion/correlate', method: 'POST', data: body }))
}

export async function listCorrelations(params = {}) {
  return normalizeListResponse(await request({ url: '/api/drone-fusion/correlations', method: 'GET', params }))
}

export async function getCorrelation(correlationId) {
  return normalizeItemResponse(await request({ url: `/api/drone-fusion/correlations/${encodeURIComponent(correlationId)}`, method: 'GET' }))
}

export async function acceptCorrelation(correlationId, notes) {
  return normalizeItemResponse(await request({
    url: `/api/drone-fusion/correlations/${encodeURIComponent(correlationId)}/accept`,
    method: 'POST',
    data: { action: 'accept', notes: notes || null },
  }))
}

export async function rejectCorrelation(correlationId, notes) {
  return normalizeItemResponse(await request({
    url: `/api/drone-fusion/correlations/${encodeURIComponent(correlationId)}/reject`,
    method: 'POST',
    data: { action: 'reject', notes: notes || null },
  }))
}

export async function markCorrelationInconclusive(correlationId, notes) {
  return normalizeItemResponse(await request({
    url: `/api/drone-fusion/correlations/${encodeURIComponent(correlationId)}/inconclusive`,
    method: 'POST',
    data: { action: 'inconclusive', notes: notes || null },
  }))
}

export async function listHandoffs(params = {}) {
  return normalizeListResponse(await request({ url: '/api/drone-fusion/handoffs', method: 'GET', params }))
}

export async function suggestHandoffsForEvent(body = {}) {
  return normalizeListResponse(await request({ url: '/api/drone-fusion/handoffs/suggest-for-event', method: 'POST', data: body }))
}

export async function suggestHandoffsForMission(body = {}) {
  return normalizeListResponse(await request({ url: '/api/drone-fusion/handoffs/suggest-for-mission', method: 'POST', data: body }))
}

export async function getFusionTimeline(params = {}) {
  return normalizeItemResponse(await request({ url: '/api/drone-fusion/timeline', method: 'GET', params }))
}

export async function getFusionHealth() {
  return normalizeItemResponse(await request({ url: '/api/drone-fusion/health', method: 'GET' }))
}
