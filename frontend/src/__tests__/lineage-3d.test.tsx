import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { createElement } from 'react'
import { render, screen } from '@testing-library/react'
import type { LineageNode } from '../types/evolution'

// ---------------------------------------------------------------------------
// Mocks -- must be before any Lineage3D import
// ---------------------------------------------------------------------------

// Mock @react-three/fiber
vi.mock('@react-three/fiber', () => ({
  Canvas: ({ children }: { children: React.ReactNode }) =>
    createElement('div', { 'data-testid': 'r3f-canvas' }, children),
  useFrame: vi.fn(),
}))

// Mock @react-three/drei
vi.mock('@react-three/drei', () => ({
  OrbitControls: () => null,
  Line: () => createElement('div', { 'data-testid': 'drei-line' }),
  Html: ({ children }: { children: React.ReactNode }) =>
    createElement('div', { 'data-testid': 'drei-html' }, children),
}))

// Mock @react-three/postprocessing
vi.mock('@react-three/postprocessing', () => ({
  EffectComposer: ({ children }: { children: React.ReactNode }) =>
    createElement('div', { 'data-testid': 'effect-composer' }, children),
  Bloom: () => null,
}))

// Mock d3-force-3d
const mockTick = vi.fn()
const mockStop = vi.fn()
const mockForce = vi.fn().mockReturnThis()
const mockSimulation = vi.fn(() => ({
  force: mockForce,
  tick: mockTick,
  stop: mockStop,
}))

vi.mock('d3-force-3d', () => ({
  forceSimulation: () => mockSimulation(),
  forceX: vi.fn(() => ({ strength: vi.fn().mockReturnThis() })),
  forceY: vi.fn(() => ({ strength: vi.fn().mockReturnThis() })),
  forceZ: vi.fn(() => ({ strength: vi.fn().mockReturnThis() })),
  forceCollide: vi.fn(() => ({})),
  forceManyBody: vi.fn(() => ({ strength: vi.fn().mockReturnThis() })),
}))

// Mock three (minimal)
vi.mock('three', () => {
  class MockObject3D {
    position = { set: vi.fn(), lerpVectors: vi.fn() }
    scale = { setScalar: vi.fn() }
    matrix = {}
    updateMatrix = vi.fn()
  }
  class MockColor {
    set = vi.fn().mockReturnThis()
    multiplyScalar = vi.fn().mockReturnThis()
  }
  class MockMesh {
    scale = { setScalar: vi.fn() }
  }
  class MockVector3 {
    x: number
    y: number
    z: number
    constructor(x = 0, y = 0, z = 0) { this.x = x; this.y = y; this.z = z }
  }
  return {
    Object3D: MockObject3D,
    Color: MockColor,
    Mesh: MockMesh,
    Vector3: MockVector3,
    DoubleSide: 2,
  }
})

// Mock scoring module
const mockFitnessColor = vi.fn().mockReturnValue('#22c55e')
vi.mock('../lib/scoring', () => ({
  fitnessColor: (v: number) => mockFitnessColor(v),
  ISLAND_COLORS: ['#3b82f6', '#8b5cf6', '#14b8a6', '#f97316', '#ec4899', '#06b6d4', '#84cc16', '#a855f7'],
  REJECTED_OPACITY: 0.3,
  ACTIVE_OPACITY: 0.9,
}))

// Mock lineage-utils -- spy on calls
const mockTraceWinningPath = vi.fn().mockReturnValue(new Set(['c-0']))
const mockDeduplicateEvents = vi.fn((events: LineageNode[]) => events)
vi.mock('../lib/lineage-utils', () => ({
  traceWinningPath: (events: LineageNode[], bestId: string | null) => mockTraceWinningPath(events, bestId),
  deduplicateEvents: (events: LineageNode[]) => mockDeduplicateEvents(events),
}))

// ---------------------------------------------------------------------------
// WebGL mock helper
// ---------------------------------------------------------------------------
let webglAvailable = true
const origGetContext = HTMLCanvasElement.prototype.getContext

beforeEach(() => {
  webglAvailable = true
  mockFitnessColor.mockClear()
  mockTraceWinningPath.mockClear()
  mockDeduplicateEvents.mockClear()
  mockSimulation.mockClear()
  mockTick.mockClear()
  mockStop.mockClear()
  mockForce.mockClear()

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  HTMLCanvasElement.prototype.getContext = function (this: HTMLCanvasElement, contextId: string, ...args: any[]) {
    if (contextId === 'webgl2' || contextId === 'webgl') {
      return webglAvailable ? ({} as WebGLRenderingContext) : null
    }
    // eslint-disable-next-line @typescript-eslint/no-unsafe-function-type
    return (origGetContext as Function).call(this, contextId, ...args)
  } as typeof origGetContext
})

afterEach(() => {
  HTMLCanvasElement.prototype.getContext = origGetContext
})

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
const makeLineageEvents = (count: number): LineageNode[] => {
  const events: LineageNode[] = []
  for (let i = 0; i < count; i++) {
    events.push({
      candidateId: `c-${i}`,
      parentIds: i > 0 ? [`c-${i - 1}`] : [],
      generation: Math.floor(i / 2),
      island: i % 2,
      fitnessScore: -5 + i * 0.5,
      normalizedScore: -0.5 + i * 0.1,
      rejected: false,
      mutationType: 'rcc',
      survived: true,
    })
  }
  return events
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------
describe('Lineage3D', () => {
  let Lineage3D: typeof import('../components/evolution/Lineage3D').default

  beforeEach(async () => {
    const mod = await import('../components/evolution/Lineage3D')
    Lineage3D = mod.default
  })

  it('renders WebGL fallback when WebGL unavailable', () => {
    webglAvailable = false

    render(
      <Lineage3D
        lineageEvents={makeLineageEvents(5)}
        bestCandidateId="c-4"
      />,
    )

    expect(screen.getByText(/WebGL is not supported/i)).toBeInTheDocument()
  })

  it('renders empty state when no lineage events', () => {
    webglAvailable = true

    render(
      <Lineage3D
        lineageEvents={[]}
        bestCandidateId={null}
      />,
    )

    expect(screen.getByText(/No lineage data/i)).toBeInTheDocument()
  })

  it('renders R3F Canvas with lineage data', () => {
    webglAvailable = true
    const events = makeLineageEvents(5)

    render(
      <Lineage3D
        lineageEvents={events}
        bestCandidateId="c-4"
      />,
    )

    expect(screen.getByTestId('r3f-canvas')).toBeInTheDocument()
  })

  it('identifies winning path nodes via traceWinningPath', () => {
    webglAvailable = true
    const events = makeLineageEvents(5)

    render(
      <Lineage3D
        lineageEvents={events}
        bestCandidateId="c-4"
      />,
    )

    // traceWinningPath should have been called with the deduped events and bestCandidateId
    expect(mockTraceWinningPath).toHaveBeenCalled()
    const callArgs = mockTraceWinningPath.mock.calls[0]
    expect(callArgs[1]).toBe('c-4')
    // First arg should be the deduped events array
    expect(Array.isArray(callArgs[0])).toBe(true)
  })

  it('deduplicates events before layout computation', () => {
    webglAvailable = true
    const events = makeLineageEvents(5)

    render(
      <Lineage3D
        lineageEvents={events}
        bestCandidateId="c-4"
      />,
    )

    // deduplicateEvents should have been called with the raw lineageEvents
    expect(mockDeduplicateEvents).toHaveBeenCalled()
    const callArgs = mockDeduplicateEvents.mock.calls[0]
    expect(callArgs[0]).toEqual(events)
  })
})
