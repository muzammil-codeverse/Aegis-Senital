import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import DroneCameraGrid from './DroneCameraGrid'

describe('DroneCameraGrid', () => {
  it('renders camera cards and degraded empty-state wording', async () => {
    const onSelect = vi.fn()
    const onRefresh = vi.fn()
    render(
      <DroneCameraGrid
        cameras={[{ source_id: 'drone_sim_01_front_center', camera_name: 'front_center' }]}
        cameraFrames={{}}
        selectedCamera="front_center"
        onSelectCamera={onSelect}
        onRefreshCamera={onRefresh}
      />,
    )
    expect(screen.getByText(/front center/i)).toBeInTheDocument()
    expect(screen.getByText(/operator review required/i)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /select/i }))
    expect(onSelect).toHaveBeenCalled()
  })
})
