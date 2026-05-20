import { describe, it, expect, vi, beforeEach } from 'vitest'
import { getOperationalView, getSuspectPath, getCameraHandoffs, getDroneRoute, getFusedTracking } from './scenarioApi'

const RUN_ID = 'run-abc12345678'

// Mock the base client so we don't hit the network
vi.mock('./client', () => ({
  request: vi.fn(),
  normalizeItemResponse: vi.fn(payload => ({ item: payload?.item || null })),
  normalizeListResponse: vi.fn(payload => ({ items: payload?.items || [] })),
  normalizeError: vi.fn(err => err?.message || 'error'),
}))

import { request, normalizeItemResponse, normalizeListResponse } from './client'

beforeEach(() => {
  vi.clearAllMocks()
})

describe('getOperationalView', () => {
  it('calls the correct URL', async () => {
    request.mockResolvedValue({ item: { run_id: RUN_ID } })
    const result = await getOperationalView(RUN_ID)
    expect(request).toHaveBeenCalledWith(expect.objectContaining({
      url: `/api/simulation/scenarios/runs/${RUN_ID}/operational-view`,
      method: 'GET',
    }))
    expect(result?.run_id).toBe(RUN_ID)
  })

  it('returns null when response is null', async () => {
    request.mockResolvedValue(null)
    const result = await getOperationalView(RUN_ID)
    expect(result).toBeNull()
  })
})

describe('getSuspectPath', () => {
  it('calls the correct URL and normalizes list', async () => {
    request.mockResolvedValue({ items: [{ waypoint_id: 'wp-1' }] })
    await getSuspectPath(RUN_ID)
    expect(request).toHaveBeenCalledWith(expect.objectContaining({
      url: `/api/simulation/scenarios/runs/${RUN_ID}/suspect-path`,
      method: 'GET',
    }))
  })
})

describe('getCameraHandoffs', () => {
  it('calls the correct URL', async () => {
    request.mockResolvedValue({ items: [] })
    await getCameraHandoffs(RUN_ID)
    expect(request).toHaveBeenCalledWith(expect.objectContaining({
      url: `/api/simulation/scenarios/runs/${RUN_ID}/camera-handoffs`,
      method: 'GET',
    }))
  })
})

describe('getDroneRoute', () => {
  it('calls the correct URL', async () => {
    request.mockResolvedValue({ drone_route: null, status: 'not_dispatched' })
    const result = await getDroneRoute(RUN_ID)
    expect(request).toHaveBeenCalledWith(expect.objectContaining({
      url: `/api/simulation/scenarios/runs/${RUN_ID}/drone-route`,
      method: 'GET',
    }))
    expect(result?.status).toBe('not_dispatched')
  })
})

describe('getFusedTracking', () => {
  it('calls the correct URL', async () => {
    request.mockResolvedValue({ item: { track_id: 'ftrack-abc' } })
    await getFusedTracking(RUN_ID)
    expect(request).toHaveBeenCalledWith(expect.objectContaining({
      url: `/api/simulation/scenarios/runs/${RUN_ID}/tracking`,
      method: 'GET',
    }))
  })
})
