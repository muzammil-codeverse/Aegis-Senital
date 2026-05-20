import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as uploadedVideoApi from '../api/uploadedVideoApi'
import { useUploadedVideo } from './useUploadedVideo'

const authGateState = vi.hoisted(() => ({
  enabled: true,
  reason: null,
  message: null,
}))

vi.mock('../api/uploadedVideoApi', () => ({
  listUploadedVideoSessions: vi.fn(),
  getUploadedVideoSession: vi.fn(),
  getUploadedVideoStatus: vi.fn(),
  getUploadedVideoTimeline: vi.fn(),
  getUploadedVideoEvents: vi.fn(),
  getUploadedVideoReport: vi.fn(),
  uploadUploadedVideo: vi.fn(),
  startUploadedVideoProcessing: vi.fn(),
  cancelUploadedVideoProcessing: vi.fn(),
  createCaseFromUploadedVideo: vi.fn(),
}))

vi.mock('./useAuthenticatedQuery', () => ({
  useAuthGate: (_permission, { enabled = true } = {}) => ({
    ...authGateState,
    enabled: Boolean(enabled && authGateState.enabled),
    reason: enabled ? authGateState.reason : 'disabled',
    message: enabled ? authGateState.message : null,
  }),
}))

describe('useUploadedVideo', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    authGateState.enabled = true
    authGateState.reason = null
    authGateState.message = null
    uploadedVideoApi.listUploadedVideoSessions.mockRejectedValue({ status: 401, message: 'Please sign in' })
    uploadedVideoApi.getUploadedVideoTimeline.mockResolvedValue([])
    uploadedVideoApi.getUploadedVideoEvents.mockResolvedValue([])
  })

  it('maps session list 401 to scoped session-expired text', async () => {
    const { result } = renderHook(() => useUploadedVideo({ enabled: true, pollMs: 0 }))
    await act(async () => {
      await result.current.refreshSessions()
    })
    expect(result.current.error).toContain('Session list unavailable: session expired')
  })

  it('waits for auth readiness before loading sessions', async () => {
    authGateState.enabled = false
    authGateState.reason = 'checking'
    authGateState.message = 'Checking session...'

    const { result } = renderHook(() => useUploadedVideo({ enabled: true, pollMs: 0 }))
    await act(async () => {
      await result.current.refreshSessions()
    })

    expect(uploadedVideoApi.listUploadedVideoSessions).not.toHaveBeenCalled()
    expect(result.current.error).toBeNull()
    expect(result.current.loading).toBe(true)
  })

  it('keeps a completed report visible after session detail refresh', async () => {
    uploadedVideoApi.getUploadedVideoSession.mockResolvedValue({
      session_id: 'uvs_done',
      original_filename: 'done.avi',
      status: 'completed',
    })
    uploadedVideoApi.getUploadedVideoStatus.mockResolvedValue({
      session_id: 'uvs_done',
      status: 'completed',
      report_ready: true,
    })
    uploadedVideoApi.getUploadedVideoReport.mockResolvedValue({
      session_id: 'uvs_done',
      detections_summary: { total_events: 1 },
    })

    const { result } = renderHook(() => useUploadedVideo({ enabled: false }))
    await act(async () => {
      await result.current.refreshSessionDetail('uvs_done')
    })

    expect(result.current.report?.session_id).toBe('uvs_done')
    expect(result.current.error).toBeNull()
  })

  it('surfaces failed processing status with persisted backend cause', async () => {
    uploadedVideoApi.getUploadedVideoSession.mockResolvedValue({
      session_id: 'uvs_failed',
      original_filename: 'failed.avi',
      status: 'failed',
      metadata: { last_error: 'model missing' },
    })
    uploadedVideoApi.getUploadedVideoStatus.mockResolvedValue({
      session_id: 'uvs_failed',
      status: 'failed',
      last_error: 'Detector capability not ready',
    })
    uploadedVideoApi.getUploadedVideoReport.mockRejectedValue({ status: 404, message: 'not found' })

    const { result } = renderHook(() => useUploadedVideo({ enabled: false }))
    await act(async () => {
      await result.current.refreshSessionDetail('uvs_failed')
    })

    expect(result.current.report).toBeNull()
    expect(result.current.error).toContain('Detector capability not ready')
  })
})
