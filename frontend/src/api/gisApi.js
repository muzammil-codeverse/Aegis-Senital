import { normalizeItemResponse, normalizeListResponse, request } from './client'

function compactParams(params = {}) {
  return Object.fromEntries(
    Object.entries(params).filter(([, value]) => value !== null && value !== undefined && value !== ''),
  )
}

export async function getGisConfig() {
  return normalizeItemResponse(await request({ url: '/api/gis/config', method: 'GET' }))
}

export async function getGisCameras() {
  return normalizeListResponse(await request({ url: '/api/gis/cameras', method: 'GET' }))
}

export async function getCameraGeoProfile(cameraId) {
  return normalizeItemResponse(await request({ url: `/api/gis/cameras/${encodeURIComponent(cameraId)}`, method: 'GET' }))
}

export async function updateCameraGeoProfile(cameraId, payload) {
  return normalizeItemResponse(
    await request({ url: `/api/gis/cameras/${encodeURIComponent(cameraId)}`, method: 'PUT', data: payload }),
  )
}

export async function getCameraFov(cameraId) {
  return normalizeItemResponse(await request({ url: `/api/gis/cameras/${encodeURIComponent(cameraId)}/fov`, method: 'GET' }))
}

export async function getNearbyCameras(params = {}) {
  return normalizeListResponse(await request({ url: '/api/gis/nearby-cameras', method: 'GET', params: compactParams(params) }))
}

export async function getGisEvents(params = {}) {
  return normalizeListResponse(await request({ url: '/api/gis/events', method: 'GET', params: compactParams(params) }))
}

export async function getGisCases(params = {}) {
  return normalizeListResponse(await request({ url: '/api/gis/cases', method: 'GET', params: compactParams(params) }))
}

export async function getGisHeatmap(params = {}) {
  return normalizeListResponse(await request({ url: '/api/gis/heatmap', method: 'GET', params: compactParams(params) }))
}

export async function getGisLayers(params = {}) {
  return normalizeItemResponse(await request({ url: '/api/gis/layers', method: 'GET', params: compactParams(params) }))
}

export async function getGeofences() {
  return normalizeListResponse(await request({ url: '/api/gis/geofences', method: 'GET' }))
}

export async function createGeofence(payload) {
  return normalizeItemResponse(await request({ url: '/api/gis/geofences', method: 'POST', data: payload }))
}

export async function updateGeofence(zoneId, payload) {
  return normalizeItemResponse(
    await request({ url: `/api/gis/geofences/${encodeURIComponent(zoneId)}`, method: 'PATCH', data: payload }),
  )
}

export async function deleteGeofence(zoneId) {
  return request({ url: `/api/gis/geofences/${encodeURIComponent(zoneId)}`, method: 'DELETE' })
}
