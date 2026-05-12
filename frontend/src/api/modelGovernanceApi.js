import { apiClient } from './client.js'

export async function fetchGovernanceRegistry() {
  const res = await apiClient.get('/api/model-governance/registry')
  return res.data
}

export async function fetchGovernanceActive() {
  const res = await apiClient.get('/api/model-governance/active')
  return res.data
}

export async function fetchGovernanceLimitations() {
  const res = await apiClient.get('/api/model-governance/limitations')
  return res.data
}

export async function fetchPromotionPolicy() {
  const res = await apiClient.get('/api/model-governance/promotion-policy')
  return res.data
}

export async function postGovernanceValidate(body = {}) {
  const res = await apiClient.post('/api/model-governance/validate', body)
  return res.data
}

export async function postGovernanceRollback(payload) {
  const res = await apiClient.post('/api/model-governance/rollback', payload)
  return res.data
}

export async function fetchDrift(modelId) {
  const res = await apiClient.get(`/api/model-governance/drift/${encodeURIComponent(modelId)}`)
  return res.data
}
