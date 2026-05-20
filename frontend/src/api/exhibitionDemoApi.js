import { apiClient } from './client'

const BASE = '/api/exhibition-demo'

export async function getDemoStatus() {
  const res = await apiClient.get(`${BASE}/status`)
  return res.data?.item ?? null
}

export async function resetDemo() {
  const res = await apiClient.post(`${BASE}/reset`)
  return res.data
}

export async function startDemo({ mode = 'step', run_preflight = false } = {}) {
  const res = await apiClient.post(`${BASE}/start`, { mode, run_preflight })
  return res.data
}

export async function stepDemo() {
  const res = await apiClient.post(`${BASE}/step`)
  return res.data
}

export async function autoRunDemo() {
  const res = await apiClient.post(`${BASE}/auto-run`)
  return res.data
}

export async function cancelDemo() {
  const res = await apiClient.post(`${BASE}/cancel`)
  return res.data
}

export async function getDemoSnapshot() {
  const res = await apiClient.get(`${BASE}/snapshot`)
  return res.data?.item ?? null
}

export async function getDemoRunbook() {
  const res = await apiClient.get(`${BASE}/runbook`)
  return res.data?.item ?? null
}

export async function getDemoFallback() {
  const res = await apiClient.get(`${BASE}/fallback`)
  return res.data?.item ?? null
}
