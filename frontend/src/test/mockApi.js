import { vi } from 'vitest'

export function mockModule(path, factory) {
  vi.mock(path, factory)
}

export function createApiMock(overrides = {}) {
  return {
    data: null,
    loading: false,
    error: null,
    refresh: vi.fn(),
    ...overrides,
  }
}
