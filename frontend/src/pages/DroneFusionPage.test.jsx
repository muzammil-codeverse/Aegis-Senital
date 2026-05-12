import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import DroneFusionPage from './DroneFusionPage'

const FORBIDDEN = [
  'suspect confirmed',
  'identity confirmed',
  'target confirmed',
  'criminal confirmed',
  'attacker confirmed',
  'guilty',
  'real drone pursuit',
  'confirmed threat',
  'confirmed terrorist',
]

vi.mock('../hooks/useAuth', () => ({
  useAuth: () => ({
    hasPermission: () => true,
    user: { role: 'admin', username: 'test' },
    authenticated: true,
    permissions: ['*'],
    loading: false,
    error: null,
    token: 'mock-token',
    authRequired: false,
  }),
}))

vi.mock('../hooks/useDroneFusion', () => ({
  useDroneFusion: () => ({
    observations: [],
    correlations: [],
    handoffs: [],
    timeline: null,
    loading: false,
    error: null,
    wsStatus: 'connecting',
    reconnectCount: 0,
    fetchAll: vi.fn(),
    correlate: vi.fn(),
    reviewCorrelation: vi.fn(),
    suggestHandoffs: vi.fn(),
  }),
}))

// Mock sub-components that may call external APIs or use Mapbox
vi.mock('../components/drone-fusion/FusionMapOverlay', () => ({
  default: () => <div>FusionMapOverlay</div>,
}))

vi.mock('../components/drone-fusion/FusionOverviewPanel', () => ({
  default: () => <div>FusionOverviewPanel</div>,
}))

vi.mock('../components/drone-fusion/FusionObservationTable', () => ({
  default: () => <div>FusionObservationTable</div>,
}))

vi.mock('../components/drone-fusion/CrossSourceCorrelationPanel', () => ({
  default: () => <div>CrossSourceCorrelationPanel</div>,
}))

vi.mock('../components/drone-fusion/HandoffSuggestionPanel', () => ({
  default: () => <div>HandoffSuggestionPanel</div>,
}))

vi.mock('../components/drone-fusion/FusionTimeline', () => ({
  default: () => <div>FusionTimeline</div>,
}))

vi.mock('../components/drone-fusion/FusionConfidenceBreakdown', () => ({
  default: () => <div>FusionConfidenceBreakdown</div>,
}))

vi.mock('../components/drone-fusion/FusionReviewControls', () => ({
  default: () => <div>FusionReviewControls</div>,
}))

beforeEach(() => vi.clearAllMocks())

describe('DroneFusionPage', () => {
  it('renders without crashing', () => {
    expect(() => {
      render(<DroneFusionPage />)
    }).not.toThrow()
  })

  it('renders "Candidate cross-source observation" fusion wording', () => {
    render(<DroneFusionPage />)
    expect(screen.getByText('Candidate cross-source observation')).toBeInTheDocument()
  })

  it('renders "Simulated drone source badges" badge', () => {
    render(<DroneFusionPage />)
    expect(screen.getByText('Simulated drone source badges')).toBeInTheDocument()
  })

  it('renders "Operator review required" badge', () => {
    render(<DroneFusionPage />)
    expect(screen.getByText('Operator review required')).toBeInTheDocument()
  })

  it('renders the Drone Fusion page heading', () => {
    render(<DroneFusionPage />)
    expect(screen.getByRole('heading', { name: /Drone Fusion/i })).toBeInTheDocument()
  })

  it('renders state chip for "Simulated drone observation"', () => {
    render(<DroneFusionPage />)
    expect(screen.getByText('Simulated drone observation')).toBeInTheDocument()
  })

  it('renders "Evidence-backed hypothesis" chip', () => {
    render(<DroneFusionPage />)
    expect(screen.getByText('Evidence-backed hypothesis')).toBeInTheDocument()
  })

  it('renders pending review count (shows 0 when no correlations)', () => {
    render(<DroneFusionPage />)
    expect(screen.getByText('No pending fusion reviews are currently visible.')).toBeInTheDocument()
  })

  it('renders Source-pair summary card', () => {
    render(<DroneFusionPage />)
    expect(screen.getByText('Source-pair summary')).toBeInTheDocument()
  })

  it('shows tab navigation buttons', () => {
    render(<DroneFusionPage />)
    expect(screen.getByRole('button', { name: 'Overview' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Observations' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Correlations' })).toBeInTheDocument()
  })

  it('does not contain forbidden wording', () => {
    render(<DroneFusionPage />)
    const bodyText = document.body.textContent.toLowerCase()
    for (const word of FORBIDDEN) {
      expect(bodyText).not.toContain(word)
    }
  })

  it('renders Accepted items remain evidence-backed hypotheses note', () => {
    render(<DroneFusionPage />)
    expect(screen.getByText(/evidence-backed hypotheses, not identity confirmation/i)).toBeInTheDocument()
  })
})
