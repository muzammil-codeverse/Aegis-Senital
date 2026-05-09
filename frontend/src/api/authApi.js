import { request } from './client'

export async function login(username, password) {
  return request({
    url: '/api/auth/login',
    method: 'POST',
    data: { username, password },
  })
}

export async function logout() {
  return request({ url: '/api/auth/logout', method: 'POST' })
}

export async function getMe() {
  return request({ url: '/api/auth/me', method: 'GET' })
}
