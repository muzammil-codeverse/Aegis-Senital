import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import DroneSimulationPage from './DroneSimulationPage'

vi.mock('../hooks/useDroneSimulation', () => ({
  useDroneSimulation: () => ({
    canRead: true,
    statusDetail: 'Ready to start simulated drone session.',
    error: null,
    runtimeStatus: null,
    status: {},
    cameraSources: [],
    cameraFrames: {},
    latestFrame: null,
    stats: { framesProcessed: 0, telemetryUpdates: 0, events: 0 },
    wsStatus: 'polling',
    uiState: 'not_started',
    canControl: true,
    telemetry: null,
    flightPath: [],
    refreshAll: vi.fn(),
    refreshCameraFrame: vi.fn(),
    startSession: vi.fn(),
    stopSession: vi.fn(),
    takeoff: vi.fn(),
    land: vi.fn(),
    hover: vi.fn(),
    move: vi.fn(),
    launchRuntime: vi.fn(),
    runMissionDemo: vi.fn(),
    actionError: null,
  }),
}))

describe('DroneSimulationPage', () => {
  it('shows scoped runtime detail instead of generic unavailable text', () => {
    render(<DroneSimulationPage />)
    expect(screen.getByText(/Ready to start simulated drone session/i)).toBeInTheDocument()
    expect(screen.queryByText(/Runtime data temporarily unavailable/i)).not.toBeInTheDocument()
  })
})

