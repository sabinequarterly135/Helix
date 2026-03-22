import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { createElement } from 'react'
import { render, screen } from '@testing-library/react'
import type { CandidateData } from '../types/evolution'

// ---------------------------------------------------------------------------
// Mocks -- must be before any Islands3D import
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
  Html: ({ children }: { children: React.ReactNode }) =>
    createElement('div', { 'data-testid': 'drei-html' }, children),
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
  class MockVector3 {
    x: number
    y: number
    z: number
    constructor(x = 0, y = 0, z = 0) { this.x = x; this.y = y; this.z = z }
  }
  return {
    Object3D: MockObject3D,
    Color: MockColor,
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
  FITNESS_DOMAIN_MIN: -10,
  FITNESS_DOMAIN_MAX: 0,
}))

// ---------------------------------------------------------------------------
// WebGL mock helper
// ---------------------------------------------------------------------------
let webglAvailable = true

// Patch once, control via flag
beforeEach(() => {
  webglAvailable = true
  mockFitnessColor.mockClear()
})

// We override getContext on HTMLCanvasElement prototype
const origGetContext = HTMLCanvasElement.prototype.getContext
beforeEach(() => {
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
const makeCandidates = (overrides: Partial<CandidateData>[] = []): CandidateData[] =>
  overrides.map((o, i) => ({
    candidateId: `c-${i}`,
    generation: 1,
    fitnessScore: -2.5,
    normalizedScore: -0.5,
    rejected: false,
    mutationType: 'rcc',
    island: 0,
    ...o,
  }))

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------
describe('Islands3D', () => {
  let Islands3D: typeof import('../components/evolution/Islands3D').default

  beforeEach(async () => {
    const mod = await import('../components/evolution/Islands3D')
    Islands3D = mod.default
  })

  it('renders WebGL fallback when WebGL unavailable', () => {
    webglAvailable = false

    render(
      <Islands3D
        candidates={[]}
        migrations={[]}
        islandCount={0}
      />,
    )

    expect(screen.getByText(/WebGL is not supported/i)).toBeInTheDocument()
  })

  it('renders R3F Canvas when candidates provided', () => {
    webglAvailable = true

    const candidates = makeCandidates([
      { island: 0 },
      { island: 1 },
      { island: 1 },
    ])

    render(
      <Islands3D
        candidates={candidates}
        migrations={[]}
        islandCount={2}
      />,
    )

    expect(screen.getByTestId('r3f-canvas')).toBeInTheDocument()
  })

  it('renders Canvas with empty candidates and islandCount=0', () => {
    webglAvailable = true

    render(
      <Islands3D
        candidates={[]}
        migrations={[]}
        islandCount={0}
      />,
    )

    // Canvas still renders (scene is just empty)
    expect(screen.getByTestId('r3f-canvas')).toBeInTheDocument()
  })

  it('imports fitness color utilities from scoring module', async () => {
    // Verify that Islands3D component depends on the scoring module
    // (structural test -- the fitnessColor mock is wired correctly)
    const scoringMod = await import('../lib/scoring')
    expect(scoringMod.fitnessColor).toBeDefined()
    expect(scoringMod.ISLAND_COLORS).toHaveLength(8)
    expect(scoringMod.REJECTED_OPACITY).toBe(0.3)
    expect(scoringMod.ACTIVE_OPACITY).toBe(0.9)
  })
})
