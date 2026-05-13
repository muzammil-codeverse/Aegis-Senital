import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import DroneTelemetryPanel from './DroneTelemetryPanel'

describe('DroneTelemetryPanel', () => {
  it('renders telemetry and camera fields', () => {
    render(
      <DroneTelemetryPanel
        telemetry={{
          latitude: 30.1575,
          longitude: 71.5249,
          altitude_meters: 42.2,
          camera_name: 'front_center',
          orientation: { pitch: 0, roll: 0, yaw: 12 },
          position: { x: 1, y: 2, z: -3 },
          velocity: { x: 0.1, y: 0.2, z: -0.1 },
        }}
      />,
    )
    expect(screen.getByText(/Simulated telemetry readout/i)).toBeInTheDocument()
    expect(screen.getByText(/front_center/i)).toBeInTheDocument()
  })
})
