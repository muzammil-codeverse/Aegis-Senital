import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import UploadedVideoAnalysisPage from './UploadedVideoAnalysisPage'

vi.mock('../hooks/useAuth', () => ({
  useAuth: () => ({ hasPermission: () => true }),
}))
vi.mock('../hooks/useUploadedVideoProgress', () => ({
  useUploadedVideoProgress: () => ({ status: null, connectionStatus: 'polling', error: null }),
}))
vi.mock('../hooks/useUploadedVideo', () => ({
  useUploadedVideo: () => ({
    actionLoading: false,
    currentSession: null,
    currentStatus: null,
    sessions: [],
    loading: false,
    error: null,
    timeline: [],
    events: [],
    report: null,
    upload: vi.fn(),
    startProcessing: vi.fn(),
    cancelProcessing: vi.fn(),
    createCase: vi.fn(),
    selectSession: vi.fn(),
    refreshSessionDetail: vi.fn(),
  }),
}))

describe('UploadedVideoAnalysisPage', () => {
  it('renders authenticated empty session state instead of stale auth errors', () => {
    render(<UploadedVideoAnalysisPage />)

    expect(screen.getByText(/No uploaded-video sessions yet/i)).toBeInTheDocument()
    expect(screen.queryByText(/auth required/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/Runtime data temporarily unavailable/i)).not.toBeInTheDocument()
  })
})
