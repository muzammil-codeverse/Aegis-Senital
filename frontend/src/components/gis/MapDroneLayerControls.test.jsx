import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import MapCommandCenter from './MapCommandCenter'

describe('MapDroneLayerControls', () => {
  it('shows drone layer counters for active routes and handoffs', () => {
    render(
      <MapCommandCenter
        gisConfig={{ provider: 'local_mock', map: { default_center: { latitude: 30.1575, longitude: 71.5249 } } }}
        layers={{
          cameras: [{ camera_id: 'cam_01', latitude: 30.1575, longitude: 71.5249, metadata: {} }],
          camera_fovs: [],
          geofences: [],
          drone_paths: [],
          active_mission_paths: [{ mission_id: 'm1', points: [{ latitude: 30.1575, longitude: 71.5249 }] }],
          completed_mission_paths: [],
          fixed_camera_handoffs: [{ handoff_id: 'h1', from: { latitude: 30.1575, longitude: 71.5249 }, to: { latitude: 30.1579, longitude: 71.5252 } }],
          event_markers: [],
          case_markers: [],
          heatmap_cells: [],
          stream_status_by_camera: {},
        }}
        canWriteGis={false}
        onSaveCamera={vi.fn()}
        filters={{}}
        onFiltersChange={vi.fn()}
      />, 
    )

    expect(screen.getByText(/active routes:/i)).toBeInTheDocument()
    expect(screen.getByText(/handoff arrows:/i)).toBeInTheDocument()
  })
})
