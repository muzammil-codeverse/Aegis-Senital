import { describe, expect, it, vi } from 'vitest'
import { uploadUploadedVideo } from './uploadedVideoApi'

const requestMock = vi.fn()
vi.mock('./client', () => ({
  request: (...args) => requestMock(...args),
  apiClient: { get: vi.fn() },
  normalizeError: e => e?.message || 'error',
}))

describe('uploadedVideoApi', () => {
  it('uploads with multipart file field "file"', async () => {
    requestMock.mockResolvedValueOnce({ session: { session_id: 's1' } })
    const file = new File(['abc'], 'demo.mp4', { type: 'video/mp4' })
    await uploadUploadedVideo(file, { profile: 'demo' })
    const config = requestMock.mock.calls[0][0]
    expect(config.url).toBe('/api/uploaded-videos')
    expect(config.method.toLowerCase()).toBe('post')
    expect(config.data instanceof FormData).toBe(true)
    expect(config.data.get('file')).toBe(file)
  })
})

