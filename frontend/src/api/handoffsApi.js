import { request } from './client'

export async function getActiveHandoffs(limit = 100) {
  const payload = await request({ url: '/api/handoffs/active', method: 'GET', params: { limit } })
  return Array.isArray(payload?.items) ? payload.items : []
}

export async function getRecentHandoffs(limit = 100) {
  const payload = await request({ url: '/api/handoffs/recent', method: 'GET', params: { limit } })
  return Array.isArray(payload?.items) ? payload.items : []
}

export async function getHandoff(handoffId) {
  const payload = await request({ url: `/api/handoffs/${encodeURIComponent(handoffId)}`, method: 'GET' })
  return payload?.item || null
}

export async function getHandoffsByIdentity(identityId, limit = 100) {
  const payload = await request({
    url: `/api/handoffs/identity/${encodeURIComponent(identityId)}`,
    method: 'GET',
    params: { limit },
  })
  return Array.isArray(payload?.items) ? payload.items : []
}

export async function getHandoffsByCamera(cameraId, limit = 100) {
  const payload = await request({
    url: `/api/handoffs/camera/${encodeURIComponent(cameraId)}`,
    method: 'GET',
    params: { limit },
  })
  return Array.isArray(payload?.items) ? payload.items : []
}
