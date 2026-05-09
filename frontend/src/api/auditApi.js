import { normalizeListResponse, request } from './client'

export async function getAuditLogs(params = {}) {
  return normalizeListResponse(await request({ url: '/api/audit/logs', method: 'GET', params }))
}

export async function getRecentAuditLogs(limit = 100) {
  return normalizeListResponse(await request({
    url: '/api/audit/recent',
    method: 'GET',
    params: { limit },
  }))
}

export async function getAuditIntegrity() {
  return request({ url: '/api/audit/integrity', method: 'GET' })
}
