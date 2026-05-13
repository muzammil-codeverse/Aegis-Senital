import { act, renderHook } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { useRuntimeStatus } from './useRuntimeStatus'

const getSystemHealth = vi.fn()

vi.mock('../api/metricsApi', () => ({
  getSystemHealth: (...args) => getSystemHealth(...args),
}))

vi.mock('./useAuth', () => ({
  useAuth: () => ({
    authenticated: false,
    hasPermission: () => false,
  }),
}))

describe('useRuntimeStatus auth gating', () => {
  it('does not poll protected runtime endpoints while unauthenticated', async () => {
    const { result } = renderHook(() => useRuntimeStatus({ pollMs: 5 }))
    await act(async () => {})
    expect(getSystemHealth).not.toHaveBeenCalled()
    expect(result.current.items).toEqual([])
  })
})
