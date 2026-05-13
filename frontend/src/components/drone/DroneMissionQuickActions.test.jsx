import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import DroneMissionQuickActions from './DroneMissionQuickActions'

describe('DroneMissionQuickActions', () => {
  it('supports preset selection and run action', async () => {
    const onSelect = vi.fn()
    const onRun = vi.fn()
    render(
      <DroneMissionQuickActions
        presets={['fixed_camera_handoff_demo', 'perimeter_patrol']}
        selectedPreset="fixed_camera_handoff_demo"
        onSelectPreset={onSelect}
        onRunPreset={onRun}
      />,
    )
    expect(screen.getByText(/Mission Quick Actions/i)).toBeInTheDocument()
    await userEvent.selectOptions(screen.getByRole('combobox'), 'perimeter_patrol')
    expect(onSelect).toHaveBeenCalledWith('perimeter_patrol')
    await userEvent.click(screen.getByRole('button', { name: /Start mission demo/i }))
    expect(onRun).toHaveBeenCalled()
  })
})
