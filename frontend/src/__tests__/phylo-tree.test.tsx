import React from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { LineageNode } from '../types/evolution'

// Mock d3-force (same pattern as islands-view.test.tsx)
vi.mock('d3-force', () => ({
  forceSimulation: () => ({
    force: vi.fn().mockReturnThis(),
    nodes: vi.fn().mockReturnThis(),
    alpha: vi.fn().mockReturnThis(),
    restart: vi.fn().mockReturnThis(),
    stop: vi.fn().mockReturnThis(),
    on: vi.fn().mockReturnThis(),
    alphaTarget: vi.fn().mockReturnThis(),
  }),
  forceX: () => ({ strength: vi.fn().mockReturnThis() }),
  forceY: () => ({ strength: vi.fn().mockReturnThis() }),
  forceCollide: () => vi.fn(),
}))

// Mock scoring utilities
vi.mock('../lib/scoring', () => ({
  fitnessColor: () => '#22c55e',
  REJECTED_OPACITY: 0.3,
  ACTIVE_OPACITY: 0.9,
  ISLAND_COLORS: ['#3b82f6', '#8b5cf6', '#14b8a6', '#f97316', '#ec4899', '#06b6d4', '#84cc16', '#a855f7'],
}))

// Mock FitnessLegend
vi.mock('../components/evolution/FitnessLegend', () => ({
  FitnessLegend: ({ x, y }: { x: number; y: number }) => {
    return React.createElement('g', { 'data-testid': 'fitness-legend', transform: `translate(${x}, ${y})` })
  },
}))

// Mock d3-zoom
vi.mock('d3-zoom', () => ({
  zoom: () => {
    const z: Record<string, unknown> = {}
    z.scaleExtent = vi.fn().mockReturnValue(z)
    z.on = vi.fn().mockReturnValue(z)
    z.scaleBy = vi.fn()
    z.transform = vi.fn()
    return z
  },
}))

// Mock d3-selection
vi.mock('d3-selection', () => ({
  select: () => {
    const s: Record<string, unknown> = {}
    s.call = vi.fn().mockReturnValue(s)
    s.on = vi.fn().mockReturnValue(s)
    s.transition = vi.fn().mockReturnValue(s)
    return s
  },
}))

// Lazy import to ensure mocks are in place
const { default: PhyloTree } = await import('../components/evolution/PhyloTree')

function makeLineageEvents(overrides: Partial<LineageNode>[] = []): LineageNode[] {
  return overrides.map((o, i) => ({
    candidateId: `cand-${i}`,
    parentIds: i > 0 ? [`cand-${i - 1}`] : [],
    generation: Math.floor(i / 2),
    island: 0,
    fitnessScore: 0.3 + i * 0.1,
    normalizedScore: 0,
    rejected: false,
    mutationType: 'rcc',
    survived: true,
    ...o,
  }))
}

describe('PhyloTree', () => {
  it('renders SVG element when lineageEvents are provided', () => {
    const events = makeLineageEvents([{ candidateId: 'a' }, { candidateId: 'b' }])
    const { container } = render(
      <PhyloTree lineageEvents={events} bestCandidateId="b" />,
    )
    const svg = container.querySelector('svg')
    expect(svg).toBeInTheDocument()
  })

  it('renders one circle per unique candidate (deduplicated by candidateId)', () => {
    // Two events with same candidateId should produce one node
    const events = makeLineageEvents([
      { candidateId: 'dup-1', generation: 0, fitnessScore: 0.3 },
      { candidateId: 'dup-1', generation: 0, fitnessScore: 0.5 },
      { candidateId: 'unique-2', generation: 1, fitnessScore: 0.7 },
    ])
    const { container } = render(
      <PhyloTree lineageEvents={events} bestCandidateId="unique-2" />,
    )
    const circles = container.querySelectorAll('circle[data-candidate]')
    // Should be 2 (dup-1 deduplicated, plus unique-2)
    expect(circles.length).toBe(2)
  })

  it('winning path nodes have a stroke highlight (data-winning="true")', () => {
    // Chain: a -> b -> c (best). All 3 should be on winning path.
    const events: LineageNode[] = [
      {
        candidateId: 'a',
        parentIds: [],
        generation: 0,
        island: 0,
        fitnessScore: 0.2,
        normalizedScore: 0,
        rejected: false,
        mutationType: 'seed',
        survived: true,
      },
      {
        candidateId: 'b',
        parentIds: ['a'],
        generation: 1,
        island: 0,
        fitnessScore: 0.5,
        normalizedScore: 0,
        rejected: false,
        mutationType: 'rcc',
        survived: true,
      },
      {
        candidateId: 'c',
        parentIds: ['b'],
        generation: 2,
        island: 0,
        fitnessScore: 0.9,
        normalizedScore: 0,
        rejected: false,
        mutationType: 'structural',
        survived: true,
      },
    ]
    const { container } = render(
      <PhyloTree lineageEvents={events} bestCandidateId="c" />,
    )
    const winningCircles = container.querySelectorAll('circle[data-winning="true"]')
    expect(winningCircles.length).toBe(3) // a, b, c all on winning path
  })

  it('shows "No lineage data" message when events array is empty', () => {
    render(<PhyloTree lineageEvents={[]} bestCandidateId={null} />)
    expect(screen.getByText('No lineage data')).toBeInTheDocument()
  })

  it('renders zoom control buttons (+, -, reset)', () => {
    const events = makeLineageEvents([{ candidateId: 'x' }])
    render(<PhyloTree lineageEvents={events} bestCandidateId="x" />)
    expect(screen.getByLabelText('Zoom in')).toBeInTheDocument()
    expect(screen.getByLabelText('Zoom out')).toBeInTheDocument()
    expect(screen.getByLabelText('Reset zoom')).toBeInTheDocument()
  })

  it('renders a mutation type legend', () => {
    const events = makeLineageEvents([{ candidateId: 'x', mutationType: 'rcc' }])
    render(<PhyloTree lineageEvents={events} bestCandidateId="x" />)
    // Legend should contain mutation type labels
    expect(screen.getByText('rcc')).toBeInTheDocument()
    expect(screen.getByText('structural')).toBeInTheDocument()
    expect(screen.getByText('fresh')).toBeInTheDocument()
    expect(screen.getByText('seed')).toBeInTheDocument()
  })

  it('renders island border rings (outer circle) for multi-island events', () => {
    // Two nodes on different islands, rendered in fallback mode (no simulation)
    const events: LineageNode[] = [
      {
        candidateId: 'island0-node',
        parentIds: [],
        generation: 0,
        island: 0,
        fitnessScore: -2.0,
        normalizedScore: 0,
        rejected: false,
        mutationType: 'seed',
        survived: true,
      },
      {
        candidateId: 'island1-node',
        parentIds: ['island0-node'],
        generation: 1,
        island: 1,
        fitnessScore: -1.0,
        normalizedScore: 0,
        rejected: false,
        mutationType: 'rcc',
        survived: true,
      },
    ]
    const { container } = render(
      <PhyloTree lineageEvents={events} bestCandidateId="island1-node" />,
    )
    // Each node renders TWO circles (island ring + fitness fill)
    // data-candidate circles are the inner fill circles
    const dataCandidateCircles = container.querySelectorAll('circle[data-candidate]')
    expect(dataCandidateCircles.length).toBe(2)

    // Total circles should be 4 (2 outer rings + 2 inner fills)
    // The transform group contains all node circles
    const allCircles = container.querySelectorAll('g > g > circle')
    expect(allCircles.length).toBe(4)
  })

  it('winning path nodes still have data-winning="true" with island borders', () => {
    const events: LineageNode[] = [
      {
        candidateId: 'seed',
        parentIds: [],
        generation: 0,
        island: 0,
        fitnessScore: -5.0,
        normalizedScore: 0,
        rejected: false,
        mutationType: 'seed',
        survived: true,
      },
      {
        candidateId: 'best',
        parentIds: ['seed'],
        generation: 1,
        island: 0,
        fitnessScore: -0.5,
        normalizedScore: 0,
        rejected: false,
        mutationType: 'rcc',
        survived: true,
      },
    ]
    const { container } = render(
      <PhyloTree lineageEvents={events} bestCandidateId="best" />,
    )
    const winningCircles = container.querySelectorAll('circle[data-winning="true"]')
    expect(winningCircles.length).toBe(2) // both seed and best on winning path
  })
})
