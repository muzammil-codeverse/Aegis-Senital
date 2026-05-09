import { normalizeItemResponse, normalizeListResponse, request } from './client'

export async function getAlerts(params = {}) {
  return normalizeListResponse(await request({ url: '/api/alerts', method: 'GET', params }))
}

export async function getLiveAlerts(params = {}) {
  return normalizeListResponse(await request({ url: '/api/alerts/live', method: 'GET', params }))
}

export async function getAlert(alertId) {
  return normalizeItemResponse(await request({ url: `/api/alerts/${encodeURIComponent(alertId)}`, method: 'GET' }))
}

export async function acknowledgeAlert(alertId, operatorId) {
  return normalizeItemResponse(await request({
    url: `/api/alerts/${encodeURIComponent(alertId)}/acknowledge`,
    method: 'POST',
    data: { operator_id: operatorId || null },
  }))
}

export async function resolveAlert(alertId, operatorId) {
  return normalizeItemResponse(await request({
    url: `/api/alerts/${encodeURIComponent(alertId)}/resolve`,
    method: 'POST',
    data: { operator_id: operatorId || null },
  }))
}

export async function escalateAlert(alertId, reason) {
  return normalizeItemResponse(await request({
    url: `/api/alerts/${encodeURIComponent(alertId)}/escalate`,
    method: 'POST',
    data: { reason: reason || null },
  }))
}

export async function getAlertHistory(alertId) {
  return normalizeListResponse(await request({
    url: `/api/alerts/${encodeURIComponent(alertId)}/history`,
    method: 'GET',
  }))
}
