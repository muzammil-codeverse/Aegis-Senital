import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import ReviewQueuePanel from './ReviewQueuePanel'

vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({
    hasPermission: () => true,
    user: { role: 'admin', username: 'test' },
    authenticated: true,
    permissions: ['*'],
    loading: false,
    error: null,
  }),
}))

vi.mock('../../api/caseApi', () => ({
  listCases: vi.fn().mockResolvedValue({ items: [] }),
}))

vi.mock('../../api/droneFusionApi', () => ({
  listCorrelations: vi.fn().mockResolvedValue({ items: [] }),
  acceptCorrelation: vi.fn().mockResolvedValue({}),
  rejectCorrelation: vi.fn().mockResolvedValue({}),
  markCorrelationInconclusive: vi.fn().mockResolvedValue({}),
}))

vi.mock('../../api/identityApi', () => ({
  getIdentityCandidates: vi.fn().mockResolvedValue({ items: [] }),
  acceptIdentityCandidate: vi.fn().mockResolvedValue({}),
  rejectIdentityCandidate: vi.fn().mockResolvedValue({}),
}))

vi.mock('../../api/investigationApi', () => ({
  investigationApi: {
    listHypotheses: vi.fn().mockResolvedValue({ items: [] }),
    acceptHypothesis: vi.fn().mockResolvedValue({}),
    rejectHypothesis: vi.fn().mockResolvedValue({}),
    markInconclusive: vi.fn().mockResolvedValue({}),
  },
}))

vi.mock('../../api/modelGovernanceApi', () => ({
  fetchGovernanceLimitations: vi.fn().mockResolvedValue({ limitations: [] }),
  fetchPromotionPolicy: vi.fn().mockResolvedValue({ promotion_policy: { enable_file_writes: true } }),
}))

beforeEach(() => vi.clearAllMocks())

describe('ReviewQueuePanel', () => {
  it('renders without crashing', async () => {
    expect(() => {
      render(<ReviewQueuePanel />)
    }).not.toThrow()
  })

  it('renders the Unified Review Queue heading', async () => {
    render(<ReviewQueuePanel />)
    expect(screen.getByText('Unified Review Queue')).toBeInTheDocument()
  })

  it('renders operator-review language in the eyebrow', async () => {
    render(<ReviewQueuePanel />)
    // "Operator Workflow" eyebrow is always rendered
    expect(screen.getByText('Operator Workflow')).toBeInTheDocument()
  })

  it('renders empty or loading state when no items returned', async () => {
    render(<ReviewQueuePanel />)
    // Initially shows loading
    expect(screen.getByText(/Loading review queue/i)).toBeInTheDocument()
  })

  it('shows empty message after load completes with no items', async () => {
    render(<ReviewQueuePanel />)
    await waitFor(() => {
      expect(screen.getByText(/No pending review items/i)).toBeInTheDocument()
    }, { timeout: 3000 })
  })
})
