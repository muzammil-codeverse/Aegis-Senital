import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import CommandCenterShell from './CommandCenterShell'

// Mock all hooks used internally
vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({
    hasPermission: () => true,
    user: { role: 'admin', username: 'test' },
    authenticated: true,
    permissions: ['*'],
    loading: false,
    error: null,
  }),
}))

vi.mock('../../hooks/useRuntimeStatus', () => ({
  useRuntimeStatus: () => ({
    overall: 'ok',
    items: [],
    byKey: {},
    loading: false,
    error: null,
    refresh: vi.fn(),
  }),
}))

vi.mock('../../hooks/useCommandPalette', () => ({
  useCommandPalette: () => ({
    isOpen: false,
    query: '',
    selectedIndex: 0,
    setQuery: vi.fn(),
    setSelectedIndex: vi.fn(),
    open: vi.fn(),
    close: vi.fn(),
    toggle: vi.fn(),
  }),
}))

vi.mock('../../hooks/useGlobalSearch', () => ({
  useGlobalSearch: () => ({
    sections: [],
    flatResults: [],
    loading: false,
    error: null,
    navigateForResult: vi.fn(),
  }),
}))

// Mock styles helper that may call window APIs
vi.mock('../../styles/commandCenterTheme', () => ({
  commandCenterCssVars: () => ({}),
  normalizeRuntimeTone: (s) => s,
}))

const defaultProps = {
  currentPage: 'dashboard',
  onNavigate: vi.fn(),
  pageMeta: { id: 'dashboard', label: 'Dashboard', description: 'Operational overview' },
  metrics: {},
  websocketStatus: 'connected',
  lastMessageAt: null,
  reconnectCount: 0,
}

beforeEach(() => vi.clearAllMocks())

describe('CommandCenterShell', () => {
  it('renders children when given children prop', () => {
    render(
      <CommandCenterShell {...defaultProps}>
        <div>test-child-content</div>
      </CommandCenterShell>,
    )
    expect(screen.getByText('test-child-content')).toBeInTheDocument()
  })

  it('does not crash when rendered with minimal props', () => {
    expect(() => {
      render(<CommandCenterShell {...defaultProps} />)
    }).not.toThrow()
  })

  it('renders page title from pageMeta', () => {
    render(<CommandCenterShell {...defaultProps} />)
    // There may be multiple elements with "Dashboard" (sidebar nav + topbar heading)
    // Use getAllByText and check at least one exists
    const elements = screen.getAllByText('Dashboard')
    expect(elements.length).toBeGreaterThanOrEqual(1)
  })
})
