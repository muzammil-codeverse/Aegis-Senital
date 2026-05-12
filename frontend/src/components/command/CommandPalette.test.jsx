import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import CommandPalette from './CommandPalette'

const FORBIDDEN = [
  'suspect confirmed',
  'identity confirmed',
  'target confirmed',
  'criminal confirmed',
  'attacker confirmed',
  'guilty',
  'real drone pursuit',
  'confirmed threat',
  'confirmed terrorist',
]

const droneRouteResult = {
  key: 'route:drone-fusion',
  kind: 'route',
  label: 'Drone Fusion',
  description: 'Cross-source drone and fixed camera fusion',
  route: 'drone-fusion',
  meta: 'Drone Operations',
}

function makeSections(items) {
  return [{ title: 'Routes', items }]
}

beforeEach(() => vi.clearAllMocks())

describe('CommandPalette', () => {
  it('renders when isOpen is true', () => {
    render(
      <CommandPalette
        isOpen
        query=""
        sections={[]}
        flatResults={[]}
        selectedIndex={0}
        loading={false}
        error={null}
        onClose={vi.fn()}
        onQueryChange={vi.fn()}
        onSelectIndex={vi.fn()}
      />,
    )
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('does not render when isOpen is false', () => {
    render(
      <CommandPalette
        isOpen={false}
        query=""
        sections={[]}
        flatResults={[]}
        selectedIndex={0}
        loading={false}
        error={null}
        onClose={vi.fn()}
        onQueryChange={vi.fn()}
        onSelectIndex={vi.fn()}
      />,
    )
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('renders route search results', () => {
    const sections = makeSections([droneRouteResult])
    render(
      <CommandPalette
        isOpen
        query="drone"
        sections={sections}
        flatResults={[droneRouteResult]}
        selectedIndex={0}
        loading={false}
        error={null}
        onClose={vi.fn()}
        onQueryChange={vi.fn()}
        onSelectIndex={vi.fn()}
      />,
    )
    expect(screen.getByText('Drone Fusion')).toBeInTheDocument()
  })

  it('shows drone fusion route when sections include it', () => {
    const sections = makeSections([droneRouteResult])
    render(
      <CommandPalette
        isOpen
        query="drone"
        sections={sections}
        flatResults={[droneRouteResult]}
        selectedIndex={0}
        loading={false}
        error={null}
        onClose={vi.fn()}
        onQueryChange={vi.fn()}
        onSelectIndex={vi.fn()}
      />,
    )
    expect(screen.getByText('Drone Fusion')).toBeInTheDocument()
    expect(screen.getByText('Cross-source drone and fixed camera fusion')).toBeInTheDocument()
  })

  it('does not show forbidden wording', () => {
    const sections = makeSections([droneRouteResult])
    render(
      <CommandPalette
        isOpen
        query=""
        sections={sections}
        flatResults={[droneRouteResult]}
        selectedIndex={0}
        loading={false}
        error={null}
        onClose={vi.fn()}
        onQueryChange={vi.fn()}
        onSelectIndex={vi.fn()}
      />,
    )
    const bodyText = document.body.textContent.toLowerCase()
    for (const word of FORBIDDEN) {
      expect(bodyText).not.toContain(word)
    }
  })

  it('calls onQueryChange when search input changes', () => {
    const onQueryChange = vi.fn()
    render(
      <CommandPalette
        isOpen
        query=""
        sections={[]}
        flatResults={[]}
        selectedIndex={0}
        loading={false}
        error={null}
        onClose={vi.fn()}
        onQueryChange={onQueryChange}
        onSelectIndex={vi.fn()}
      />,
    )
    const input = screen.getByRole('textbox')
    fireEvent.change(input, { target: { value: 'drone' } })
    expect(onQueryChange).toHaveBeenCalledWith('drone')
  })

  it('calls onClose when backdrop is clicked', () => {
    const onClose = vi.fn()
    render(
      <CommandPalette
        isOpen
        query=""
        sections={[]}
        flatResults={[]}
        selectedIndex={0}
        loading={false}
        error={null}
        onClose={onClose}
        onQueryChange={vi.fn()}
        onSelectIndex={vi.fn()}
      />,
    )
    // The backdrop is the outer div with role="presentation"
    const backdrop = document.querySelector('.command-palette-backdrop')
    fireEvent.click(backdrop)
    expect(onClose).toHaveBeenCalled()
  })

  it('shows loading state text', () => {
    render(
      <CommandPalette
        isOpen
        query="test"
        sections={[]}
        flatResults={[]}
        selectedIndex={0}
        loading
        error={null}
        onClose={vi.fn()}
        onQueryChange={vi.fn()}
        onSelectIndex={vi.fn()}
      />,
    )
    expect(screen.getByText(/Searching operational data/i)).toBeInTheDocument()
  })
})
