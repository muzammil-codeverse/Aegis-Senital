import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import MapCommandCenter from './MapCommandCenter'

describe('MapCommandCenter', () => {
  it('renders drone route and handoff layer status chips', () => {
    render(
      <MapCommandCenter
        gisConfig={{ provider: 'local_mock', map: { default_center: { latitude: 30.1575, longitude: 71.5249 } } }}
        layers={{
          cameras: [{ camera_id: 'cam_01', latitude: 30.1575, longitude: 71.5249, metadata: {} }],
          camera_fovs: [],
          geofences: [],
          drone_paths: [],
          active_mission_paths: [{ mission_id: 'm1', points: [{ latitude: 30.1575, longitude: 71.5249 }, { latitude: 30.1579, longitude: 71.5252 }] }],
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

  it('renders local simulation overlay when GIS camera geometry is empty', () => {
    render(
      <MapCommandCenter
        gisConfig={{ provider: 'local_mock', map: { default_center: { latitude: 30.1575, longitude: 71.5249 } } }}
        layers={{
          cameras: [],
          camera_fovs: [],
          geofences: [],
          drone_paths: [],
          active_mission_paths: [],
          completed_mission_paths: [],
          fixed_camera_handoffs: [],
          event_markers: [],
          case_markers: [],
          heatmap_cells: [],
          stream_status_by_camera: {},
        }}
        simulationCameras={[{
          camera_id: 'CAM-BANK-01',
          name: 'Bank Main Entrance',
          status: 'online',
          location: { x: 360, y: 260, z: 5 },
          orientation: { yaw: 45 },
          coverage: { fov_degrees: 90, range_meters: 80 },
        }]}
        simulationDrones={[{
          drone_id: 'DRONE-ALPHA',
          status: 'standby',
          current_location: { x: 370, y: 270, z: 40 },
        }]}
        canWriteGis={false}
        onSaveCamera={vi.fn()}
        filters={{}}
        onFiltersChange={vi.fn()}
      />,
    )

    expect(screen.getAllByText(/Local simulation map/i).length).toBeGreaterThan(0)
    expect(screen.getByText(/CAM-BANK-01:/i)).toBeInTheDocument()
    expect(screen.queryByText(/Authentication required/i)).not.toBeInTheDocument()
  })
})
