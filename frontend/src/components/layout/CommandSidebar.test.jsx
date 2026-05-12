import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import CommandSidebar from './CommandSidebar'
import { commandNavigation } from '../../navigation/commandNavigation'

const mockRuntimeStatus = {
  overall: 'ok',
  items: [],
  byKey: {
    droneSimulation: { key: 'droneSimulation', label: 'Drone Simulation', status: 'ok', summary: 'ok' },
  },
  loading: false,
  error: null,
  refresh: vi.fn(),
}

beforeEach(() => vi.clearAllMocks())

describe('CommandSidebar', () => {
  it('renders navigation groups', () => {
    render(
      <CommandSidebar
        currentPage="dashboard"
        navigation={commandNavigation}
        onNavigate={vi.fn()}
        runtimeStatus={mockRuntimeStatus}
      />,
    )
    // At least the Overview group should be visible
    expect(screen.getByText('Overview')).toBeInTheDocument()
  })

  it('renders Drone Operations group label', () => {
    render(
      <CommandSidebar
        currentPage="dashboard"
        navigation={commandNavigation}
        onNavigate={vi.fn()}
        runtimeStatus={mockRuntimeStatus}
      />,
    )
    expect(screen.getByText('Drone Operations')).toBeInTheDocument()
  })

  it('calls onNavigate when a nav item is clicked', () => {
    const onNavigate = vi.fn()
    render(
      <CommandSidebar
        currentPage="dashboard"
        navigation={commandNavigation}
        onNavigate={onNavigate}
        runtimeStatus={mockRuntimeStatus}
      />,
    )
    // Click the Dashboard nav item
    const dashboardButton = screen.getByRole('button', { name: /Dashboard/i })
    fireEvent.click(dashboardButton)
    expect(onNavigate).toHaveBeenCalledWith('dashboard')
  })

  it('renders Drone Operations Hub nav item', () => {
    render(
      <CommandSidebar
        currentPage="dashboard"
        navigation={commandNavigation}
        onNavigate={vi.fn()}
        runtimeStatus={mockRuntimeStatus}
      />,
    )
    expect(screen.getByText('Drone Operations Hub')).toBeInTheDocument()
  })

  it('renders Intelligence group label', () => {
    render(
      <CommandSidebar
        currentPage="dashboard"
        navigation={commandNavigation}
        onNavigate={vi.fn()}
        runtimeStatus={mockRuntimeStatus}
      />,
    )
    expect(screen.getByText('Intelligence')).toBeInTheDocument()
  })
})
