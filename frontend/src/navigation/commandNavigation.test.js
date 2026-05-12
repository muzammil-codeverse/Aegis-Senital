import { describe, it, expect, vi, beforeEach } from 'vitest'
import { commandNavigation, commandRouteIndex } from './commandNavigation'

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

beforeEach(() => vi.clearAllMocks())

describe('commandNavigation', () => {
  it('has at least 4 groups', () => {
    expect(commandNavigation.length).toBeGreaterThanOrEqual(4)
  })

  it('has a group labeled Drone Operations', () => {
    const group = commandNavigation.find(g => g.group === 'Drone Operations')
    expect(group).toBeDefined()
  })

  it('Drone Operations group has required item ids', () => {
    const group = commandNavigation.find(g => g.group === 'Drone Operations')
    const ids = group.items.map(item => item.id)
    expect(ids).toContain('drone-operations')
    expect(ids).toContain('drone-simulation')
    expect(ids).toContain('drone-mission-planner')
    expect(ids).toContain('drone-fusion')
  })

  it('Intelligence group exists and has required item ids', () => {
    const group = commandNavigation.find(g => g.group === 'Intelligence')
    expect(group).toBeDefined()
    const ids = group.items.map(item => item.id)
    expect(ids).toContain('cases')
    expect(ids).toContain('identities')
    expect(ids).toContain('osint-enrichment')
    expect(ids).toContain('model-governance')
  })

  it('commandRouteIndex contains all expected ids', () => {
    const expectedIds = [
      'dashboard',
      'drone-operations',
      'drone-simulation',
      'drone-mission-planner',
      'drone-fusion',
      'cases',
      'identities',
      'model-governance',
    ]
    for (const id of expectedIds) {
      expect(commandRouteIndex[id]).toBeDefined()
    }
  })

  it('no item label contains forbidden wording', () => {
    const allLabels = commandNavigation.flatMap(g =>
      g.items.map(item => item.label.toLowerCase()),
    )
    for (const label of allLabels) {
      for (const word of FORBIDDEN) {
        expect(label).not.toContain(word)
      }
    }
  })

  it('no item description contains forbidden wording', () => {
    const allDescriptions = commandNavigation.flatMap(g =>
      g.items.map(item => (item.description || '').toLowerCase()),
    )
    for (const desc of allDescriptions) {
      for (const word of FORBIDDEN) {
        expect(desc).not.toContain(word)
      }
    }
  })
})
