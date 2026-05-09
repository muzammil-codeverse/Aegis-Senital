import { normalizeItemResponse, request } from './client'

export async function getCameraHeatmap(cameraId) {
  return normalizeItemResponse(await request({
    url: `/api/cameras/${encodeURIComponent(cameraId)}/heatmap`,
    method: 'GET',
  }))
}

export async function getLiveAnomalies() {
  const payload = await request({ url: '/api/anomalies/live', method: 'GET' })
  const items = Array.isArray(payload?.items) ? payload.items : []
  return { items, count: Number.isFinite(payload?.count) ? payload.count : items.length, status: payload?.status || (items.length ? 'ok' : 'empty') }
}
