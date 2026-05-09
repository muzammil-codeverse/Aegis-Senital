import { normalizeItemResponse, normalizeListResponse, request } from './client'

export async function getIncidents(params = {}) {
  return normalizeListResponse(await request({ url: '/api/incidents', method: 'GET', params }))
}

export async function getIncident(incidentId) {
  return normalizeItemResponse(await request({
    url: `/api/incidents/${encodeURIComponent(incidentId)}`,
    method: 'GET',
  }))
}
