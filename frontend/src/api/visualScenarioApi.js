import { apiClient } from './client'
import { API_BASE_URL } from '../config'

const BASE = '/api/visual-scenario'

export async function getVisualScenarioStatus() {
  const res = await apiClient.get(`${BASE}/status`)
  return res.data?.controller ?? null
}

export async function getVisualSyncStatus() {
  const res = await apiClient.get(`${BASE}/sync-status`)
  return res.data?.sync ?? null
}

export async function setupVisualScene() {
  const res = await apiClient.post(`${BASE}/setup`)
  return res.data
}

export async function startVisualAnimation({ duration_seconds = 65, real_time_factor = 1 } = {}) {
  const res = await apiClient.post(`${BASE}/animate`, { duration_seconds, real_time_factor })
  return res.data
}

export async function stopVisualAnimation() {
  const res = await apiClient.post(`${BASE}/stop`)
  return res.data
}

export async function flushVisualScene() {
  const res = await apiClient.post(`${BASE}/flush`)
  return res.data
}

export async function startVisualDemo({ scenario_run_id = null, duration_seconds = 65 } = {}) {
  const res = await apiClient.post(`${BASE}/demo/start`, { scenario_run_id, duration_seconds })
  return res.data
}

export async function stopVisualDemo({ flush_markers = false } = {}) {
  const res = await apiClient.post(`${BASE}/demo/stop`, { flush_markers })
  return res.data
}

export async function syncVisualToOffset({ t_offset_seconds, camera_id = null, capture_snapshot = null } = {}) {
  const res = await apiClient.post(`${BASE}/sync`, { t_offset_seconds, camera_id, capture_snapshot })
  return res.data?.result ?? res.data
}

export async function syncVisualFromStep(stepPayload) {
  const res = await apiClient.post(`${BASE}/sync-step`, stepPayload || {})
  return res.data?.result ?? res.data
}

export async function getRealActorMode() {
  const res = await apiClient.get(`${BASE}/real-actor-mode`)
  return res.data ?? null
}

export async function listVisualCameras() {
  const res = await apiClient.get(`${BASE}/cameras`)
  return res.data?.cameras ?? []
}

export async function captureCameraSnapshot(camera_id) {
  const res = await apiClient.post(`${BASE}/cameras/${encodeURIComponent(camera_id)}/snapshot`)
  return res.data
}

export async function captureAllSnapshots() {
  const res = await apiClient.post(`${BASE}/cameras/snapshot-all`)
  return res.data
}

/** Build a URL the dashboard can use as an <img src=…> for a saved snapshot. */
export function snapshotImageUrl(camera_id, cacheBust = null) {
  const base = API_BASE_URL ? API_BASE_URL.replace(/\/$/, '') : ''
  const stamp = cacheBust ? `?t=${encodeURIComponent(String(cacheBust))}` : ''
  return `${base}${BASE}/snapshots/${encodeURIComponent(camera_id)}${stamp}`
}
