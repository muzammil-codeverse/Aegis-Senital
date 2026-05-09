import { normalizeItemResponse, normalizeListResponse, request, apiClient } from './client'

// ── Open-Vocabulary Threat Scanner API ────────────────────────────────────────

/**
 * Get open-vocabulary scanner status and metrics.
 * @returns {Promise<{item: Object|null, status: string}>}
 */
export async function getOpenVocabStatus() {
  return normalizeItemResponse(await request({ url: '/api/open-vocab/status', method: 'GET' }))
}

/**
 * List open-vocabulary prompts in the library.
 * @param {Object} [params] - Optional filters: category, enabled
 * @returns {Promise<{items: Array, count: number, status: string}>}
 */
export async function getOpenVocabPrompts(params = {}) {
  return normalizeListResponse(await request({ url: '/api/open-vocab/prompts', method: 'GET', params }))
}

/**
 * Create a new open-vocabulary prompt.
 * @param {{ text: string, category: string, severity?: string, threshold?: number, metadata?: Object }} payload
 * @returns {Promise<{item: Object|null, status: string}>}
 */
export async function createOpenVocabPrompt(payload) {
  return normalizeItemResponse(await request({ url: '/api/open-vocab/prompts', method: 'POST', data: payload }))
}

/**
 * Update an existing open-vocabulary prompt.
 * @param {string} promptId
 * @param {Object} payload - Fields to update
 * @returns {Promise<{item: Object|null, status: string}>}
 */
export async function updateOpenVocabPrompt(promptId, payload) {
  return normalizeItemResponse(await request({
    url: `/api/open-vocab/prompts/${encodeURIComponent(promptId)}`,
    method: 'PATCH',
    data: payload,
  }))
}

/**
 * Disable an open-vocabulary prompt.
 * @param {string} promptId
 * @returns {Promise<{item: Object|null, status: string}>}
 */
export async function disableOpenVocabPrompt(promptId) {
  return normalizeItemResponse(await request({
    url: `/api/open-vocab/prompts/${encodeURIComponent(promptId)}/disable`,
    method: 'POST',
  }))
}

/**
 * Trigger an open-vocabulary scan on the latest frame from a camera.
 * @param {string} cameraId
 * @param {string[]} [prompts] - Optional prompt overrides
 * @returns {Promise<{item: Object|null, status: string}>}
 */
export async function scanLatestFrame(cameraId, prompts) {
  return normalizeItemResponse(await request({
    url: `/api/open-vocab/scan/latest-frame/${encodeURIComponent(cameraId)}`,
    method: 'POST',
    data: prompts?.length ? { prompts } : {},
  }))
}

/**
 * Trigger an open-vocabulary scan on incident frame references.
 * @param {string} incidentId
 * @param {string[]} [prompts] - Optional prompt overrides
 * @returns {Promise<{item: Object|null, status: string}>}
 */
export async function scanIncident(incidentId, prompts) {
  return normalizeItemResponse(await request({
    url: `/api/open-vocab/scan/incident/${encodeURIComponent(incidentId)}`,
    method: 'POST',
    data: prompts?.length ? { prompts } : {},
  }))
}

/**
 * Scan an uploaded image using open-vocabulary prompts.
 * @param {File} file - Image file (.jpg/.jpeg/.png, max 10 MB)
 * @param {string[]} [prompts] - Optional prompt overrides
 * @returns {Promise<{item: Object|null, status: string}>}
 */
export async function scanImage(file, prompts) {
  const fd = new FormData()
  fd.append('file', file)
  if (prompts?.length) {
    fd.append('prompts', JSON.stringify(prompts))
  }
  const response = await apiClient.post('/api/open-vocab/scan/image', fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return normalizeItemResponse(response.data)
}

/**
 * List recent open-vocabulary scan results.
 * @param {Object} [params] - Optional filters: limit
 * @returns {Promise<{items: Array, count: number, status: string}>}
 */
export async function getOpenVocabResults(params = {}) {
  return normalizeListResponse(await request({ url: '/api/open-vocab/results', method: 'GET', params }))
}

/**
 * Get a specific open-vocabulary scan result by scan_id.
 * @param {string} scanId
 * @returns {Promise<{item: Object|null, status: string}>}
 */
export async function getOpenVocabResult(scanId) {
  return normalizeItemResponse(await request({
    url: `/api/open-vocab/results/${encodeURIComponent(scanId)}`,
    method: 'GET',
  }))
}

/**
 * List open-vocabulary scan results for a specific camera.
 * @param {string} cameraId
 * @param {Object} [params] - Optional filters: limit
 * @returns {Promise<{items: Array, count: number, status: string}>}
 */
export async function getOpenVocabResultsByCamera(cameraId, params = {}) {
  return normalizeListResponse(await request({
    url: `/api/open-vocab/results/camera/${encodeURIComponent(cameraId)}`,
    method: 'GET',
    params,
  }))
}

/**
 * List open-vocabulary scan results for a specific incident.
 * @param {string} incidentId
 * @param {Object} [params] - Optional filters: limit
 * @returns {Promise<{items: Array, count: number, status: string}>}
 */
export async function getOpenVocabResultsByIncident(incidentId, params = {}) {
  return normalizeListResponse(await request({
    url: `/api/open-vocab/results/incident/${encodeURIComponent(incidentId)}`,
    method: 'GET',
    params,
  }))
}

// ── Model hot-load control (Phase 24) ─────────────────────────────────────────

/**
 * Trigger a hot-load of the open-vocabulary model adapter.
 * Reads model paths from backend environment variables.
 * Requires open_vocab:write permission.
 * @returns {Promise<{status: string, loaded: boolean, adapter: Object|null}>}
 */
export const loadOpenVocabModel = () => apiClient.post('/api/open-vocab/model/load').then(r => r.data)

/**
 * Unload the open-vocabulary model adapter to free memory.
 * Requires open_vocab:write permission.
 * @returns {Promise<{status: string, loaded: boolean, adapter: Object|null}>}
 */
export const unloadOpenVocabModel = () => apiClient.post('/api/open-vocab/model/unload').then(r => r.data)

/**
 * Unload then re-load the open-vocabulary model adapter (hot-reload).
 * Requires open_vocab:write permission.
 * @returns {Promise<{status: string, loaded: boolean, adapter: Object|null}>}
 */
export const reloadOpenVocabModel = () => apiClient.post('/api/open-vocab/model/reload').then(r => r.data)

/**
 * Get current load status of the open-vocabulary model adapter.
 * Requires open_vocab:read permission.
 * @returns {Promise<{status: string, adapter: Object|null}>}
 */
export const getOpenVocabModelStatus = () => apiClient.get('/api/open-vocab/model/status').then(r => r.data)
