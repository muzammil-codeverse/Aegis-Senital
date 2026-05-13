import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import Dashboard from './Dashboard'

vi.mock('../hooks/useAuth', () => ({
  useAuth: () => ({ hasPermission: () => true }),
}))

vi.mock('../hooks/useDroneSimulation', () => ({
  useDroneSimulation: () => ({
    status: { health: { status: 'ok' } },
    telemetry: null,
    stats: { framesProcessed: 0, events: 0 },
  }),
}))

vi.mock('../components/dashboard/CommandOverview', () => ({
  default: () => <div>command-overview</div>,
}))
vi.mock('../components/command/OperationsTimeline', () => ({ default: () => <div>timeline</div> }))
vi.mock('../components/command/ReviewQueuePanel', () => ({ default: () => <div>review</div> }))
vi.mock('../components/command/Tactical3DStatusScene', () => ({ default: () => <div>scene</div> }))
vi.mock('../components/alerts/AlertDetailDrawer', () => ({ default: () => null }))
vi.mock('../components/cases/CaseDetailDrawer', () => ({ default: () => null }))

describe('Dashboard fallback wording', () => {
  it('does not spam global backend degraded wording in summary cards', () => {
    render(
      <Dashboard
        alertState={{ alerts: [], selectedAlert: null, history: [], detailLoading: false, actionError: null, selectAlert: vi.fn() }}
        incidentState={{ incidents: [] }}
        caseState={{ requiringReviewCount: 0, relatedCaseByEvent: () => null, selectedCase: null, selectCase: vi.fn() }}
        metricsState={{}}
        websocketState={{ alerts: [], status: 'connected' }}
        health={{ status: 'ok', reasons: [] }}
      />,
    )
    expect(screen.getByText('No simulated telemetry reported to the dashboard yet.')).toBeInTheDocument()
    expect(screen.queryByText(/backend unavailable/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/production system health endpoint temporarily unavailable/i)).not.toBeInTheDocument()
  })
})
