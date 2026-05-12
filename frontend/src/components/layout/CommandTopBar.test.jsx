import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import CommandTopBar from './CommandTopBar'

// UserMenu uses useAuth internally
vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({
    user: null,
    authenticated: false,
    permissions: [],
    loading: false,
    error: null,
    hasPermission: () => true,
    logout: vi.fn(),
  }),
}))

const defaultProps = {
  pageMeta: { id: 'dashboard', label: 'Dashboard', description: 'Operational overview' },
  websocketStatus: 'connected',
  lastMessageAt: null,
  reconnectCount: 0,
  runtimeStatus: { overall: 'ok' },
  onOpenPalette: vi.fn(),
}

beforeEach(() => vi.clearAllMocks())

describe('CommandTopBar', () => {
  it('renders without crashing', () => {
    expect(() => {
      render(<CommandTopBar {...defaultProps} />)
    }).not.toThrow()
  })

  it('renders page title from pageMeta', () => {
    render(<CommandTopBar {...defaultProps} />)
    expect(screen.getByText('Dashboard')).toBeInTheDocument()
  })

  it('has a Search button that triggers palette open', () => {
    const onOpenPalette = vi.fn()
    render(<CommandTopBar {...defaultProps} onOpenPalette={onOpenPalette} />)
    const searchButton = screen.getByRole('button', { name: /search/i })
    fireEvent.click(searchButton)
    expect(onOpenPalette).toHaveBeenCalled()
  })

  it('shows the Unified Command Center eyebrow', () => {
    render(<CommandTopBar {...defaultProps} />)
    expect(screen.getByText('Unified Command Center')).toBeInTheDocument()
  })

  it('shows websocket status', () => {
    render(<CommandTopBar {...defaultProps} websocketStatus="connected" />)
    expect(screen.getByText(/Alerts WS/i)).toBeInTheDocument()
  })

  it('shows runtime status pill', () => {
    render(<CommandTopBar {...defaultProps} runtimeStatus={{ overall: 'ok' }} />)
    expect(screen.getByText(/Runtime ok/i)).toBeInTheDocument()
  })
})
