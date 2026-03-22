import { describe, it, expect, beforeAll } from 'vitest'
import type { LineageNode } from '../types/evolution'
import { traceWinningPath, deduplicateEvents } from '../lib/lineage-utils'

// Importing detectIslandTransitions (will be added in GREEN phase)
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let detectIslandTransitions: any

// Dynamically import to handle when function doesn't exist yet
beforeAll(async () => {
  const mod = await import('../lib/lineage-utils')
  detectIslandTransitions = (mod as Record<string, unknown>).detectIslandTransitions
})

function makeNode(overrides: Partial<LineageNode> & { candidateId: string }): LineageNode {
  return {
    parentIds: [],
    generation: 0,
    island: 0,
    fitnessScore: -2.0,
    normalizedScore: 0,
    rejected: false,
    mutationType: 'rcc',
    survived: true,
    ...overrides,
  }
}

describe('traceWinningPath', () => {
  it('traces a single-island path from best back to seed', () => {
    const events: LineageNode[] = [
      makeNode({ candidateId: 'seed', parentIds: [], generation: 0, fitnessScore: -5.0, mutationType: 'seed' }),
      makeNode({ candidateId: 'rcc1', parentIds: ['seed'], generation: 1, fitnessScore: -3.0, mutationType: 'rcc' }),
      makeNode({ candidateId: 'structural1', parentIds: ['rcc1'], generation: 2, fitnessScore: -1.0, mutationType: 'structural' }),
    ]
    const path = traceWinningPath(events, 'structural1')
    expect(path.size).toBe(3)
    expect(path.has('structural1')).toBe(true)
    expect(path.has('rcc1')).toBe(true)
    expect(path.has('seed')).toBe(true)
  })

  it('traces multi-island path through migration events back to original seed', () => {
    // seed-original (gen 0, island 0) -> seed-clone-0 (gen 0, island 0) and seed-clone-1 (gen 0, island 1)
    // rcc-0 (gen 1, island 0, parent=seed-clone-0), rcc-1 (gen 1, island 1, parent=seed-clone-1)
    // migrated-to-0 (gen 1, island 0, parent=rcc-1, type=migrated)
    // best (gen 2, island 0, parent=migrated-to-0)
    const events: LineageNode[] = [
      makeNode({ candidateId: 'seed-original', parentIds: [], generation: 0, island: 0, fitnessScore: -5.0, mutationType: 'seed' }),
      makeNode({ candidateId: 'seed-clone-0', parentIds: ['seed-original'], generation: 0, island: 0, fitnessScore: -5.0, mutationType: 'seed' }),
      makeNode({ candidateId: 'seed-clone-1', parentIds: ['seed-original'], generation: 0, island: 1, fitnessScore: -5.0, mutationType: 'seed' }),
      makeNode({ candidateId: 'rcc-0', parentIds: ['seed-clone-0'], generation: 1, island: 0, fitnessScore: -3.0, mutationType: 'rcc' }),
      makeNode({ candidateId: 'rcc-1', parentIds: ['seed-clone-1'], generation: 1, island: 1, fitnessScore: -2.0, mutationType: 'rcc' }),
      makeNode({ candidateId: 'migrated-to-0', parentIds: ['rcc-1'], generation: 1, island: 0, fitnessScore: -2.0, mutationType: 'migrated' }),
      makeNode({ candidateId: 'best', parentIds: ['migrated-to-0'], generation: 2, island: 0, fitnessScore: -0.5, mutationType: 'rcc' }),
    ]

    const path = traceWinningPath(events, 'best')
    // Path should follow: best -> migrated-to-0 -> rcc-1 -> seed-clone-1 -> seed-original
    expect(path.has('best')).toBe(true)
    expect(path.has('migrated-to-0')).toBe(true)
    expect(path.has('rcc-1')).toBe(true)
    expect(path.has('seed-clone-1')).toBe(true)
    expect(path.has('seed-original')).toBe(true)
    // Should NOT include the island 0 branch that wasn't on the winning path
    expect(path.has('rcc-0')).toBe(false)
    expect(path.has('seed-clone-0')).toBe(false)
  })

  it('handles old-format data (single seed, no island clones) gracefully', () => {
    // Old format: seed has no per-island clones, candidates point directly to seed
    const events: LineageNode[] = [
      makeNode({ candidateId: 'old-seed', parentIds: [], generation: 0, fitnessScore: -5.0, mutationType: 'seed' }),
      makeNode({ candidateId: 'old-rcc', parentIds: ['old-seed'], generation: 1, fitnessScore: -2.0, mutationType: 'rcc' }),
    ]
    const path = traceWinningPath(events, 'old-rcc')
    expect(path.size).toBe(2)
    expect(path.has('old-rcc')).toBe(true)
    expect(path.has('old-seed')).toBe(true)
  })

  it('returns empty set for null bestId', () => {
    const events: LineageNode[] = [
      makeNode({ candidateId: 'a', fitnessScore: -1.0 }),
    ]
    const path = traceWinningPath(events, null)
    expect(path.size).toBe(0)
  })

  it('returns empty set for empty string bestId', () => {
    const events: LineageNode[] = [
      makeNode({ candidateId: 'a', fitnessScore: -1.0 }),
    ]
    const path = traceWinningPath(events, '')
    expect(path.size).toBe(0)
  })
})

describe('deduplicateEvents', () => {
  it('keeps last event for each candidateId', () => {
    const events: LineageNode[] = [
      makeNode({ candidateId: 'dup', fitnessScore: -5.0 }),
      makeNode({ candidateId: 'dup', fitnessScore: -1.0 }),
      makeNode({ candidateId: 'unique', fitnessScore: -3.0 }),
    ]
    const result = deduplicateEvents(events)
    expect(result.length).toBe(2)
    const dupNode = result.find(e => e.candidateId === 'dup')
    expect(dupNode?.fitnessScore).toBe(-1.0) // last wins
  })
})

describe('detectIslandTransitions', () => {
  it('detects transitions when island changes between consecutive nodes', () => {
    const orderedPath: LineageNode[] = [
      makeNode({ candidateId: 'a', island: 0, generation: 0 }),
      makeNode({ candidateId: 'b', island: 0, generation: 1 }),
      makeNode({ candidateId: 'c', island: 1, generation: 1 }), // transition 0 -> 1
      makeNode({ candidateId: 'd', island: 1, generation: 2 }),
      makeNode({ candidateId: 'e', island: 0, generation: 2 }), // transition 1 -> 0
    ]
    const transitions = detectIslandTransitions(orderedPath)
    expect(transitions).toHaveLength(2)
    expect(transitions[0]).toEqual({ fromIsland: 0, toIsland: 1, atCandidateId: 'c' })
    expect(transitions[1]).toEqual({ fromIsland: 1, toIsland: 0, atCandidateId: 'e' })
  })

  it('returns empty array when all nodes are on the same island', () => {
    const orderedPath: LineageNode[] = [
      makeNode({ candidateId: 'a', island: 0 }),
      makeNode({ candidateId: 'b', island: 0 }),
      makeNode({ candidateId: 'c', island: 0 }),
    ]
    const transitions = detectIslandTransitions(orderedPath)
    expect(transitions).toHaveLength(0)
  })

  it('returns empty array for single node', () => {
    const orderedPath: LineageNode[] = [
      makeNode({ candidateId: 'a', island: 0 }),
    ]
    const transitions = detectIslandTransitions(orderedPath)
    expect(transitions).toHaveLength(0)
  })

  it('returns empty array for empty path', () => {
    const transitions = detectIslandTransitions([])
    expect(transitions).toHaveLength(0)
  })
})
