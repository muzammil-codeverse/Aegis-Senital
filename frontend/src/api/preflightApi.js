import { request } from './client'

function unwrapItem(payload, fallback = null) {
  if (!payload || typeof payload !== 'object') return fallback
  if ('item' in payload) return payload.item ?? fallback
  return payload
}

export async function getLatestPreflight() {
  const payload = await request({ url: '/api/preflight/latest', method: 'GET', timeout: 12000 })
  return unwrapItem(payload, { overall_status: 'NOT_STARTED', results: [] })
}

export async function runPreflight(mode = 'QUICK', selectedCapabilities = undefined) {
  const payload = await request({
    url: '/api/preflight/run',
    method: 'POST',
    timeout: mode === 'EXHIBITION' ? 45000 : 20000,
    data: {
      mode,
      ...(Array.isArray(selectedCapabilities) ? { selected_capabilities: selectedCapabilities } : {}),
    },
  })
  return unwrapItem(payload, null)
}

export async function getPreflightRun(runId) {
  const payload = await request({
    url: `/api/preflight/runs/${encodeURIComponent(runId)}`,
    method: 'GET',
    timeout: 12000,
  })
  return unwrapItem(payload, null)
}

export async function getPreflightSummary() {
  const payload = await request({ url: '/api/preflight/summary', method: 'GET', timeout: 12000 })
  return unwrapItem(payload, {})
}

export async function checkPreflightCapability(capabilityId) {
  const payload = await request({
    url: `/api/preflight/capabilities/${encodeURIComponent(capabilityId)}/check`,
    method: 'POST',
    timeout: 20000,
  })
  return unwrapItem(payload, null)
}

export async function getPreflightModes() {
  const payload = await request({ url: '/api/preflight/modes', method: 'GET', timeout: 12000 })
  return Array.isArray(payload?.items) ? payload.items : []
}

