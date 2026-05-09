import { request } from './client'

export async function getCoreMetrics() {
  const payload = await request({ url: '/metrics/core', method: 'GET' })
  return payload && typeof payload === 'object' ? payload : {}
}
