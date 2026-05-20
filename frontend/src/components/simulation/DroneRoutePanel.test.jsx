import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import DroneRoutePanel from './DroneRoutePanel'

const MOCK_ROUTE = {
  route_id: 'route-abc12345',
  drone_id: 'DRONE-ALPHA',
  status: 'tracking',
  mission_id: 'mission-abc12345',
  linked_actor_id: 'SUSPECT-001',
  waypoints: [
    {
      waypoint_id: 'drone-wp-00',
      offset_seconds: 25,
      zone_name: 'Financial District',
      location: { x: 120, y: 80, z: 40 },
      confidence: 0.95,
      metadata: { phase: 'dispatch', description: 'DRONE-ALPHA home' },
    },
  ],
  metadata: {
    airsim_ready: false,
    camera_feed_uri: 'rtsp://drone-alpha/feed',
  },
}

describe('DroneRoutePanel', () => {
  it('renders standby when not dispatched', () => {
    render(<DroneRoutePanel droneRoute={null} droneDispatched={false} />)
    expect(screen.getByText(/awaiting dispatch/i)).toBeTruthy()
  })

  it('renders route when dispatched', () => {
    render(<DroneRoutePanel droneRoute={MOCK_ROUTE} droneDispatched={true} dispatchedDroneId="DRONE-ALPHA" />)
    const alphaLabels = screen.getAllByText(/DRONE-ALPHA/i)
    expect(alphaLabels.length).toBeGreaterThan(0)
  })

  it('shows TRACKING status', () => {
    render(<DroneRoutePanel droneRoute={MOCK_ROUTE} droneDispatched={true} dispatchedDroneId="DRONE-ALPHA" />)
    const trackingEls = screen.getAllByText(/TRACKING/i)
    expect(trackingEls.length).toBeGreaterThan(0)
  })

  it('shows linked actor', () => {
    render(<DroneRoutePanel droneRoute={MOCK_ROUTE} droneDispatched={true} />)
    expect(screen.getByText(/SUSPECT-001/i)).toBeTruthy()
  })

  it('shows AirSim provider status', () => {
    render(<DroneRoutePanel droneRoute={MOCK_ROUTE} droneDispatched={true} />)
    const airsimEls = screen.getAllByText(/AirSim/i)
    expect(airsimEls.length).toBeGreaterThan(0)
  })

  it('shows camera feed URI when available', () => {
    render(<DroneRoutePanel droneRoute={MOCK_ROUTE} droneDispatched={true} />)
    expect(screen.getByText(/rtsp:\/\/drone-alpha\/feed/i)).toBeTruthy()
  })
})
