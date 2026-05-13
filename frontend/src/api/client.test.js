import { describe, expect, it } from 'vitest'
import { ApiError, classifyApiError, normalizeError } from './client'

describe('api client error classification', () => {
  it('classifies network failures cleanly', () => {
    const classified = classifyApiError({ message: 'Network Error' })
    expect(classified.kind).toBe('network')
    expect(classified.message.toLowerCase()).toContain('backend unavailable')
  })

  it('classifies auth and permission errors', () => {
    expect(classifyApiError({ response: { status: 401 } }).kind).toBe('unauthenticated')
    expect(classifyApiError({ response: { status: 403 } }).kind).toBe('forbidden')
  })

  it('normalizes ApiError output for user-safe messaging', () => {
    const err = new ApiError('Please sign in to continue.', { status: 401, kind: 'unauthenticated' })
    expect(normalizeError(err)).toBe('Please sign in to continue.')
  })
})
