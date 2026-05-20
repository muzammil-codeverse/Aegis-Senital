import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import ExhibitionDemoPanel from './ExhibitionDemoPanel'

// Mock useAuth to control auth state
vi.mock('../../hooks/useAuth', () => ({
  useAuth: vi.fn(),
}))

// Mock the entire exhibitionDemoApi module
vi.mock('../../api/exhibitionDemoApi', () => ({
  getDemoStatus: vi.fn(),
  getDemoSnapshot: vi.fn(),
  resetDemo: vi.fn(),
  startDemo: vi.fn(),
  stepDemo: vi.fn(),
  autoRunDemo: vi.fn(),
  cancelDemo: vi.fn(),
  getDemoRunbook: vi.fn(),
  getDemoFallback: vi.fn(),
}))

// Phase XII child panel — mocked to keep ExhibitionDemoPanel tests isolated
vi.mock('../../api/visualScenarioApi', () => ({
  getVisualSyncStatus: vi.fn().mockResolvedValue(null),
  setupVisualScene: vi.fn().mockResolvedValue({}),
  startVisualDemo: vi.fn().mockResolvedValue({}),
  stopVisualDemo: vi.fn().mockResolvedValue({}),
  syncVisualToOffset: vi.fn().mockResolvedValue({}),
  syncVisualFromStep: vi.fn().mockResolvedValue({}),
  flushVisualScene: vi.fn().mockResolvedValue({}),
  captureAllSnapshots: vi.fn().mockResolvedValue({}),
  captureCameraSnapshot: vi.fn().mockResolvedValue({}),
  listVisualCameras: vi.fn().mockResolvedValue([]),
  getRealActorMode: vi.fn().mockResolvedValue({ real_actor_mode: 'unavailable' }),
  snapshotImageUrl: vi.fn().mockReturnValue('about:blank'),
}))

import { useAuth } from '../../hooks/useAuth'
import {
  getDemoStatus,
  getDemoSnapshot,
  resetDemo,
  startDemo,
  stepDemo,
  autoRunDemo,
  cancelDemo,
  getDemoRunbook,
  getDemoFallback,
} from '../../api/exhibitionDemoApi'

const AUTH_READY = { loading: false, authenticated: true, hasPermission: () => true }
const AUTH_LOADING = { loading: true, authenticated: false, hasPermission: () => false }
const AUTH_UNAUTHENTICATED = { loading: false, authenticated: false, hasPermission: () => false }

const NOT_STARTED_SESSION = {
  demo_id: 'demo-001',
  status: 'not_started',
  scenario_run_id: null,
  current_step: 0,
  total_steps: 0,
  active_alert_ids: [],
  active_incident_ids: [],
  assigned_drone_ids: [],
  tracking_ready: false,
  command_center_ready: false,
  started_at: null,
  completed_at: null,
  last_error: null,
  metadata: {},
}

const RUNNING_SESSION = {
  ...NOT_STARTED_SESSION,
  status: 'running',
  scenario_run_id: 'run-abc123456789',
  current_step: 0,
  total_steps: 12,
}

const ALERT_SESSION = {
  ...RUNNING_SESSION,
  current_step: 4,
  active_alert_ids: ['alert-scn-abc-001'],
  active_incident_ids: ['inc-scn-abc-001'],
  assigned_drone_ids: ['DRONE-ALPHA'],
  tracking_ready: true,
  command_center_ready: true,
}

const EMPTY_SNAPSHOT = {
  demo_session: NOT_STARTED_SESSION,
  scenario_run: null,
  active_event: null,
  recent_observations: [],
  camera_observations: [],
  promotions: [],
  drone_state: null,
  suspect_path: [],
  camera_handoffs: [],
  drone_route: null,
  fused_track: null,
  analytics_summary: { total_alerts: 0, total_incidents: 0, critical_alerts: 0, high_alerts: 0 },
  report_links: {},
  ui_links: {
    tracking_panel: '/#operational-tracking',
    alerts_page: '/alerts',
    incidents_page: '/incidents',
    analytics_page: '/analytics',
  },
}

function setup(sessionOverride = {}, snapshotOverride = {}) {
  useAuth.mockReturnValue(AUTH_READY)
  getDemoStatus.mockResolvedValue({ ...NOT_STARTED_SESSION, ...sessionOverride })
  getDemoSnapshot.mockResolvedValue({ ...EMPTY_SNAPSHOT, demo_session: { ...NOT_STARTED_SESSION, ...sessionOverride }, ...snapshotOverride })
  return render(<ExhibitionDemoPanel />)
}

describe('ExhibitionDemoPanel — no demo state', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAuth.mockReturnValue(AUTH_READY)
  })

  it('renders the panel heading', async () => {
    setup()
    await waitFor(() => {
      expect(screen.getByText('Bank Robbery Demo')).toBeInTheDocument()
    })
  })

  it('shows Not Started status badge', async () => {
    setup()
    await waitFor(() => {
      expect(screen.getByText('Not Started')).toBeInTheDocument()
    })
  })

  it('shows Start Demo buttons', async () => {
    setup()
    await waitFor(() => {
      const buttons = screen.getAllByText(/start demo/i)
      expect(buttons.length).toBeGreaterThan(0)
    })
  })

  it('shows operator guidance text for not_started state', async () => {
    setup()
    await waitFor(() => {
      const body = document.body.textContent
      expect(body).toContain('Step mode')
    })
  })

  it('shows Runbook button', async () => {
    setup()
    await waitFor(() => {
      expect(screen.getByText('Runbook')).toBeInTheDocument()
    })
  })

  it('shows Reset button', async () => {
    setup()
    await waitFor(() => {
      expect(screen.getByText('Reset')).toBeInTheDocument()
    })
  })
})

describe('ExhibitionDemoPanel — Start Demo button calls API', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAuth.mockReturnValue(AUTH_READY)
    startDemo.mockResolvedValue({ status: 'running', demo: RUNNING_SESSION })
    getDemoStatus
      .mockResolvedValueOnce(NOT_STARTED_SESSION)
      .mockResolvedValue(RUNNING_SESSION)
    getDemoSnapshot.mockResolvedValue(EMPTY_SNAPSHOT)
    resetDemo.mockResolvedValue({ reset: true, status: 'ok' })
  })

  it('calls startDemo with step mode on Start Demo (Step) click', async () => {
    render(<ExhibitionDemoPanel />)
    await waitFor(() => screen.getByText(/start demo \(step\)/i))
    fireEvent.click(screen.getByText(/start demo \(step\)/i))
    await waitFor(() => {
      expect(startDemo).toHaveBeenCalledWith({ mode: 'step' })
    })
  })

  it('calls startDemo with auto mode on Start Demo (Auto) click', async () => {
    render(<ExhibitionDemoPanel />)
    await waitFor(() => screen.getByText(/start demo \(auto\)/i))
    fireEvent.click(screen.getByText(/start demo \(auto\)/i))
    await waitFor(() => {
      expect(startDemo).toHaveBeenCalledWith({ mode: 'auto' })
    })
  })

  it('calls resetDemo on Reset click', async () => {
    render(<ExhibitionDemoPanel />)
    await waitFor(() => screen.getByText('Reset'))
    fireEvent.click(screen.getByText('Reset'))
    await waitFor(() => {
      expect(resetDemo).toHaveBeenCalled()
    })
  })
})

describe('ExhibitionDemoPanel — running state', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAuth.mockReturnValue(AUTH_READY)
    getDemoStatus.mockResolvedValue(RUNNING_SESSION)
    getDemoSnapshot.mockResolvedValue({ ...EMPTY_SNAPSHOT, demo_session: RUNNING_SESSION })
    stepDemo.mockResolvedValue({ status: 'ok', step_result: { step: 1, event_type: 'person_tracking' }, demo: RUNNING_SESSION })
    autoRunDemo.mockResolvedValue({ status: 'ok', demo: RUNNING_SESSION })
    cancelDemo.mockResolvedValue({ status: 'cancelled' })
  })

  it('shows Running status badge', async () => {
    render(<ExhibitionDemoPanel />)
    await waitFor(() => {
      expect(screen.getByText('Running')).toBeInTheDocument()
    })
  })

  it('shows Step → button when running', async () => {
    render(<ExhibitionDemoPanel />)
    await waitFor(() => {
      expect(screen.getByText(/step →/i)).toBeInTheDocument()
    })
  })

  it('shows progress bar when total_steps > 0', async () => {
    render(<ExhibitionDemoPanel />)
    await waitFor(() => {
      expect(screen.getByText(/step 0 \/ 12/i)).toBeInTheDocument()
    })
  })

  it('calls stepDemo on Step → click', async () => {
    render(<ExhibitionDemoPanel />)
    await waitFor(() => screen.getByText(/step →/i))
    fireEvent.click(screen.getByText(/step →/i))
    await waitFor(() => {
      expect(stepDemo).toHaveBeenCalled()
    })
  })

  it('shows Cancel button when running', async () => {
    render(<ExhibitionDemoPanel />)
    await waitFor(() => {
      expect(screen.getByText('Cancel')).toBeInTheDocument()
    })
  })
})

describe('ExhibitionDemoPanel — critical alert state', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAuth.mockReturnValue(AUTH_READY)
    getDemoStatus.mockResolvedValue(ALERT_SESSION)
    getDemoSnapshot.mockResolvedValue({
      ...EMPTY_SNAPSHOT,
      demo_session: ALERT_SESSION,
      report_links: {
        scenario_id: 'bank_robbery_demo',
        run_id: 'run-abc123456789',
        simulated: true,
        source_cameras: ['CAM-BANK-01', 'CAM-BANK-02'],
        suspect_actor: 'SUSPECT-001',
        drone_assigned: 'DRONE-ALPHA',
        alert_ids: ['alert-scn-abc-001'],
        incident_ids: ['inc-scn-abc-001'],
        disclaimer: 'All data is simulated.',
      },
    })
  })

  it('shows alert count 1', async () => {
    render(<ExhibitionDemoPanel />)
    await waitFor(() => {
      // Both alerts and incidents show "1" — verify both are present
      const ones = screen.getAllByText('1')
      expect(ones.length).toBeGreaterThanOrEqual(1)
    })
  })

  it('shows DRONE-ALPHA assigned indicator (▲)', async () => {
    render(<ExhibitionDemoPanel />)
    await waitFor(() => {
      expect(screen.getByText('▲')).toBeInTheDocument()
    })
  })

  it('shows tracking ready indicator (●)', async () => {
    render(<ExhibitionDemoPanel />)
    await waitFor(() => {
      expect(screen.getByText('●')).toBeInTheDocument()
    })
  })

  it('shows scenario evidence summary', async () => {
    render(<ExhibitionDemoPanel />)
    await waitFor(() => {
      expect(screen.getByText(/SIMULATED/)).toBeInTheDocument()
    })
  })

  it('shows View Tracking link', async () => {
    render(<ExhibitionDemoPanel />)
    await waitFor(() => {
      expect(screen.getByText(/view tracking/i)).toBeInTheDocument()
    })
  })
})

describe('ExhibitionDemoPanel — error state displays cleanly', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAuth.mockReturnValue(AUTH_READY)
    getDemoStatus.mockRejectedValue({ response: { status: 500, data: { detail: 'Server exploded' } } })
    getDemoSnapshot.mockRejectedValue(new Error('snapshot unavailable'))
  })

  it('does not crash on API error', async () => {
    render(<ExhibitionDemoPanel />)
    await waitFor(() => {
      // Panel header always renders even if API fails
      const body = document.body.textContent
      expect(body).toContain('Bank Robbery Demo')
    })
  })
})

describe('ExhibitionDemoPanel — runbook modal', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAuth.mockReturnValue(AUTH_READY)
    getDemoStatus.mockResolvedValue(NOT_STARTED_SESSION)
    getDemoSnapshot.mockResolvedValue(EMPTY_SNAPSHOT)
    getDemoRunbook.mockResolvedValue({
      title: 'Bank Robbery Demo — Operator Runbook',
      steps: [
        { step: 1, title: 'System Startup', description: 'Backend and frontend are running.', phase: 'setup', operator_note: 'Check health.' },
        { step: 2, title: 'Exhibition Preflight', description: 'Run preflight.', phase: 'setup', operator_note: 'Click Run Preflight.' },
      ],
    })
  })

  it('opens runbook modal on Runbook button click', async () => {
    render(<ExhibitionDemoPanel />)
    await waitFor(() => screen.getByText('Runbook'))
    fireEvent.click(screen.getByText('Runbook'))
    await waitFor(() => {
      expect(screen.getByText('Exhibition Demo Runbook')).toBeInTheDocument()
    })
  })

  it('shows runbook steps in modal', async () => {
    render(<ExhibitionDemoPanel />)
    await waitFor(() => screen.getByText('Runbook'))
    fireEvent.click(screen.getByText('Runbook'))
    await waitFor(() => {
      expect(screen.getByText('System Startup')).toBeInTheDocument()
      expect(screen.getByText('Exhibition Preflight')).toBeInTheDocument()
    })
  })
})

// ─── Phase 10 Hardening Tests ────────────────────────────────────────────────

describe('ExhibitionDemoPanel — Phase 10: auth loading state', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAuth.mockReturnValue(AUTH_LOADING)
    getDemoStatus.mockResolvedValue(NOT_STARTED_SESSION)
    getDemoSnapshot.mockResolvedValue(EMPTY_SNAPSHOT)
  })

  it('shows Authenticating text while auth is loading', () => {
    render(<ExhibitionDemoPanel />)
    expect(screen.getByText('Authenticating…')).toBeInTheDocument()
  })

  it('does not call getDemoStatus while auth is loading', () => {
    render(<ExhibitionDemoPanel />)
    expect(getDemoStatus).not.toHaveBeenCalled()
  })
})

describe('ExhibitionDemoPanel — Phase 10: unauthenticated state', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAuth.mockReturnValue(AUTH_UNAUTHENTICATED)
    getDemoStatus.mockResolvedValue(NOT_STARTED_SESSION)
    getDemoSnapshot.mockResolvedValue(EMPTY_SNAPSHOT)
  })

  it('shows session expired message when not authenticated', () => {
    render(<ExhibitionDemoPanel />)
    expect(screen.getByText(/session expired/i)).toBeInTheDocument()
  })

  it('does not call getDemoStatus when unauthenticated', () => {
    render(<ExhibitionDemoPanel />)
    expect(getDemoStatus).not.toHaveBeenCalled()
  })
})

describe('ExhibitionDemoPanel — Phase 10: stale status', () => {
  const STALE_SESSION = {
    ...NOT_STARTED_SESSION,
    status: 'stale',
    last_error: 'Backend restarted. Click Reset to start fresh.',
  }

  beforeEach(() => {
    vi.clearAllMocks()
    useAuth.mockReturnValue(AUTH_READY)
    getDemoStatus.mockResolvedValue(STALE_SESSION)
    getDemoSnapshot.mockResolvedValue({ ...EMPTY_SNAPSHOT, demo_session: STALE_SESSION })
  })

  it('shows stale banner with last_error message', async () => {
    render(<ExhibitionDemoPanel />)
    await waitFor(() => {
      expect(screen.getByText(/backend restarted/i)).toBeInTheDocument()
    })
  })

  it('shows Stale status badge', async () => {
    render(<ExhibitionDemoPanel />)
    await waitFor(() => {
      const matches = screen.getAllByText(/stale/i)
      expect(matches.length).toBeGreaterThanOrEqual(1)
    })
  })
})

describe('ExhibitionDemoPanel — Phase 10: fallback replay button', () => {
  const FALLBACK_DATA = {
    fallback: true,
    fallback_label: 'Demo Replay Mode — deterministic fallback, not a live scenario run',
    scenario_id: 'bank_robbery_demo',
    timeline_summary: [
      { event_type: 'person_observed', camera_id: 'CAM-BANK-01', is_critical: false },
      { event_type: 'weapon_detected', camera_id: 'CAM-BANK-02', is_critical: true },
    ],
    simulated: true,
    disclaimer: 'All data is simulated.',
  }

  beforeEach(() => {
    vi.clearAllMocks()
    useAuth.mockReturnValue(AUTH_READY)
    getDemoStatus.mockResolvedValue(NOT_STARTED_SESSION)
    getDemoSnapshot.mockResolvedValue(EMPTY_SNAPSHOT)
    getDemoFallback.mockResolvedValue(FALLBACK_DATA)
  })

  it('renders Fallback Replay button', async () => {
    render(<ExhibitionDemoPanel />)
    await waitFor(() => {
      expect(screen.getByText(/fallback replay/i)).toBeInTheDocument()
    })
  })

  it('calls getDemoFallback and shows banner on click', async () => {
    render(<ExhibitionDemoPanel />)
    await waitFor(() => screen.getByText(/fallback replay/i))
    fireEvent.click(screen.getByText(/fallback replay/i))
    await waitFor(() => {
      expect(getDemoFallback).toHaveBeenCalled()
      const matches = screen.getAllByText(/demo replay mode/i)
      expect(matches.length).toBeGreaterThanOrEqual(1)
    })
  })
})
