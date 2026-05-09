import { request } from './client'

export async function getMapState() {
  const payload = await request({ url: '/api/map/state', method: 'GET' })
  return payload?.item || null
}

export async function getMapSites() {
  const payload = await request({ url: '/api/map/sites', method: 'GET' })
  return Array.isArray(payload?.items) ? payload.items : []
}

export async function getMapZones(siteId) {
  const params = siteId ? { site_id: siteId } : {}
  const payload = await request({ url: '/api/map/zones', method: 'GET', params })
  return Array.isArray(payload?.items) ? payload.items : []
}

export async function getMapGeofences() {
  const payload = await request({ url: '/api/map/geofences', method: 'GET' })
  return Array.isArray(payload?.items) ? payload.items : []
}

export async function getMapCameras() {
  const payload = await request({ url: '/api/map/cameras', method: 'GET' })
  return Array.isArray(payload?.items) ? payload.items : []
}

export async function getMapConnections() {
  const payload = await request({ url: '/api/map/connections', method: 'GET' })
  return Array.isArray(payload?.items) ? payload.items : []
}

export async function getMapIncidents() {
  const payload = await request({ url: '/api/map/incidents', method: 'GET' })
  return Array.isArray(payload?.items) ? payload.items : []
}

export async function getMapAlerts() {
  const payload = await request({ url: '/api/map/alerts', method: 'GET' })
  return Array.isArray(payload?.items) ? payload.items : []
}

export async function getMapTopology() {
  const payload = await request({ url: '/api/map/topology', method: 'GET' })
  return payload?.item || null
}
