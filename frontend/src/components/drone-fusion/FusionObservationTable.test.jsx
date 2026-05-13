import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import FusionObservationTable from './FusionObservationTable'

describe('FusionObservationTable', () => {
  it('shows mission context and runtime columns for drone observations', () => {
    render(
      <FusionObservationTable
        observations={[
          {
            observation_id: 'obs_1',
            source_type: 'drone_simulation',
            source_id: 'drone_sim_01_front_center',
            event_type: 'candidate_cross_source_observation',
            timestamp: '2026-05-13T10:00:00Z',
            latitude: 30.1575,
            longitude: 71.5249,
            geo_missing: false,
            simulated: true,
            metadata: {
              drone_camera: 'front_center',
              city_runtime: 'AirSimNH',
              mission_id: 'mission_123',
            },
          },
        ]}
      />,
    )
    expect(screen.getByText(/Mission Context/i)).toBeInTheDocument()
    expect(screen.getByText(/AirSimNH/i)).toBeInTheDocument()
    expect(screen.getByText(/mission:mission_123/i)).toBeInTheDocument()
  })
})
