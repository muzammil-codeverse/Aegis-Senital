import { act, renderHook } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { useUploadedVideo } from './useUploadedVideo'

vi.mock('../api/uploadedVideoApi', () => ({
  listUploadedVideoSessions: vi.fn().mockRejectedValue({ status: 401, message: 'Please sign in' }),
  getUploadedVideoSession: vi.fn(),
  getUploadedVideoTimeline: vi.fn(),
  getUploadedVideoEvents: vi.fn(),
  getUploadedVideoReport: vi.fn(),
  uploadUploadedVideo: vi.fn(),
  startUploadedVideoProcessing: vi.fn(),
  cancelUploadedVideoProcessing: vi.fn(),
  createCaseFromUploadedVideo: vi.fn(),
}))

describe('useUploadedVideo', () => {
  it('maps session list 401 to scoped auth error text', async () => {
    const { result } = renderHook(() => useUploadedVideo({ enabled: true, pollMs: 0 }))
    await act(async () => {
      await result.current.refreshSessions()
    })
    expect(result.current.error).toContain('Session list unavailable: auth required')
  })
})

