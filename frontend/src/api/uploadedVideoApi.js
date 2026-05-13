import { apiClient, normalizeError, request } from './client'

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
  return request({
    url: '/api/uploaded-videos',
    method: 'post',
    data: formData,
  })
}

export async function getUploadedVideoSession(sessionId) {
  const payload = await request({ url: `/api/uploaded-videos/${encodeURIComponent(sessionId)}`, method: 'get' })
  return payload?.item || null
}

export async function startUploadedVideoProcessing(sessionId) {
  const payload = await request({ url: `/api/uploaded-videos/${encodeURIComponent(sessionId)}/process`, method: 'post' })
  return payload?.item || null
}

export async function getUploadedVideoStatus(sessionId) {
  const payload = await request({ url: `/api/uploaded-videos/${encodeURIComponent(sessionId)}/status`, method: 'get' })
  return payload?.item || null
}

export async function getUploadedVideoTimeline(sessionId) {
  const payload = await request({ url: `/api/uploaded-videos/${encodeURIComponent(sessionId)}/timeline`, method: 'get' })
  return Array.isArray(payload?.items) ? payload.items : []
}

export async function getUploadedVideoEvents(sessionId) {
  const payload = await request({ url: `/api/uploaded-videos/${encodeURIComponent(sessionId)}/events`, method: 'get' })
  return Array.isArray(payload?.items) ? payload.items : []
}

export async function cancelUploadedVideoProcessing(sessionId) {
  const payload = await request({ url: `/api/uploaded-videos/${encodeURIComponent(sessionId)}/cancel`, method: 'post' })
  return payload?.item || null
}

export async function createCaseFromUploadedVideo(sessionId, body = {}) {
  const payload = await request({
    url: `/api/uploaded-videos/${encodeURIComponent(sessionId)}/create-case`,
    method: 'post',
    data: body,
  })
  return payload?.item || null
}

export async function getUploadedVideoReport(sessionId) {
  const payload = await request({ url: `/api/uploaded-videos/${encodeURIComponent(sessionId)}/report`, method: 'get' })
  return payload?.item || null
}

export async function fetchUploadedVideoClipBlob(sessionId, eventId) {
  const url = `/api/uploaded-videos/${encodeURIComponent(sessionId)}/clips/${encodeURIComponent(eventId)}/download`
  const response = await apiClient.get(url, { responseType: 'blob' })
  return response.data
}

export function uploadedVideoError(error) {
  return normalizeError(error)
}
