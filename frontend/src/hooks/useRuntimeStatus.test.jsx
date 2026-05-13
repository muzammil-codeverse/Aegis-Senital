import { act, renderHook } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { useRuntimeStatus } from './useRuntimeStatus'

const getSystemHealth = vi.fn()
const getPublicHealth = vi.fn()
const authState = { authenticated: false, hasPermission: () => false }

vi.mock('../api/metricsApi', () => ({
  getSystemHealth: (...args) => getSystemHealth(...args),
  getPublicHealth: (...args) => getPublicHealth(...args),
}))

vi.mock('./useAuth', () => ({
  useAuth: () => authState,
}))

describe('useRuntimeStatus auth gating', () => {
  it('does not poll protected runtime endpoints while unauthenticated', async () => {
    authState.authenticated = false
    const { result } = renderHook(() => useRuntimeStatus({ pollMs: 5 }))
    await act(async () => {})
    expect(getSystemHealth).not.toHaveBeenCalled()
    expect(result.current.items).toEqual([])
  })

  it('maps 401 protected health to sign-in state instead of backend unavailable', async () => {
    authState.authenticated = true
    getSystemHealth.mockResolvedValue({ status: 'error', error: 'Authentication required' })
    const { result } = renderHook(() => useRuntimeStatus({ pollMs: 5 }))
    await act(async () => {
      await result.current.refresh()
    })
    const summaries = result.current.items.map(item => String(item.summary || '').toLowerCase())
    expect(summaries.some(summary => summary.includes('sign in'))).toBe(true)
    expect(summaries.some(summary => summary.includes('backend unavailable'))).toBe(false)
  })

  it('maps 503 readiness failures to degraded status once in runtime strip data', async () => {
    authState.authenticated = true
    getSystemHealth.mockResolvedValue({ status: 'degraded', checks: { database: { status: 'degraded', detail: 'Database not configured' } } })
    const { result } = renderHook(() => useRuntimeStatus({ pollMs: 5 }))
    await act(async () => {
      await result.current.refresh()
    })
    expect(result.current.byKey.system.status).toBe('degraded')
    expect(result.current.byKey.database.summary).toContain('Database not configured')
  })

  it('does not create unknown subsystem spam before data is available', async () => {
    authState.authenticated = true
    getSystemHealth.mockResolvedValue({ status: 'ok', checks: {} })
    const { result } = renderHook(() => useRuntimeStatus({ pollMs: 5 }))
    await act(async () => {
      await result.current.refresh()
    })
    expect(result.current.items.some(item => /health data unavailable/i.test(item.summary))).toBe(false)
  })

  it('uses non-production degraded wording for temporary runtime health issues', async () => {
    authState.authenticated = true
    getSystemHealth.mockResolvedValueOnce({ status: 'error', error: 'Health endpoint unavailable' })
    getPublicHealth.mockResolvedValueOnce({ status: 'ok' })
    const { result } = renderHook(() => useRuntimeStatus({ pollMs: 5 }))
    await act(async () => {
      await result.current.refresh()
    })
    expect(result.current.items[0]?.summary).toBe('Runtime health temporarily unavailable')
    expect(result.current.items[0]?.summary?.toLowerCase()).not.toContain('production')
  })
})
