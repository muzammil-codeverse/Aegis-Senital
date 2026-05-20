import { request } from './client'

const BASE = '/api/drone-unified'

export async function getUnifiedFleet() {
  const data = await request({ url: `${BASE}/fleet`, method: 'GET' })
  return data?.item ?? null
}

export async function getUnifiedDrone(droneId) {
  const data = await request({ url: `${BASE}/drones/${encodeURIComponent(droneId)}`, method: 'GET' })
  return data?.item ?? null
}
