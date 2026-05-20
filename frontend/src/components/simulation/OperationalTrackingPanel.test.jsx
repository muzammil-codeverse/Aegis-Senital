import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import OperationalTrackingPanel from './OperationalTrackingPanel'

// Mock the scenario API so tests don't hit the network
vi.mock('../../api/scenarioApi', () => ({
  getOperationalView: vi.fn().mockResolvedValue(null),
}))

const MOCK_RUN_RUNNING = {
  run_id: 'run-abc12345678',
  scenario_id: 'bank_robbery_demo',
  state: 'running',
  current_step: 4,
  total_steps: 12,
  drone_dispatched: false,
  dispatched_drone_id: null,
}

const MOCK_RUN_WITH_DRONE = {
  ...MOCK_RUN_RUNNING,
  drone_dispatched: true,
  dispatched_drone_id: 'DRONE-ALPHA',
}

const MOCK_SUSPECT_PATH = [
  { waypoint_id: 'wp-1', entity_id: 'SUSPECT-001', entity_type: 'suspect', offset_seconds: 0, location: { x: 120, y: 80 }, zone_id: 'zone_financial', zone_name: 'Financial District', source_id: 'CAM-BANK-01', confidence: 0.72 },
  { waypoint_id: 'wp-2', entity_id: 'SUSPECT-001', entity_type: 'suspect', offset_seconds: 15, location: { x: 145, y: 100 }, zone_id: 'zone_financial', zone_name: 'Financial District', source_id: 'CAM-BANK-02', confidence: 0.95 },
]

const MOCK_HANDOFFS = [
  { handoff_id: 'hoff-01', from_camera_id: 'CAM-BANK-01', to_camera_id: 'CAM-BANK-02', actor_id: 'SUSPECT-001', offset_seconds: 15, reason: 'weapon_detected', confidence: 0.95 },
]

const MOCK_DRONE_ROUTE = {
  route_id: 'route-abc12345',
  drone_id: 'DRONE-ALPHA',
  status: 'dispatched',
  linked_actor_id: 'SUSPECT-001',
  waypoints: [],
  metadata: { airsim_ready: false },
}

const MOCK_FUSED_TRACK = {
  track_id: 'ftrack-abc12345',
  scenario_run_id: 'run-abc12345678',
  actor_id: 'SUSPECT-001',
  source_types: ['scenario_observation', 'drone_camera'],
  waypoints: [],
  camera_observations: [{}],
  drone_observations: [{}],
  handoffs: [],
  alert_ids: ['alert-001'],
  incident_ids: ['inc-001'],
  confidence: 0.88,
  status: 'active',
}

describe('OperationalTrackingPanel', () => {
  describe('zero-state', () => {
    it('renders zero-state when no activeRun', () => {
      render(<OperationalTrackingPanel activeRun={null} />)
      expect(screen.getByText(/No active scenario run/i)).toBeTruthy()
    })

    it('renders zero-state when run is idle', () => {
      render(<OperationalTrackingPanel activeRun={{ ...MOCK_RUN_RUNNING, state: 'idle' }} />)
      expect(screen.getByText(/No active scenario run/i)).toBeTruthy()
    })

    it('renders zero-state when run is cancelled', () => {
      render(<OperationalTrackingPanel activeRun={{ ...MOCK_RUN_RUNNING, state: 'cancelled' }} />)
      expect(screen.getByText(/No active scenario run/i)).toBeTruthy()
    })
  })

  describe('active scenario', () => {
    it('renders panel header with Fused Path View', () => {
      render(<OperationalTrackingPanel activeRun={MOCK_RUN_RUNNING} />)
      expect(screen.getByText(/Fused Path View/i)).toBeTruthy()
    })

    it('shows Operational Tracking eyebrow', () => {
      render(<OperationalTrackingPanel activeRun={MOCK_RUN_RUNNING} />)
      expect(screen.getByText(/Operational Tracking/i)).toBeTruthy()
    })

    it('shows run state in header', () => {
      render(<OperationalTrackingPanel activeRun={MOCK_RUN_RUNNING} />)
      expect(screen.getByText(/RUNNING/i)).toBeTruthy()
    })

    it('shows drone dispatch badge when drone is dispatched', () => {
      render(<OperationalTrackingPanel activeRun={MOCK_RUN_WITH_DRONE} />)
      const elements = screen.getAllByText(/DRONE-ALPHA/i)
      expect(elements.length).toBeGreaterThan(0)
    })

    it('renders tabs', () => {
      render(<OperationalTrackingPanel activeRun={MOCK_RUN_RUNNING} />)
      const suspectTabs = screen.getAllByText(/Suspect Path/i)
      expect(suspectTabs.length).toBeGreaterThan(0)
      const droneRoute = screen.getAllByText(/Drone Route/i)
      expect(droneRoute.length).toBeGreaterThan(0)
      expect(screen.getByText(/Fused Track/i)).toBeTruthy()
    })
  })
})

describe('SuspectPathMap rendering', () => {
  it('renders zero-state when no waypoints', async () => {
    const { default: SuspectPathMap } = await import('./SuspectPathMap')
    render(<SuspectPathMap waypoints={[]} />)
    expect(screen.getByText(/No suspect path data/i)).toBeTruthy()
  })

  it('renders SVG with waypoints', async () => {
    const { default: SuspectPathMap } = await import('./SuspectPathMap')
    render(<SuspectPathMap waypoints={MOCK_SUSPECT_PATH} />)
    const svg = document.querySelector('svg')
    expect(svg).not.toBeNull()
  })

  it('shows suspect path legend', async () => {
    const { default: SuspectPathMap } = await import('./SuspectPathMap')
    render(<SuspectPathMap waypoints={MOCK_SUSPECT_PATH} />)
    expect(screen.getByText(/Suspect path/i)).toBeTruthy()
  })
})

describe('CameraHandoffTimeline rendering', () => {
  it('renders zero-state when no handoffs', async () => {
    const { default: CameraHandoffTimeline } = await import('./CameraHandoffTimeline')
    render(<CameraHandoffTimeline handoffs={[]} />)
    expect(screen.getByText(/No camera handoffs recorded/i)).toBeTruthy()
  })

  it('renders handoff sequence', async () => {
    const { default: CameraHandoffTimeline } = await import('./CameraHandoffTimeline')
    render(<CameraHandoffTimeline handoffs={MOCK_HANDOFFS} />)
    const bank01 = screen.getAllByText(/BANK-01/i)
    expect(bank01.length).toBeGreaterThan(0)
    const bank02 = screen.getAllByText(/BANK-02/i)
    expect(bank02.length).toBeGreaterThan(0)
  })
})

describe('DroneRoutePanel rendering', () => {
  it('renders standby message when drone not dispatched', async () => {
    const { default: DroneRoutePanel } = await import('./DroneRoutePanel')
    render(<DroneRoutePanel droneRoute={null} droneDispatched={false} />)
    expect(screen.getByText(/DRONE-ALPHA awaiting dispatch/i)).toBeTruthy()
  })

  it('renders route when drone is dispatched', async () => {
    const { default: DroneRoutePanel } = await import('./DroneRoutePanel')
    render(<DroneRoutePanel droneRoute={MOCK_DRONE_ROUTE} droneDispatched={true} dispatchedDroneId="DRONE-ALPHA" />)
    expect(screen.getByText(/DRONE-ALPHA/i)).toBeTruthy()
    expect(screen.getByText(/DISPATCHED/i)).toBeTruthy()
  })
})

describe('FusedTrackSummary rendering', () => {
  it('renders zero-state when no fused track', async () => {
    const { default: FusedTrackSummary } = await import('./FusedTrackSummary')
    render(<FusedTrackSummary fusedTrack={null} />)
    expect(screen.getByText(/Fused track not yet available/i)).toBeTruthy()
  })

  it('renders track details', async () => {
    const { default: FusedTrackSummary } = await import('./FusedTrackSummary')
    render(<FusedTrackSummary fusedTrack={MOCK_FUSED_TRACK} />)
    expect(screen.getByText(/SUSPECT-001/i)).toBeTruthy()
    expect(screen.getByText(/ACTIVE/i)).toBeTruthy()
  })
})
