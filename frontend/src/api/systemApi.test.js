import { describe, expect, it } from 'vitest'
import { getPublicHealth, getSystemHealth, getSystemReadiness } from './systemApi'

describe('systemApi exports', () => {
  it('re-exports runtime health functions', () => {
    expect(typeof getPublicHealth).toBe('function')
    expect(typeof getSystemHealth).toBe('function')
    expect(typeof getSystemReadiness).toBe('function')
  })
})

