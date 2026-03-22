import { describe, it, expect } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import MutationStats, { computeMutationStats } from '../components/evolution/MutationStats'
import type { LineageNode } from '../types/evolution'

// --- Helper factory ---
function makeNode(overrides: Partial<LineageNode> = {}): LineageNode {
  return {
    candidateId: 'c-1',
    parentIds: [],
    generation: 1,
    island: 0,
    fitnessScore: 0.5,
    normalizedScore: 0,
    rejected: false,
    mutationType: 'rcc',
    survived: true,
    ...overrides,
  }
}

describe('computeMutationStats', () => {
  it('correctly computes delta as event.fitness - max(parent fitnesses)', () => {
    const events: LineageNode[] = [
      makeNode({ candidateId: 'seed-1', mutationType: 'seed', fitnessScore: 0.5, parentIds: [] }),
      makeNode({ candidateId: 'c-1', mutationType: 'rcc', fitnessScore: 0.7, parentIds: ['seed-1'] }),
    ]
    const stats = computeMutationStats(events)
    const rcc = stats.get('rcc')!
    expect(rcc.count).toBe(1)
    expect(rcc.improved).toBe(1)
    expect(rcc.avgDelta).toBeCloseTo(0.2, 4)
  })

  it('skips seed mutation type events', () => {
    const events: LineageNode[] = [
      makeNode({ candidateId: 'seed-1', mutationType: 'seed', fitnessScore: 0.5, parentIds: [] }),
      makeNode({ candidateId: 'seed-2', mutationType: 'seed', fitnessScore: 0.3, parentIds: [] }),
    ]
    const stats = computeMutationStats(events)
    expect(stats.size).toBe(0)
  })

  it('handles multiple mutation types with correct counts', () => {
    const events: LineageNode[] = [
      makeNode({ candidateId: 'seed-1', mutationType: 'seed', fitnessScore: 0.5, parentIds: [] }),
      makeNode({ candidateId: 'c-1', mutationType: 'rcc', fitnessScore: 0.7, parentIds: ['seed-1'] }),
      makeNode({ candidateId: 'c-2', mutationType: 'rcc', fitnessScore: 0.4, parentIds: ['seed-1'] }),
      makeNode({ candidateId: 'c-3', mutationType: 'structural', fitnessScore: 0.8, parentIds: ['seed-1'] }),
    ]
    const stats = computeMutationStats(events)
    expect(stats.get('rcc')!.count).toBe(2)
    expect(stats.get('rcc')!.improved).toBe(1)
    expect(stats.get('structural')!.count).toBe(1)
    expect(stats.get('structural')!.improved).toBe(1)
  })

  it('returns empty map for empty events array', () => {
    const stats = computeMutationStats([])
    expect(stats.size).toBe(0)
  })
})

describe('MutationStats', () => {
  it('renders a table with one row per non-seed mutation type', () => {
    const events: LineageNode[] = [
      makeNode({ candidateId: 'seed-1', mutationType: 'seed', fitnessScore: 0.5, parentIds: [] }),
      makeNode({ candidateId: 'c-1', mutationType: 'rcc', fitnessScore: 0.7, parentIds: ['seed-1'] }),
      makeNode({ candidateId: 'c-2', mutationType: 'structural', fitnessScore: 0.6, parentIds: ['seed-1'] }),
    ]
    render(<MutationStats lineageEvents={events} />)
    expect(screen.getByText('rcc')).toBeInTheDocument()
    expect(screen.getByText('structural')).toBeInTheDocument()
    expect(screen.queryByText('seed')).not.toBeInTheDocument()
  })

  it('shows count, improved, rate, and avg delta for each row', () => {
    const events: LineageNode[] = [
      makeNode({ candidateId: 'seed-1', mutationType: 'seed', fitnessScore: 0.5, parentIds: [] }),
      makeNode({ candidateId: 'c-1', mutationType: 'rcc', fitnessScore: 0.7, parentIds: ['seed-1'] }),
      makeNode({ candidateId: 'c-2', mutationType: 'rcc', fitnessScore: 0.4, parentIds: ['seed-1'] }),
    ]
    render(<MutationStats lineageEvents={events} />)
    // Count = 2 for rcc
    const table = screen.getByRole('table')
    const rows = within(table).getAllByRole('row')
    // header + 1 data row (rcc)
    expect(rows.length).toBe(2)
    // Check numeric values are rendered
    expect(screen.getByText('2')).toBeInTheDocument()
    // Improved = 1
    expect(screen.getByText('1')).toBeInTheDocument()
    // Rate = 50.0%
    expect(screen.getByText('50.0%')).toBeInTheDocument()
  })

  it('shows "No mutation data" when lineage events is empty', () => {
    render(<MutationStats lineageEvents={[]} />)
    expect(screen.getByText('No mutation data')).toBeInTheDocument()
  })

  it('uses MUTATION_COLORS for badge styling', () => {
    const events: LineageNode[] = [
      makeNode({ candidateId: 'seed-1', mutationType: 'seed', fitnessScore: 0.5, parentIds: [] }),
      makeNode({ candidateId: 'c-1', mutationType: 'rcc', fitnessScore: 0.7, parentIds: ['seed-1'] }),
    ]
    render(<MutationStats lineageEvents={events} />)
    const badge = screen.getByText('rcc')
    // rcc color is #22c55e
    expect(badge).toHaveStyle({ color: '#22c55e' })
  })
})
