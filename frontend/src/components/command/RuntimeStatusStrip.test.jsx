import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import RuntimeStatusStrip from './RuntimeStatusStrip'

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

function makeRuntimeStatus(items) {
  return {
    overall: items.reduce((worst, item) => {
      const weight = { ok: 1, degraded: 2, critical: 3 }
      return (weight[item.status] || 0) > (weight[worst] || 0) ? item.status : worst
    }, 'ok'),
    items,
    byKey: Object.fromEntries(items.map(item => [item.key, item])),
    loading: false,
    error: null,
    refresh: vi.fn(),
  }
}

const healthyItems = [
  { key: 'system', label: 'Backend', status: 'ok', summary: 'Backend health' },
  { key: 'database', label: 'Database', status: 'ok', summary: 'Database ready' },
  { key: 'droneSimulation', label: 'Drone Simulation', status: 'ok', summary: 'Simulated session available' },
  { key: 'droneFusion', label: 'Drone Fusion', status: 'ok', summary: 'Fusion service reachable' },
  { key: 'modelGovernance', label: 'Model Governance', status: 'ok', summary: 'Governance checks available' },
]

beforeEach(() => vi.clearAllMocks())

describe('RuntimeStatusStrip', () => {
  it('renders healthy status items with ok text', () => {
    render(<RuntimeStatusStrip runtimeStatus={makeRuntimeStatus(healthyItems)} />)
    const okElements = screen.getAllByText('ok')
    expect(okElements.length).toBeGreaterThanOrEqual(1)
  })

  it('renders degraded status', () => {
    const items = [
      { key: 'modelGovernance', label: 'Model Governance', status: 'degraded', summary: '1 governance blocker requires review' },
    ]
    render(<RuntimeStatusStrip runtimeStatus={makeRuntimeStatus(items)} />)
    expect(screen.getByText('degraded')).toBeInTheDocument()
  })

  it('renders critical status', () => {
    const items = [
      { key: 'system', label: 'Backend', status: 'critical', summary: 'Backend unavailable' },
    ]
    render(<RuntimeStatusStrip runtimeStatus={makeRuntimeStatus(items)} />)
    expect(screen.getByText('critical')).toBeInTheDocument()
  })

  it('renders drone simulation item', () => {
    render(<RuntimeStatusStrip runtimeStatus={makeRuntimeStatus(healthyItems)} />)
    expect(screen.getByText('Drone Simulation')).toBeInTheDocument()
  })

  it('renders drone fusion item with ok status', () => {
    render(<RuntimeStatusStrip runtimeStatus={makeRuntimeStatus(healthyItems)} />)
    expect(screen.getByText('Drone Fusion')).toBeInTheDocument()
  })

  it('renders model governance blocker as degraded', () => {
    const items = [
      { key: 'modelGovernance', label: 'Model Governance', status: 'degraded', summary: 'Promotion disabled while file writes are locked' },
    ]
    render(<RuntimeStatusStrip runtimeStatus={makeRuntimeStatus(items)} />)
    expect(screen.getByText('Model Governance')).toBeInTheDocument()
    expect(screen.getByText('degraded')).toBeInTheDocument()
  })

  it('has tone CSS class for each status card', () => {
    render(<RuntimeStatusStrip runtimeStatus={makeRuntimeStatus(healthyItems)} />)
    const okCards = document.querySelectorAll('.tone-ok')
    expect(okCards.length).toBeGreaterThanOrEqual(1)
  })

  it('has tone-degraded class for degraded items', () => {
    const items = [
      { key: 'modelGovernance', label: 'Model Governance', status: 'degraded', summary: 'Blocker present' },
    ]
    render(<RuntimeStatusStrip runtimeStatus={makeRuntimeStatus(items)} />)
    const degradedCards = document.querySelectorAll('.tone-degraded')
    expect(degradedCards.length).toBeGreaterThanOrEqual(1)
  })

  it('has tone-critical class for critical items', () => {
    const items = [
      { key: 'system', label: 'Backend', status: 'critical', summary: 'Down' },
    ]
    render(<RuntimeStatusStrip runtimeStatus={makeRuntimeStatus(items)} />)
    const criticalCards = document.querySelectorAll('.tone-critical')
    expect(criticalCards.length).toBeGreaterThanOrEqual(1)
  })

  it('no forbidden wording appears', () => {
    render(<RuntimeStatusStrip runtimeStatus={makeRuntimeStatus(healthyItems)} />)
    const bodyText = document.body.textContent.toLowerCase()
    for (const word of FORBIDDEN) {
      expect(bodyText).not.toContain(word)
    }
  })

  it('renders without crashing when items is empty', () => {
    expect(() => {
      render(<RuntimeStatusStrip runtimeStatus={makeRuntimeStatus([])} />)
    }).not.toThrow()
  })

  it('shows compact waiting message while loading runtime status', () => {
    render(<RuntimeStatusStrip runtimeStatus={{ ...makeRuntimeStatus([]), loading: true }} compact />)
    expect(screen.getByText('Signed in, waiting for runtime status')).toBeInTheDocument()
  })
})
