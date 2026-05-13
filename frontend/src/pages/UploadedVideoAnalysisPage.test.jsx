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
    sessions: [],
    error: 'Session list unavailable: auth required',
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
  it('shows scoped session library error text', () => {
    render(<UploadedVideoAnalysisPage />)
    expect(screen.getByText(/Session list unavailable: auth required/i)).toBeInTheDocument()
    expect(screen.queryByText(/Runtime data temporarily unavailable/i)).not.toBeInTheDocument()
  })
})

