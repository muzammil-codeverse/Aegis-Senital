import { normalizeItemResponse, normalizeListResponse, request } from './client'

export async function getUsers(params = {}) {
  return normalizeListResponse(await request({ url: '/api/security/users', method: 'GET', params }))
}

export async function createUser(payload) {
  return normalizeItemResponse(await request({ url: '/api/security/users', method: 'POST', data: payload }))
}

export async function updateUser(userId, payload) {
  return normalizeItemResponse(await request({
    url: `/api/security/users/${encodeURIComponent(userId)}`,
    method: 'PATCH',
    data: payload,
  }))
}

export async function disableUser(userId) {
  return normalizeItemResponse(await request({
    url: `/api/security/users/${encodeURIComponent(userId)}/disable`,
    method: 'POST',
  }))
}

export async function lockUser(userId) {
  return normalizeItemResponse(await request({
    url: `/api/security/users/${encodeURIComponent(userId)}/lock`,
    method: 'POST',
  }))
}

export async function resetUserPassword(userId, payload) {
  return normalizeItemResponse(await request({
    url: `/api/security/users/${encodeURIComponent(userId)}/reset-password`,
    method: 'POST',
    data: payload,
  }))
}

export async function getRoles() {
  return normalizeListResponse(await request({ url: '/api/security/roles', method: 'GET' }))
}
