import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import CameraGrid from './CameraGrid'

vi.mock('../../hooks/useStreamControls', () => ({
  useStreamControls: () => ({
    busyCameraId: null,
    error: null,
    start: vi.fn(),
    stop: vi.fn(),
    pause: vi.fn(),
    restart: vi.fn(),
  }),
}))

describe('CameraGrid exhibition camera rendering', () => {
  it('renders simulated cameras with visual snapshot imagery', () => {
    render(
      <CameraGrid
        cameras={[{
          camera_id: 'CAM-BANK-01',
          name: 'Bank Main Entrance',
          status: 'online',
          priority: 'critical',
          simulated: true,
          source_type: 'fixed_cctv',
          zone_name: 'Financial District',
          snapshotUrl: 'http://localhost:8000/api/visual-scenario/snapshots/CAM-BANK-01',
        }]}
        loading={false}
        error={null}
      />,
    )

    expect(screen.getByText('Bank Main Entrance')).toBeInTheDocument()
    expect(screen.getByText('CAM-BANK-01')).toBeInTheDocument()
    expect(screen.getByAltText('CAM-BANK-01 visual snapshot')).toHaveAttribute(
      'src',
      'http://localhost:8000/api/visual-scenario/snapshots/CAM-BANK-01',
    )
  })

  it('renders an exhibition-safe zero state when simulation cameras are absent', () => {
    render(<CameraGrid cameras={[]} loading={false} error={null} />)

    expect(screen.getByText(/No simulation cameras loaded/i)).toBeInTheDocument()
    expect(screen.queryByText(/Authentication required/i)).not.toBeInTheDocument()
  })
})
