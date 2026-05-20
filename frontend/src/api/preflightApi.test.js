import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  checkPreflightCapability,
  getLatestPreflight,
  getPreflightModes,
  getPreflightRun,
  getPreflightSummary,
  runPreflight,
} from './preflightApi'

const requestMock = vi.fn()
vi.mock('./client', () => ({
  request: (...args) => requestMock(...args),
}))

describe('preflightApi', () => {
  beforeEach(() => {
    requestMock.mockReset()
  })

  it('parses latest and summary item responses', async () => {
    requestMock.mockResolvedValueOnce({ item: { overall_status: 'NOT_STARTED', results: [] }, status: 'ok' })
    requestMock.mockResolvedValueOnce({ item: { total: 6, by_state: { READY: 6 } }, status: 'ok' })

    const latest = await getLatestPreflight()
    const summary = await getPreflightSummary()

    expect(requestMock.mock.calls[0][0].url).toBe('/api/preflight/latest')
    expect(requestMock.mock.calls[1][0].url).toBe('/api/preflight/summary')
    expect(latest.overall_status).toBe('NOT_STARTED')
    expect(summary.total).toBe(6)
  })

  it('runs exhibition preflight with selected capabilities', async () => {
    requestMock.mockResolvedValueOnce({ item: { mode: 'EXHIBITION', results: [] }, status: 'ok' })

    const result = await runPreflight('EXHIBITION', ['llm_osint'])

    expect(requestMock.mock.calls[0][0]).toMatchObject({
      url: '/api/preflight/run',
      method: 'POST',
      data: { mode: 'EXHIBITION', selected_capabilities: ['llm_osint'] },
    })
    expect(result.mode).toBe('EXHIBITION')
  })

  it('fetches runs, modes, and single capability checks', async () => {
    requestMock.mockResolvedValueOnce({ item: { run_id: 'run-1' }, status: 'ok' })
    requestMock.mockResolvedValueOnce({ items: [{ mode: 'QUICK' }], status: 'ok' })
    requestMock.mockResolvedValueOnce({ item: { capability_id: 'llm_osint' }, status: 'ok' })

    expect((await getPreflightRun('run-1')).run_id).toBe('run-1')
    expect(await getPreflightModes()).toEqual([{ mode: 'QUICK' }])
    expect((await checkPreflightCapability('llm_osint')).capability_id).toBe('llm_osint')
  })
})

