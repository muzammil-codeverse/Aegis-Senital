import { apiClient, normalizeItemResponse, normalizeListResponse, request } from './client'

export async function listCases(params = {}) {
  return normalizeListResponse(await request({ url: '/api/cases', method: 'GET', params }))
}

export async function getCase(caseId) {
  return normalizeItemResponse(await request({
    url: `/api/cases/${encodeURIComponent(caseId)}`,
    method: 'GET',
  }))
}

export async function createCase(payload) {
  return normalizeItemResponse(await request({
    url: '/api/cases',
    method: 'POST',
    data: payload,
  }))
}

export async function updateCase(caseId, payload) {
  return normalizeItemResponse(await request({
    url: `/api/cases/${encodeURIComponent(caseId)}`,
    method: 'PATCH',
    data: payload,
  }))
}

export async function createCaseFromEvent(eventId) {
  return normalizeItemResponse(await request({
    url: `/api/cases/from-event/${encodeURIComponent(eventId)}`,
    method: 'POST',
  }))
}

export async function addEvidence(caseId, payload) {
  return normalizeItemResponse(await request({
    url: `/api/cases/${encodeURIComponent(caseId)}/evidence`,
    method: 'POST',
    data: payload,
  }))
}

export async function listEvidence(caseId) {
  return normalizeListResponse(await request({
    url: `/api/cases/${encodeURIComponent(caseId)}/evidence`,
    method: 'GET',
  }))
}

export async function uploadEvidenceFile(caseId, formData) {
  return normalizeItemResponse(await request({
    url: `/api/cases/${encodeURIComponent(caseId)}/evidence/upload`,
    method: 'POST',
    data: formData,
    headers: { 'Content-Type': 'multipart/form-data' },
  }))
}

export async function verifyEvidenceFile(caseId, evidenceId) {
  return normalizeItemResponse(await request({
    url: `/api/cases/${encodeURIComponent(caseId)}/evidence/${encodeURIComponent(evidenceId)}/verify`,
    method: 'POST',
  }))
}

export async function getEvidenceManifest(caseId) {
  return normalizeItemResponse(await request({
    url: `/api/cases/${encodeURIComponent(caseId)}/evidence/manifest`,
    method: 'GET',
  }))
}

export async function downloadEvidenceFile(caseId, evidenceId) {
  const response = await apiClient.request({
    url: `/api/cases/${encodeURIComponent(caseId)}/evidence/${encodeURIComponent(evidenceId)}/download`,
    method: 'GET',
    responseType: 'blob',
  })
  const disposition = response.headers['content-disposition'] || ''
  const match = disposition.match(/filename=\"?([^"]+)\"?/)
  return {
    blob: response.data,
    filename: match?.[1] || `${evidenceId}`,
    contentType: response.headers['content-type'] || response.data?.type || 'application/octet-stream',
  }
}

export async function addNote(caseId, payload) {
  return normalizeItemResponse(await request({
    url: `/api/cases/${encodeURIComponent(caseId)}/notes`,
    method: 'POST',
    data: payload,
  }))
}

export async function listNotes(caseId) {
  return normalizeListResponse(await request({
    url: `/api/cases/${encodeURIComponent(caseId)}/notes`,
    method: 'GET',
  }))
}

export async function assignCase(caseId, assignedTo, reason = '') {
  return normalizeItemResponse(await request({
    url: `/api/cases/${encodeURIComponent(caseId)}/assign`,
    method: 'POST',
    data: { assigned_to: assignedTo, reason },
  }))
}

export async function closeCase(caseId, reason = '') {
  return normalizeItemResponse(await request({
    url: `/api/cases/${encodeURIComponent(caseId)}/close`,
    method: 'POST',
    data: { reason },
  }))
}

export async function reopenCase(caseId, reason = '') {
  return normalizeItemResponse(await request({
    url: `/api/cases/${encodeURIComponent(caseId)}/reopen`,
    method: 'POST',
    data: { reason },
  }))
}

export async function dismissCase(caseId, reason = '') {
  return normalizeItemResponse(await request({
    url: `/api/cases/${encodeURIComponent(caseId)}/dismiss`,
    method: 'POST',
    data: { reason },
  }))
}

export async function archiveCase(caseId, reason = '') {
  return normalizeItemResponse(await request({
    url: `/api/cases/${encodeURIComponent(caseId)}/archive`,
    method: 'POST',
    data: { reason },
  }))
}

export async function getTimeline(caseId) {
  return normalizeListResponse(await request({
    url: `/api/cases/${encodeURIComponent(caseId)}/timeline`,
    method: 'GET',
  }))
}

export async function exportCase(caseId, format = 'json') {
  return normalizeItemResponse(await request({
    url: `/api/cases/${encodeURIComponent(caseId)}/export`,
    method: 'GET',
    params: { format },
  }))
}
