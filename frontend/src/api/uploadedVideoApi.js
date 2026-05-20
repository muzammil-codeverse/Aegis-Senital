import { apiClient, normalizeError, request } from './client'

function unwrapItem(payload, fallback = null) {
  if (!payload || typeof payload !== 'object') return fallback
  if ('item' in payload) return payload.item ?? fallback
  if ('session' in payload) return payload.session ?? fallback
  if ('report' in payload) return payload.report ?? fallback
  if ('status' in payload && payload.session_id) return payload
  return payload
}

export async function listUploadedVideoSessions() {
  const payload = await request({ url: '/api/uploaded-videos', method: 'get' })
  return {
    items: Array.isArray(payload?.items) ? payload.items : [],
    count: Number.isFinite(payload?.count) ? payload.count : Array.isArray(payload?.items) ? payload.items.length : 0,
    status: payload?.status || 'empty',
  }
}

export async function uploadUploadedVideo(file, options = {}) {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('options', JSON.stringify(options))
  const payload = await request({
    url: '/api/uploaded-videos',
    method: 'post',
    data: formData,
  })
  return {
    session: unwrapItem(payload, null),
    status: payload?.status || payload?.session?.status || 'uploaded',
    detail: payload?.detail || null,
  }
}

export async function getUploadedVideoSession(sessionId) {
  const payload = await request({ url: `/api/uploaded-videos/${encodeURIComponent(sessionId)}`, method: 'get' })
  return unwrapItem(payload, null)
}

export async function startUploadedVideoProcessing(sessionId) {
  const payload = await request({ url: `/api/uploaded-videos/${encodeURIComponent(sessionId)}/process`, method: 'post' })
  return unwrapItem(payload, null)
}

export async function getUploadedVideoStatus(sessionId) {
  const payload = await request({ url: `/api/uploaded-videos/${encodeURIComponent(sessionId)}/status`, method: 'get' })
  return unwrapItem(payload, null)
}

export async function getUploadedVideoTimeline(sessionId) {
  const payload = await request({ url: `/api/uploaded-videos/${encodeURIComponent(sessionId)}/timeline`, method: 'get' })
  return Array.isArray(payload?.items) ? payload.items : []
}

export async function getUploadedVideoEvents(sessionId) {
  const payload = await request({ url: `/api/uploaded-videos/${encodeURIComponent(sessionId)}/events`, method: 'get' })
  return Array.isArray(payload?.items) ? payload.items : []
}

export async function getUploadedVideoCommandCenterLinks(sessionId) {
  const payload = await request({ url: `/api/uploaded-videos/${encodeURIComponent(sessionId)}/command-center`, method: 'get' })
  return unwrapItem(payload, null)
}

export async function cancelUploadedVideoProcessing(sessionId) {
  const payload = await request({ url: `/api/uploaded-videos/${encodeURIComponent(sessionId)}/cancel`, method: 'post' })
  return unwrapItem(payload, null)
}

export async function createCaseFromUploadedVideo(sessionId, body = {}) {
  const payload = await request({
    url: `/api/uploaded-videos/${encodeURIComponent(sessionId)}/create-case`,
    method: 'post',
    data: body,
  })
  return unwrapItem(payload, null)
}

export async function getUploadedVideoReport(sessionId) {
  const payload = await request({ url: `/api/uploaded-videos/${encodeURIComponent(sessionId)}/report`, method: 'get' })
  return unwrapItem(payload, null)
}

export async function fetchUploadedVideoClipBlob(sessionId, eventId) {
  const url = `/api/uploaded-videos/${encodeURIComponent(sessionId)}/clips/${encodeURIComponent(eventId)}/download`
  const response = await apiClient.get(url, { responseType: 'blob' })
  return response.data
}

export function uploadedVideoError(error) {
  return normalizeError(error)
}
