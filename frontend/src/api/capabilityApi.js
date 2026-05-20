import { request } from './client'

function normalizeCapabilityItems(payload) {
  if (Array.isArray(payload)) return payload
  return Array.isArray(payload?.items) ? payload.items : []
}

export async function getCapabilities() {
  const payload = await request({ url: '/api/capabilities', method: 'GET', timeout: 12000 })
  return {
    items: normalizeCapabilityItems(payload),
    count: Number.isFinite(payload?.count) ? payload.count : normalizeCapabilityItems(payload).length,
    dependencies: payload?.dependencies || {},
    status: payload?.status || 'ok',
  }
}

export async function getCapabilitySummary() {
  const payload = await request({ url: '/api/capabilities/summary', method: 'GET', timeout: 12000 })
  return payload?.item || payload || {}
}

export async function refreshCapabilities() {
  const payload = await request({ url: '/api/capabilities/refresh', method: 'POST', timeout: 15000 })
  return {
    items: normalizeCapabilityItems(payload),
    count: Number.isFinite(payload?.count) ? payload.count : normalizeCapabilityItems(payload).length,
    summary: payload?.summary || {},
    status: payload?.status || 'ok',
  }
}

export async function checkCapability(capabilityId) {
  const payload = await request({
    url: `/api/capabilities/${encodeURIComponent(capabilityId)}/check`,
    method: 'POST',
    timeout: 12000,
  })
  return payload?.item || payload || null
}
