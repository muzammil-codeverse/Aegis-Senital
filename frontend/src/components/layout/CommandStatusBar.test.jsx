import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import CommandStatusBar from './CommandStatusBar'

beforeEach(() => vi.clearAllMocks())

describe('CommandStatusBar', () => {
  it('renders without crashing', () => {
    expect(() => {
      render(
        <CommandStatusBar
          metrics={{}}
          runtimeStatus={{ overall: 'ok' }}
          currentPage="dashboard"
        />,
      )
    }).not.toThrow()
  })

  it('shows websocket/overall runtime status', () => {
    render(
      <CommandStatusBar
        metrics={{}}
        runtimeStatus={{ overall: 'ok' }}
        currentPage="dashboard"
      />,
    )
    expect(screen.getByText('ok')).toBeInTheDocument()
  })

  it('shows the current page route', () => {
    render(
      <CommandStatusBar
        metrics={{}}
        runtimeStatus={{ overall: 'ok' }}
        currentPage="drone-operations"
      />,
    )
    expect(screen.getByText('drone-operations')).toBeInTheDocument()
  })

  it('shows Overall label', () => {
    render(
      <CommandStatusBar
        metrics={{}}
        runtimeStatus={{ overall: 'degraded' }}
        currentPage="dashboard"
      />,
    )
    expect(screen.getByText('degraded')).toBeInTheDocument()
  })

  it('renders with empty metrics without crashing', () => {
    expect(() => {
      render(
        <CommandStatusBar
          metrics={undefined}
          runtimeStatus={null}
          currentPage="dashboard"
        />,
      )
    }).not.toThrow()
  })
})
