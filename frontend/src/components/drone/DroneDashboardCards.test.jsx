import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import DroneStatusPanel from './DroneStatusPanel'

describe('DroneDashboardCards', () => {
  it('renders simulated status metrics', () => {
    render(
      <DroneStatusPanel
        wsStatus="open"
        status={{
          session: { status: 'running', active: true },
          connection: { status: 'connected' },
          health: { status: 'healthy' },
        }}
        stats={{ framesProcessed: 12, telemetryUpdates: 22, events: 3 }}
      />,
    )

    expect(screen.getByText(/simulated aerial source/i)).toBeTruthy()
    expect(screen.getByText(/frames processed/i)).toBeTruthy()
    expect(screen.getByText(/telemetry updates/i)).toBeTruthy()
    expect(screen.getByText(/detected events/i)).toBeTruthy()
  })
})
