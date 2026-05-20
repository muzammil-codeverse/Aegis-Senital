import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Dashboard from './Dashboard'

const authState = vi.hoisted(() => ({
  ready: true,
  loading: false,
  authenticated: true,
  hasPermission: () => true,
}))

const hookCalls = vi.hoisted(() => ({
  useCameras: vi.fn(),
  useLatestFrames: vi.fn(),
  useMapState: vi.fn(),
  useHandoffs: vi.fn(),
  useDroneSimulation: vi.fn(),
  useSimulationSources: vi.fn(),
  useScenario: vi.fn(),
}))

const commandOverviewSpy = vi.hoisted(() => vi.fn())

function resetHookReturns() {
  hookCalls.useCameras.mockReturnValue({
    cameras: [],
    loading: false,
    error: null,
    refresh: vi.fn(),
    selectedCamera: null,
    setSelectedCamera: vi.fn(),
  })
  hookCalls.useLatestFrames.mockReturnValue({ framesByCameraId: {}, refresh: vi.fn() })
  hookCalls.useMapState.mockReturnValue({
    mapState: null,
    loading: false,
    error: null,
    refresh: vi.fn(),
    setSelectedCameraId: vi.fn(),
  })
  hookCalls.useHandoffs.mockReturnValue({ activeHandoffs: [], recentHandoffs: [] })
  hookCalls.useDroneSimulation.mockReturnValue({
    status: { health: { status: 'ok' } },
    telemetry: null,
    stats: { framesProcessed: 0, events: 0 },
  })
  hookCalls.useSimulationSources.mockReturnValue({
    cameras: [],
    drones: [],
    loading: false,
    error: null,
    refresh: vi.fn(),
  })
  hookCalls.useScenario.mockReturnValue({
    scenarios: [],
    activeRun: null,
    timeline: [],
    loading: false,
    error: null,
  })
  commandOverviewSpy.mockClear()
}

vi.mock('../hooks/useAuth', () => ({
  useAuth: () => authState,
}))

vi.mock('../hooks/useDroneSimulation', () => ({
  useDroneSimulation: options => hookCalls.useDroneSimulation(options),
}))

vi.mock('../hooks/useSimulationSources', () => ({
  useSimulationSources: options => hookCalls.useSimulationSources(options),
}))

vi.mock('../hooks/useScenario', () => ({
  useScenario: options => hookCalls.useScenario(options),
}))

vi.mock('../hooks/useMapState', () => ({
  useMapState: options => hookCalls.useMapState(options),
}))

vi.mock('../hooks/useHandoffs', () => ({
  useHandoffs: options => hookCalls.useHandoffs(options),
}))

vi.mock('../hooks/useCameras', () => ({
  useCameras: options => hookCalls.useCameras(options),
}))

vi.mock('../hooks/useLatestFrames', () => ({
  useLatestFrames: options => hookCalls.useLatestFrames(options),
}))

vi.mock('../hooks/useFrameUpdates', () => ({
  useFrameUpdates: () => ({ framesByCameraId: {} }),
}))

vi.mock('../hooks/useWebSocketHandoffs', () => ({
  useWebSocketHandoffs: () => ({ handoffList: [], status: 'connected' }),
}))

vi.mock('../api/camerasApi', () => ({
  getStreams: vi.fn(async () => ({ items: [] })),
  getLiveAnomalies: vi.fn(async () => ({ items: [] })),
}))

vi.mock('../api/analyticsApi', () => ({
  getDashboardOverview: vi.fn(async () => ({ item: { summary: {} } })),
}))

vi.mock('../components/dashboard/CommandOverview', () => ({
  default: props => {
    commandOverviewSpy(props)
    return <div data-testid="command-overview">{props.cameras.length} cameras</div>
  },
}))
vi.mock('../components/exhibition/ExhibitionDemoPanel', () => ({ default: () => <div>exhibition</div> }))
vi.mock('../components/command/OperationsTimeline', () => ({ default: () => <div>timeline</div> }))
vi.mock('../components/command/ReviewQueuePanel', () => ({ default: () => <div>review</div> }))
vi.mock('../components/command/Tactical3DStatusScene', () => ({ default: () => <div>scene</div> }))
vi.mock('../components/alerts/AlertDetailDrawer', () => ({ default: () => null }))
vi.mock('../components/cases/CaseDetailDrawer', () => ({ default: () => null }))

function renderDashboard(overrides = {}) {
  return render(
    <Dashboard
      alertState={{ alerts: [], selectedAlert: null, history: [], detailLoading: false, actionError: null, selectAlert: vi.fn(), ...overrides.alertState }}
      incidentState={{ incidents: [], ...overrides.incidentState }}
      caseState={{ requiringReviewCount: 0, relatedCaseByEvent: () => null, selectedCase: null, selectCase: vi.fn(), ...overrides.caseState }}
      metricsState={{ metrics: {}, ...overrides.metricsState }}
      websocketState={{ alerts: [], status: 'connected', ...overrides.websocketState }}
      health={{ status: 'ok', reasons: [], ...overrides.health }}
    />,
  )
}

describe('Dashboard auth readiness and exhibition camera flow', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    authState.ready = true
    authState.loading = false
    authState.authenticated = true
    authState.hasPermission = () => true
    resetHookReturns()
  })

  it('does not enable protected dashboard widgets before auth is ready', () => {
    authState.ready = false
    authState.loading = true
    authState.authenticated = false

    renderDashboard()

    expect(hookCalls.useCameras).toHaveBeenCalledWith(expect.objectContaining({ enabled: false }))
    expect(hookCalls.useLatestFrames).toHaveBeenCalledWith(expect.objectContaining({ enabled: false }))
    expect(hookCalls.useMapState).toHaveBeenCalledWith(expect.objectContaining({ enabled: false }))
    expect(hookCalls.useSimulationSources).toHaveBeenCalledWith(expect.objectContaining({ enabled: false }))
  })

  it('passes simulation cameras into the main command overview after login', () => {
    hookCalls.useSimulationSources.mockReturnValue({
      cameras: [{ camera_id: 'CAM-BANK-01', name: 'Bank Main Entrance', simulated: true, status: 'online' }],
      drones: [],
      loading: false,
      error: null,
      refresh: vi.fn(),
    })

    renderDashboard()

    expect(screen.getByTestId('command-overview')).toHaveTextContent('1 cameras')
    expect(commandOverviewSpy).toHaveBeenCalledWith(expect.objectContaining({
      cameras: expect.arrayContaining([expect.objectContaining({ camera_id: 'CAM-BANK-01', simulated: true })]),
    }))
  })

  it('does not show old global backend degraded wording in summary cards', () => {
    renderDashboard()

    expect(screen.getByText('No simulated telemetry reported to the dashboard yet.')).toBeInTheDocument()
    expect(screen.getByText('Uploaded-video intelligence')).toBeInTheDocument()
    expect(screen.queryByText(/backend unavailable/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/production system health endpoint temporarily unavailable/i)).not.toBeInTheDocument()
  })
})
