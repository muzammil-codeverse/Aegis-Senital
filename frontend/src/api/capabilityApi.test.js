import { beforeEach, describe, expect, it, vi } from 'vitest'
import { getCapabilities, getCapabilitySummary, refreshCapabilities } from './capabilityApi'

const requestMock = vi.fn()
vi.mock('./client', () => ({
  request: (...args) => requestMock(...args),
}))

describe('capabilityApi', () => {
  beforeEach(() => {
    requestMock.mockReset()
  })

  it('parses capability list responses', async () => {
    requestMock.mockResolvedValueOnce({
      items: [{ id: 'backend_api', state: 'READY' }],
      count: 1,
      dependencies: { backend_api: { dependencies: [] } },
      status: 'ok',
    })

    const result = await getCapabilities()

    expect(requestMock.mock.calls[0][0].url).toBe('/api/capabilities')
    expect(result.items).toHaveLength(1)
    expect(result.items[0].state).toBe('READY')
    expect(result.count).toBe(1)
  })

  it('unwraps summary item payloads', async () => {
    requestMock.mockResolvedValueOnce({ item: { total: 31, cold: 20 }, status: 'ok' })

    const result = await getCapabilitySummary()

    expect(requestMock.mock.calls[0][0].url).toBe('/api/capabilities/summary')
    expect(result.total).toBe(31)
    expect(result.cold).toBe(20)
  })

  it('parses refresh responses with summary', async () => {
    requestMock.mockResolvedValueOnce({
      items: [{ id: 'drone_simulation', state: 'COLD' }],
      count: 1,
      summary: { cold: 1 },
    })

    const result = await refreshCapabilities()

    expect(requestMock.mock.calls[0][0].method).toBe('POST')
    expect(result.summary.cold).toBe(1)
  })
})
