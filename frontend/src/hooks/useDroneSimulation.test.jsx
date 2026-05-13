import { act, renderHook } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { useDroneSimulation } from './useDroneSimulation'

vi.mock('../api/droneSimulationApi', () => ({
  droneSimulationApi: {
    getStatus: vi.fn().mockResolvedValue({ item: { session: { active: false }, runtime_status: { connected: true }, health: { status: 'ok' } } }),
    getFlightPath: vi.fn().mockResolvedValue({ items: [] }),
    getLatestFrame: vi.fn().mockResolvedValue({ item: null }),
    getRuntimeStatus: vi.fn().mockResolvedValue({ item: { connected: true } }),
    listCameras: vi.fn().mockResolvedValue({ items: [] }),
    startSession: vi.fn().mockRejectedValue({ status: 403, message: 'forbidden' }),
  },
}))

vi.mock('./useAuth', () => ({
  useAuth: () => ({
    token: 'tok',
    authRequired: true,
    hasPermission: p => p === 'drone:read' || p === 'drone:control',
  }),
}))

describe('useDroneSimulation', () => {
  it('maps start-session 403 failure to scoped permission text', async () => {
    const { result } = renderHook(() => useDroneSimulation({ pollMs: 0 }))
    await act(async () => {
      await result.current.startSession()
    })
    expect(result.current.actionError).toContain('403 permission denied')
  })
})

