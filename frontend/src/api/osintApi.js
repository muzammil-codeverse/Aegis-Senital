import { normalizeItemResponse, normalizeListResponse, request } from './client'

export async function createSource(caseId, payload) {
  return normalizeItemResponse(await request({
    url: `/api/cases/${encodeURIComponent(caseId)}/enrichment/sources`,
    method: 'POST',
    data: payload,
  }))
}

export async function listSources(caseId) {
  return normalizeListResponse(await request({
    url: `/api/cases/${encodeURIComponent(caseId)}/enrichment/sources`,
    method: 'GET',
  }))
}

export async function addExternalLink(caseId, payload) {
  return normalizeItemResponse(await request({
    url: `/api/cases/${encodeURIComponent(caseId)}/enrichment/links`,
    method: 'POST',
    data: payload,
  }))
}

export async function uploadDocument(caseId, file, metadata = {}) {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('title', metadata.title || '')
  formData.append('description', metadata.description || '')
  formData.append('source_reliability', metadata.source_reliability || 'unknown')
  formData.append('metadata', JSON.stringify(metadata.metadata || {}))
  return normalizeItemResponse(await request({
    url: `/api/cases/${encodeURIComponent(caseId)}/enrichment/upload`,
    method: 'POST',
    data: formData,
    headers: { 'Content-Type': 'multipart/form-data' },
  }))
}

export async function updateSource(caseId, sourceId, payload) {
  return normalizeItemResponse(await request({
    url: `/api/cases/${encodeURIComponent(caseId)}/enrichment/sources/${encodeURIComponent(sourceId)}`,
    method: 'PATCH',
    data: payload,
  }))
}

export async function deleteSource(caseId, sourceId) {
  return normalizeItemResponse(await request({
    url: `/api/cases/${encodeURIComponent(caseId)}/enrichment/sources/${encodeURIComponent(sourceId)}`,
    method: 'DELETE',
  }))
}

export async function summarizeEnrichment(caseId, payload = {}) {
  return normalizeItemResponse(await request({
    url: `/api/cases/${encodeURIComponent(caseId)}/enrichment/summarize`,
    method: 'POST',
    data: payload,
  }))
}

export async function listSummaries(caseId) {
  return normalizeListResponse(await request({
    url: `/api/cases/${encodeURIComponent(caseId)}/enrichment/summaries`,
    method: 'GET',
  }))
}
