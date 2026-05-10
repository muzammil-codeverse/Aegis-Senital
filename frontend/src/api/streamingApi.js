import { normalizeItemResponse, request } from './client'

export async function getStreamHealth(cameraId) {
  const payload = await request({ url: `/api/streams/${encodeURIComponent(cameraId)}/health`, method: 'GET' })
  return normalizeItemResponse(payload)
}

export async function getStreamStats(cameraId) {
  const payload = await request({ url: `/api/streams/${encodeURIComponent(cameraId)}/stats`, method: 'GET' })
  return normalizeItemResponse(payload)
}

export async function startStream(cameraId) {
  const payload = await request({ url: `/api/streams/${encodeURIComponent(cameraId)}/start`, method: 'POST' })
  return normalizeItemResponse(payload)
}

export async function stopStream(cameraId) {
  const payload = await request({ url: `/api/streams/${encodeURIComponent(cameraId)}/stop`, method: 'POST' })
  return normalizeItemResponse(payload)
}

export async function restartStream(cameraId) {
  const payload = await request({ url: `/api/streams/${encodeURIComponent(cameraId)}/restart`, method: 'POST' })
  return normalizeItemResponse(payload)
}

export async function createWebRTCOffer(cameraId, data) {
  const payload = await request({ url: `/api/streams/${encodeURIComponent(cameraId)}/webrtc/offer`, method: 'POST', data })
  return normalizeItemResponse(payload)
}

export async function stopWebRTCPreview(cameraId) {
  const payload = await request({ url: `/api/streams/${encodeURIComponent(cameraId)}/webrtc/stop`, method: 'POST' })
  return normalizeItemResponse(payload)
}

export async function getWebRTCStatus(cameraId) {
  const payload = await request({ url: `/api/streams/${encodeURIComponent(cameraId)}/webrtc/status`, method: 'GET' })
  return normalizeItemResponse(payload)
}

export function getHlsPlaylistUrl(cameraId) {
  return `/api/streams/${encodeURIComponent(cameraId)}/hls/playlist.m3u8`
}

export function getMjpegStreamUrl(cameraId) {
  return `/api/streams/${encodeURIComponent(cameraId)}/mjpeg`
}

export async function exportReplayClip(cameraId, data) {
  const payload = await request({ url: `/api/streams/${encodeURIComponent(cameraId)}/replay/export`, method: 'POST', data })
  return normalizeItemResponse(payload)
}

export function getReplayClipUrl(cameraId, clipId) {
  return `/api/streams/${encodeURIComponent(cameraId)}/replay/${encodeURIComponent(clipId)}`
}
