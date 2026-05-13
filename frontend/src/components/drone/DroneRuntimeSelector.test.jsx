import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import DroneRuntimeSelector from './DroneRuntimeSelector'

describe('DroneRuntimeSelector', () => {
  it('shows runtimes and launch buttons', async () => {
    const onLaunch = vi.fn()
    render(
      <DroneRuntimeSelector
        runtimeStatus={{ selected_runtime: 'AirSimNH', available_runtimes: ['AirSimNH', 'Blocks'], fallback_used: false, connected: true }}
        onLaunchRuntime={onLaunch}
      />,
    )
    expect(screen.getByText(/City Runtime Selector/i)).toBeInTheDocument()
    expect(screen.getAllByText(/AirSimNH/).length).toBeGreaterThan(0)
    await userEvent.click(screen.getByRole('button', { name: /Launch Blocks/i }))
    expect(onLaunch).toHaveBeenCalledWith('Blocks')
  })
})
