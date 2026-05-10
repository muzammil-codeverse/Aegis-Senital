import { normalizeItemResponse, request } from './client'

export async function getLlmStatus() {
  return normalizeItemResponse(await request({
    url: '/api/llm/status',
    method: 'GET',
  }))
}

export async function verifyLlmProvider(payload = {}) {
  return normalizeItemResponse(await request({
    url: '/api/llm/verify-provider',
    method: 'POST',
    data: payload,
  }))
}

export async function summarizeCase(caseId, payload = {}) {
  return normalizeItemResponse(await request({
    url: `/api/llm/cases/${encodeURIComponent(caseId)}/summary`,
    method: 'POST',
    data: payload,
  }))
}

export async function summarizeTimeline(caseId, payload = {}) {
  return normalizeItemResponse(await request({
    url: `/api/llm/cases/${encodeURIComponent(caseId)}/timeline-summary`,
    method: 'POST',
    data: payload,
  }))
}

export async function summarizeEvidence(caseId, payload = {}) {
  return normalizeItemResponse(await request({
    url: `/api/llm/cases/${encodeURIComponent(caseId)}/evidence-summary`,
    method: 'POST',
    data: payload,
  }))
}

export async function draftCaseReport(caseId, payload = {}) {
  return normalizeItemResponse(await request({
    url: `/api/llm/cases/${encodeURIComponent(caseId)}/report`,
    method: 'POST',
    data: payload,
  }))
}

export async function askCaseQuestion(caseId, payload) {
  return normalizeItemResponse(await request({
    url: `/api/llm/cases/${encodeURIComponent(caseId)}/query`,
    method: 'POST',
    data: payload,
  }))
}
