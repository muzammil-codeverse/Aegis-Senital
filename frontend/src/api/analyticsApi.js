import { normalizeItemResponse, normalizeListResponse, request } from './client'

function compactParams(params = {}) {
  return Object.fromEntries(
    Object.entries(params).filter(([, value]) => value !== null && value !== undefined && value !== ''),
  )
}

export async function getDashboardOverview(params = {}) {
  return normalizeItemResponse(await request({ url: '/api/analytics/overview', method: 'GET', params: compactParams(params) }))
}

export async function getEventTimeseries(params = {}) {
  return normalizeListResponse(await request({ url: '/api/analytics/events/timeseries', method: 'GET', params: compactParams(params) }))
}

export async function getEventsByType(params = {}) {
  return normalizeListResponse(await request({ url: '/api/analytics/events/by-type', method: 'GET', params: compactParams(params) }))
}

export async function getCaseSummary(params = {}) {
  return normalizeItemResponse(await request({ url: '/api/analytics/cases/summary', method: 'GET', params: compactParams(params) }))
}

export async function getCaseTimeseries(params = {}) {
  return normalizeListResponse(await request({ url: '/api/analytics/cases/timeseries', method: 'GET', params: compactParams(params) }))
}

export async function getCameraRisk(params = {}) {
  return normalizeListResponse(await request({ url: '/api/analytics/cameras/risk', method: 'GET', params: compactParams(params) }))
}

export async function getCameraHeatmap(params = {}) {
  return normalizeListResponse(await request({ url: '/api/analytics/cameras/heatmap', method: 'GET', params: compactParams(params) }))
}

export async function getModelPerformance(params = {}) {
  return normalizeListResponse(await request({ url: '/api/analytics/models/performance', method: 'GET', params: compactParams(params) }))
}

export async function getAnomalyTrends(params = {}) {
  return normalizeItemResponse(await request({ url: '/api/analytics/anomaly/trends', method: 'GET', params: compactParams(params) }))
}

export async function getIdentitySummary(params = {}) {
  return normalizeItemResponse(await request({ url: '/api/analytics/identity/summary', method: 'GET', params: compactParams(params) }))
}

export async function getOpenVocabSummary(params = {}) {
  return normalizeItemResponse(await request({ url: '/api/analytics/open-vocab/summary', method: 'GET', params: compactParams(params) }))
}

export async function getStreamReliability(params = {}) {
  return normalizeListResponse(await request({ url: '/api/analytics/streams/reliability', method: 'GET', params: compactParams(params) }))
}

export async function getOperatorWorkload(params = {}) {
  return normalizeListResponse(await request({ url: '/api/analytics/operators/workload', method: 'GET', params: compactParams(params) }))
}

export async function getSystemPerformance(params = {}) {
  return normalizeItemResponse(await request({ url: '/api/analytics/system/performance', method: 'GET', params: compactParams(params) }))
}

export async function exportAnalytics(payload) {
  return normalizeItemResponse(await request({ url: '/api/analytics/export', method: 'POST', data: payload }))
}
