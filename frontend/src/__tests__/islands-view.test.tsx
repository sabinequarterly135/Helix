import { describe, it, expect, vi } from 'vitest'
import { createElement } from 'react'
import { render, screen } from '@testing-library/react'
import IslandsView from '../components/evolution/IslandsView'
import type { CandidateData, MigrationData } from '../types/evolution'

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

vi.mock('../lib/scoring', () => ({
  fitnessColor: () => '#22c55e',
  getDotRadius: () => 5,
  REJECTED_OPACITY: 0.3,
  ACTIVE_OPACITY: 0.9,
}))

vi.mock('../components/evolution/FitnessLegend', () => ({
  FitnessLegend: ({ x, y }: { x: number; y: number }) =>
    createElement('g', { 'data-testid': 'fitness-legend', transform: `translate(${x}, ${y})` }),
}))

const makeCandidates = (overrides: Partial<CandidateData>[] = []): CandidateData[] =>
  overrides.map((o, i) => ({
    candidateId: `c-${i}`,
    generation: 1,
    fitnessScore: 0.5,
    normalizedScore: 0,
    rejected: false,
    mutationType: 'rcc',
    island: 0,
    ...o,
  }))

describe('IslandsView', () => {
  it('renders SVG element when candidates array is provided', () => {
    const candidates = makeCandidates([{ island: 0 }, { island: 1 }])
    const { container } = render(
      <IslandsView candidates={candidates} migrations={[]} islandCount={2} status="running" />,
    )
    const svg = container.querySelector('svg')
    expect(svg).toBeInTheDocument()
  })

  it('renders one island group per unique island number in candidates', () => {
    const candidates = makeCandidates([
      { island: 0 },
      { island: 0 },
      { island: 1 },
      { island: 2 },
    ])
    render(
      <IslandsView candidates={candidates} migrations={[]} islandCount={3} status="running" />,
    )
    expect(screen.getByText('Island 0')).toBeInTheDocument()
    expect(screen.getByText('Island 1')).toBeInTheDocument()
    expect(screen.getByText('Island 2')).toBeInTheDocument()
  })

  it('renders "No island data" message when candidates array is empty', () => {
    render(
      <IslandsView candidates={[]} migrations={[]} islandCount={0} status="running" />,
    )
    expect(screen.getByText('No island data')).toBeInTheDocument()
  })

  it('renders candidate dots inside island regions', () => {
    const candidates = makeCandidates([
      { island: 0, candidateId: 'dot-a', fitnessScore: 0.8 },
      { island: 0, candidateId: 'dot-b', fitnessScore: 0.2 },
      { island: 1, candidateId: 'dot-c', fitnessScore: 0.5 },
    ])
    const { container } = render(
      <IslandsView candidates={candidates} migrations={[]} islandCount={2} status="running" />,
    )
    // Each candidate should be rendered as a circle element with a data-candidate attribute
    const dots = container.querySelectorAll('circle[data-candidate]')
    expect(dots.length).toBe(3)
  })

  it('renders migration indicator when migrations array has entries', () => {
    const candidates = makeCandidates([{ island: 0 }, { island: 1 }])
    const migrations: MigrationData[] = [
      { generation: 1, emigrantsPerIsland: 2, timestamp: new Date().toISOString() },
    ]
    render(
      <IslandsView candidates={candidates} migrations={migrations} islandCount={2} status="running" />,
    )
    expect(screen.getByText(/migration/i)).toBeInTheDocument()
  })
})
