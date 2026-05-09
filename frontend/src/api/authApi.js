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

export async function changePassword(currentPassword, newPassword) {
  return request({
    url: '/api/auth/change-password',
    method: 'POST',
    data: {
      current_password: currentPassword,
      new_password: newPassword,
    },
  })
}
