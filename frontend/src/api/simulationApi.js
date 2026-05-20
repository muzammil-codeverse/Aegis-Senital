import { normalizeItemResponse, normalizeListResponse, request } from './client'

export async function getSimulationCameras({ zone, status } = {}) {
  const params = {}
  if (zone != null) params.zone = zone
  if (status != null) params.status = status
  const payload = await request({ url: '/api/simulation/sources/cameras', method: 'GET', params })
  return normalizeListResponse(payload)
}

export async function getSimulationCamera(cameraId) {
  const payload = await request({
    url: `/api/simulation/sources/cameras/${encodeURIComponent(cameraId)}`,
    method: 'GET',
  })
  return normalizeItemResponse(payload)
}

export async function getSimulationDrones() {
  const payload = await request({ url: '/api/simulation/sources/drones', method: 'GET' })
  return normalizeListResponse(payload)
}

export async function getSimulationDrone(droneId) {
  const payload = await request({
    url: `/api/simulation/sources/drones/${encodeURIComponent(droneId)}`,
    method: 'GET',
  })
  return normalizeItemResponse(payload)
}

export async function getSimulationDashboardFeeds() {
  const payload = await request({ url: '/api/simulation/sources/dashboard-feeds', method: 'GET' })
  return normalizeListResponse(payload)
}

export async function getSimulationSourceSnapshot() {
  const payload = await request({ url: '/api/simulation/sources/snapshot', method: 'GET' })
  return payload || {}
}

export async function postSimulationObservation(observation) {
  const payload = await request({
    url: '/api/simulation/sources/observations',
    method: 'POST',
    data: observation,
  })
  return payload || {}
}
