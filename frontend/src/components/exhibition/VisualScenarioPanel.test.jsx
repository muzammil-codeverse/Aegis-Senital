import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

// Mock the API module BEFORE importing the component under test.
vi.mock('../../api/visualScenarioApi', () => ({
  getVisualSyncStatus: vi.fn(),
  setupVisualScene: vi.fn(),
  startVisualDemo: vi.fn(),
  stopVisualDemo: vi.fn(),
  syncVisualToOffset: vi.fn(),
  syncVisualFromStep: vi.fn(),
  flushVisualScene: vi.fn(),
  captureAllSnapshots: vi.fn(),
  captureCameraSnapshot: vi.fn(),
  listVisualCameras: vi.fn(),
  getRealActorMode: vi.fn(),
  snapshotImageUrl: vi.fn((id, bust) => `http://test/snap/${id}?t=${bust ?? ''}`),
}))

import VisualScenarioPanel from './VisualScenarioPanel'
import {
  getVisualSyncStatus,
  setupVisualScene,
  startVisualDemo,
  stopVisualDemo,
  syncVisualToOffset,
  flushVisualScene,
  captureAllSnapshots,
  captureCameraSnapshot,
  listVisualCameras,
  getRealActorMode,
} from '../../api/visualScenarioApi'

const baseStatus = {
  connected: false,
  active: false,
  scenario_run_id: null,
  last_t_offset_seconds: null,
  last_sync_at: null,
  last_step: null,
  last_error: null,
  auto_capture_snapshots: true,
  snapshot_dir: '/tmp/snapshots',
  real_actor_mode: 'proxy_overlay',
  controller: {
    real_actor_mode: 'proxy_overlay',
    static_drawn: false,
    animation_running: false,
    spawned_assets: {},
    airsim_host: '127.0.0.1',
    airsim_port: 41451,
  },
}

const connectedStatus = {
  ...baseStatus,
  connected: true,
  active: true,
  real_actor_mode: 'spawned_mesh',
  last_t_offset_seconds: 20,
  last_sync_at: new Date().toISOString(),
  controller: {
    ...baseStatus.controller,
    real_actor_mode: 'spawned_mesh',
    static_drawn: true,
    animation_running: true,
    spawned_assets: { AegisActor_SUSPECT_001: 'BP_Sedan' },
  },
}

const sampleCameras = [
  {
    camera_id: 'CAM-BANK-01',
    zone_id: 'zone_financial',
    pose: { x: 118, y: 77, z: 4.5 },
    snapshot_path: '/tmp/snapshots/CAM-BANK-01.png',
    snapshot_url: '/api/visual-scenario/snapshots/CAM-BANK-01',
    last_capture_at: new Date().toISOString(),
    last_status: 'ok',
  },
  {
    camera_id: 'CAM-BANK-02',
    zone_id: 'zone_financial',
    pose: { x: 148, y: 103, z: 4.5 },
    snapshot_path: null,
    snapshot_url: null,
    last_capture_at: null,
    last_status: 'pending',
  },
]

function setupMocks({ status = baseStatus, cameras = sampleCameras } = {}) {
  getVisualSyncStatus.mockResolvedValue(status)
  listVisualCameras.mockResolvedValue(cameras)
  setupVisualScene.mockResolvedValue({ status: 'ok' })
  startVisualDemo.mockResolvedValue({ status: 'ok' })
  stopVisualDemo.mockResolvedValue({ status: 'ok' })
  syncVisualToOffset.mockResolvedValue({ status: 'ok' })
  flushVisualScene.mockResolvedValue({ status: 'ok' })
  captureAllSnapshots.mockResolvedValue({ status: 'ok', captured: [] })
  captureCameraSnapshot.mockResolvedValue({ status: 'ok' })
  getRealActorMode.mockResolvedValue({ real_actor_mode: 'spawned_mesh' })
}

describe('VisualScenarioPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders heading and AirSim offline state when disconnected', async () => {
    setupMocks({ status: baseStatus })
    render(<VisualScenarioPanel pollIntervalMs={0} />)
    await waitFor(() => {
      expect(screen.getByText('Visual Simulation Bridge')).toBeInTheDocument()
    })
    expect(screen.getByText('AirSim Offline')).toBeInTheDocument()
    expect(screen.getByTestId('visual-real-actor-mode')).toHaveTextContent(/Proxy Overlay/i)
  })

  it('shows proxy_overlay fidelity warning', async () => {
    setupMocks({ status: baseStatus })
    render(<VisualScenarioPanel pollIntervalMs={0} />)
    await waitFor(() => {
      expect(screen.getByTestId('visual-mode-warning')).toBeInTheDocument()
    })
  })

  it('renders connected status and spawned_mesh badge', async () => {
    setupMocks({ status: connectedStatus })
    render(<VisualScenarioPanel pollIntervalMs={0} />)
    await waitFor(() => {
      expect(screen.getByText('AirSim Connected')).toBeInTheDocument()
    })
    expect(screen.getByTestId('visual-real-actor-mode')).toHaveTextContent(/Spawned Mesh Proxies/i)
    // No fidelity warning in spawned_mesh mode
    expect(screen.queryByTestId('visual-mode-warning')).not.toBeInTheDocument()
  })

  it('renders camera snapshot grid with one captured and one pending camera', async () => {
    setupMocks({ status: connectedStatus, cameras: sampleCameras })
    render(<VisualScenarioPanel pollIntervalMs={0} />)
    await waitFor(() => {
      expect(screen.getByTestId('visual-camera-card-CAM-BANK-01')).toBeInTheDocument()
      expect(screen.getByTestId('visual-camera-card-CAM-BANK-02')).toBeInTheDocument()
    })
    expect(screen.getByTestId('visual-camera-img-CAM-BANK-01')).toBeInTheDocument()
    expect(screen.queryByTestId('visual-camera-img-CAM-BANK-02')).not.toBeInTheDocument()
  })

  it('Setup Visual World button calls setupVisualScene', async () => {
    setupMocks({ status: baseStatus })
    render(<VisualScenarioPanel pollIntervalMs={0} />)
    await waitFor(() => {
      expect(screen.getByTestId('visual-action-setup')).toBeInTheDocument()
    })
    fireEvent.click(screen.getByTestId('visual-action-setup'))
    await waitFor(() => {
      expect(setupVisualScene).toHaveBeenCalledTimes(1)
    })
  })

  it('Start Visual Scene button calls startVisualDemo with run id', async () => {
    setupMocks({ status: baseStatus })
    render(<VisualScenarioPanel scenarioRunId="run-abc" pollIntervalMs={0} />)
    await waitFor(() => {
      expect(screen.getByTestId('visual-action-start')).toBeInTheDocument()
    })
    fireEvent.click(screen.getByTestId('visual-action-start'))
    await waitFor(() => {
      expect(startVisualDemo).toHaveBeenCalledWith(expect.objectContaining({ scenario_run_id: 'run-abc' }))
    })
  })

  it('Sync to Current Step button uses last offset', async () => {
    setupMocks({ status: connectedStatus })
    render(<VisualScenarioPanel pollIntervalMs={0} />)
    await waitFor(() => {
      expect(screen.getByTestId('visual-action-sync')).toBeInTheDocument()
    })
    fireEvent.click(screen.getByTestId('visual-action-sync'))
    await waitFor(() => {
      expect(syncVisualToOffset).toHaveBeenCalledWith(expect.objectContaining({ t_offset_seconds: 20 }))
    })
  })

  it('Capture Snapshots button calls captureAllSnapshots', async () => {
    setupMocks({ status: connectedStatus })
    render(<VisualScenarioPanel pollIntervalMs={0} />)
    await waitFor(() => {
      expect(screen.getByTestId('visual-action-capture-all')).toBeInTheDocument()
    })
    fireEvent.click(screen.getByTestId('visual-action-capture-all'))
    await waitFor(() => {
      expect(captureAllSnapshots).toHaveBeenCalledTimes(1)
    })
  })

  it('Refresh Mode button calls getRealActorMode', async () => {
    setupMocks({ status: connectedStatus })
    render(<VisualScenarioPanel pollIntervalMs={0} />)
    await waitFor(() => {
      expect(screen.getByTestId('visual-action-refresh-mode')).toBeInTheDocument()
    })
    fireEvent.click(screen.getByTestId('visual-action-refresh-mode'))
    await waitFor(() => {
      expect(getRealActorMode).toHaveBeenCalledTimes(1)
    })
  })

  it('Stop Animation and Flush buttons invoke the right API', async () => {
    setupMocks({ status: connectedStatus })
    render(<VisualScenarioPanel pollIntervalMs={0} />)
    await waitFor(() => {
      expect(screen.getByTestId('visual-action-stop')).toBeInTheDocument()
    })
    fireEvent.click(screen.getByTestId('visual-action-stop'))
    fireEvent.click(screen.getByTestId('visual-action-flush'))
    await waitFor(() => {
      expect(stopVisualDemo).toHaveBeenCalledTimes(1)
      expect(flushVisualScene).toHaveBeenCalledTimes(1)
    })
  })

  it('Individual camera capture button triggers captureCameraSnapshot', async () => {
    setupMocks({ status: connectedStatus, cameras: sampleCameras })
    render(<VisualScenarioPanel pollIntervalMs={0} />)
    await waitFor(() => {
      expect(screen.getByTestId('visual-camera-capture-CAM-BANK-02')).toBeInTheDocument()
    })
    fireEvent.click(screen.getByTestId('visual-camera-capture-CAM-BANK-02'))
    await waitFor(() => {
      expect(captureCameraSnapshot).toHaveBeenCalledWith('CAM-BANK-02')
    })
  })

  it('shows error banner when API fails', async () => {
    getVisualSyncStatus.mockRejectedValue({ message: 'boom' })
    listVisualCameras.mockResolvedValue([])
    render(<VisualScenarioPanel pollIntervalMs={0} />)
    await waitFor(() => {
      expect(screen.getByTestId('visual-error')).toBeInTheDocument()
    })
  })
})
