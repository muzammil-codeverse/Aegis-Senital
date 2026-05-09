import { request } from './client'

export async function getCoreMetrics() {
  const payload = await request({ url: '/metrics/core', method: 'GET' })
  return payload && typeof payload === 'object' ? payload : {}
}

/**
 * Get detailed subsystem health from the backend health service.
 * Returns status, checks (database, redis, gpu, open_vocab, storage,
 * model_registry, event_bus, security), and generated_at timestamp.
 * @returns {Promise<Object>}
 */
export async function getSystemHealth() {
  try {
    const payload = await request({ url: '/api/system/health', method: 'GET' })
    return payload && typeof payload === 'object' ? payload : { status: 'unknown', checks: {} }
  } catch (e) {
    return { status: 'error', checks: {}, error: e?.message || 'Health endpoint unavailable' }
  }
}

/**
 * Get system readiness state from the readiness probe endpoint.
 * Returns ready (boolean), failures (array), and generated_at.
 * @returns {Promise<Object>}
 */
export async function getSystemReadiness() {
  try {
    const payload = await request({ url: '/api/system/readiness', method: 'GET' })
    return payload && typeof payload === 'object' ? payload : { ready: false, failures: [] }
  } catch (e) {
    return { ready: false, failures: [e?.message || 'Readiness endpoint unavailable'] }
  }
}
