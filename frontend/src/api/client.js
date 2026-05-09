import axios from 'axios'
import { API_BASE_URL, REQUEST_TIMEOUT_MS } from '../config'

/**
 * @typedef {Object} ApiListResponse
 * @property {Array} items
 * @property {number} count
 * @property {'ok'|'empty'|'error'} status
 * @property {string=} error
 */

/**
 * @typedef {Object} ApiItemResponse
 * @property {Object|null} item
 * @property {'ok'|'empty'|'not_found'|'error'} status
 * @property {string=} error
 */

export class ApiError extends Error {
  constructor(message, details = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = details.status
    this.details = details
  }
}

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: REQUEST_TIMEOUT_MS,
  headers: { Accept: 'application/json' },
})

apiClient.interceptors.response.use(
  response => response,
  error => {
    const status = error.response?.status
    const message =
      error.response?.data?.detail ||
      error.response?.data?.error ||
      error.message ||
      'Backend request failed'
    throw new ApiError(message, {
      status,
      url: error.config?.url,
      method: error.config?.method,
      payload: error.response?.data,
    })
  },
)

export async function request(config) {
  const response = await apiClient.request(config)
  return response.data
}

export function normalizeListResponse(payload, fallbackStatus = 'empty') {
  if (Array.isArray(payload)) {
    return { items: payload, count: payload.length, status: payload.length ? 'ok' : fallbackStatus }
  }
  const items = Array.isArray(payload?.items) ? payload.items : []
  return {
    items,
    count: Number.isFinite(payload?.count) ? payload.count : items.length,
    status: payload?.status || (items.length ? 'ok' : fallbackStatus),
  }
}

export function normalizeItemResponse(payload) {
  if (!payload || typeof payload !== 'object') {
    return { item: null, status: 'empty' }
  }
  if ('item' in payload) {
    return { item: payload.item ?? null, status: payload.status || (payload.item ? 'ok' : 'empty') }
  }
  return { item: payload, status: 'ok' }
}

export function normalizeError(error) {
  if (error instanceof ApiError) {
    return error.message
  }
  return error?.message || 'Request failed'
}
