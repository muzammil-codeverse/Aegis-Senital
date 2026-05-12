import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import Tactical3DStatusScene from './Tactical3DStatusScene'

// Mock @react-three/fiber since WebGL is not available in jsdom
vi.mock('@react-three/fiber', () => ({
  Canvas: ({ children }) => <div data-testid="r3f-canvas">{children}</div>,
  useFrame: vi.fn(),
  useThree: () => ({ camera: {}, gl: {} }),
}))

vi.mock('@react-three/drei', () => ({
  OrbitControls: () => null,
  Stars: () => null,
  Grid: () => null,
  PerspectiveCamera: () => null,
  Environment: () => null,
}))

// jsdom does not implement window.matchMedia — provide a minimal stub
beforeEach(() => {
  vi.clearAllMocks()
  if (!window.matchMedia) {
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: vi.fn().mockImplementation(query => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    })
  }
})

describe('Tactical3DStatusScene', () => {
  it('renders without crashing', () => {
    expect(() => {
      render(<Tactical3DStatusScene />)
    }).not.toThrow()
  })

  it('renders the fallback scene (no WebGL or reduced motion)', () => {
    // In jsdom, matchMedia returns false for prefers-reduced-motion
    // The component uses dynamic import for @react-three/fiber, so Canvas state starts null
    // This means it renders the ReducedMotionFallback initially
    render(<Tactical3DStatusScene summary="Test summary" />)
    // The fallback always renders when Canvas hasn't loaded yet or reduced motion is on
    expect(screen.getByText('Network status scene')).toBeInTheDocument()
  })

  it('renders the summary text passed as prop', () => {
    render(<Tactical3DStatusScene summary="Abstract visualization of camera, mission, and fusion dependencies." />)
    expect(screen.getByText('Abstract visualization of camera, mission, and fusion dependencies.')).toBeInTheDocument()
  })

  it('renders without external asset requirements', () => {
    // Should not throw even without Mapbox tokens, real backend, etc.
    expect(() => {
      render(<Tactical3DStatusScene />)
    }).not.toThrow()
  })

  it('renders the Tactical 3D eyebrow text', () => {
    render(<Tactical3DStatusScene />)
    expect(screen.getByText('Tactical 3D')).toBeInTheDocument()
  })

  it('uses default summary when no prop provided', () => {
    render(<Tactical3DStatusScene />)
    expect(screen.getByText('Abstract camera, drone, and fusion network overview.')).toBeInTheDocument()
  })
})
