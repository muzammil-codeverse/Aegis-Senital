import { normalizeItemResponse, normalizeListResponse, request } from './client'

export async function getCameras({ status, enabled } = {}) {
  const params = {}
  if (status != null) params.status = status
  if (enabled != null) params.enabled = enabled
  const payload = await request({ url: '/api/cameras', method: 'GET', params })
  return normalizeListResponse(payload)
}

export async function getCamera(cameraId) {
  const payload = await request({ url: `/api/cameras/${encodeURIComponent(cameraId)}`, method: 'GET' })
  return normalizeItemResponse(payload)
}

export async function createCamera(data) {
  const payload = await request({ url: '/api/cameras', method: 'POST', data })
  return normalizeItemResponse(payload)
}

export async function updateCamera(cameraId, data) {
  const payload = await request({ url: `/api/cameras/${encodeURIComponent(cameraId)}`, method: 'PATCH', data })
  return normalizeItemResponse(payload)
}

export async function deleteCamera(cameraId) {
  const payload = await request({ url: `/api/cameras/${encodeURIComponent(cameraId)}`, method: 'DELETE' })
  return normalizeItemResponse(payload)
}

export async function getCameraStatus(cameraId) {
  const payload = await request({ url: `/api/cameras/${encodeURIComponent(cameraId)}/status`, method: 'GET' })
  return normalizeItemResponse(payload)
}

export async function startCamera(cameraId) {
  const payload = await request({ url: `/api/cameras/${encodeURIComponent(cameraId)}/start`, method: 'POST' })
  return normalizeItemResponse(payload)
}

export async function stopCamera(cameraId) {
  const payload = await request({ url: `/api/cameras/${encodeURIComponent(cameraId)}/stop`, method: 'POST' })
  return normalizeItemResponse(payload)
}

export async function pauseCamera(cameraId) {
  const payload = await request({ url: `/api/cameras/${encodeURIComponent(cameraId)}/pause`, method: 'POST' })
  return normalizeItemResponse(payload)
}

export async function resumeCamera(cameraId) {
  const payload = await request({ url: `/api/cameras/${encodeURIComponent(cameraId)}/resume`, method: 'POST' })
  return normalizeItemResponse(payload)
}

export async function restartCamera(cameraId) {
  const payload = await request({ url: `/api/cameras/${encodeURIComponent(cameraId)}/restart`, method: 'POST' })
  return normalizeItemResponse(payload)
}

export async function getStreams() {
  const payload = await request({ url: '/api/streams', method: 'GET' })
  return normalizeListResponse(payload)
}

export async function getStream(cameraId) {
  const payload = await request({ url: `/api/streams/${encodeURIComponent(cameraId)}`, method: 'GET' })
  return normalizeItemResponse(payload)
}

export async function getLatestFrame(cameraId) {
  const payload = await request({ url: `/api/cameras/${encodeURIComponent(cameraId)}/latest-frame`, method: 'GET' })
  return normalizeItemResponse(payload)
}

export async function getLatestFrames() {
  const payload = await request({ url: '/api/cameras/latest-frames', method: 'GET' })
  return normalizeListResponse(payload)
}

export async function getCameraHeatmap(cameraId) {
  return normalizeItemResponse(await request({
    url: `/api/cameras/${encodeURIComponent(cameraId)}/heatmap`,
    method: 'GET',
  }))
}

export async function getCameraTimeline(cameraId, { startTime, endTime, limit } = {}) {
  const params = {}
  if (startTime != null) params.start_time = startTime
  if (endTime != null) params.end_time = endTime
  if (limit != null) params.limit = limit
  const payload = await request({ url: `/api/cameras/${encodeURIComponent(cameraId)}/timeline`, method: 'GET', params })
  const items = Array.isArray(payload?.items) ? payload.items : []
  return { items, count: items.length, camera_id: cameraId }
}

export async function getIncidentReplay(incidentId) {
  const payload = await request({ url: `/api/incidents/${encodeURIComponent(incidentId)}/replay`, method: 'GET' })
  return payload || {}
}

export async function getLiveAnomalies() {
  const payload = await request({ url: '/api/anomalies/live', method: 'GET' })
  const items = Array.isArray(payload?.items) ? payload.items : []
  return { items, count: Number.isFinite(payload?.count) ? payload.count : items.length, status: payload?.status || (items.length ? 'ok' : 'empty') }
}
