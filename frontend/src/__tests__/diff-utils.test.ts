import { describe, it, expect } from 'vitest'

// Will import from the module once created
import {
  parsePatchLines,
  computePairDiff,
  computePopoverPosition,
} from '../lib/diff-utils'
import type { PairDiff } from '../lib/diff-utils'
import type { LineageNode } from '../types/evolution'

describe('parsePatchLines', () => {
  it('parses unified diff into typed DiffLine array (add, del, context, hunk)', () => {
    const patch = [
      '--- a/file',
      '+++ b/file',
      '@@ -1,3 +1,3 @@',
      ' context line',
      '-old line',
      '+new line',
      ' more context',
    ].join('\n')

    const lines = parsePatchLines(patch)

    expect(lines).toEqual([
      { type: 'hunk', content: '@@ -1,3 +1,3 @@' },
      { type: 'context', content: 'context line' },
      { type: 'del', content: 'old line' },
      { type: 'add', content: 'new line' },
      { type: 'context', content: 'more context' },
    ])
  })

  it('skips file header lines (---, +++, Index:, ====)', () => {
    const patch = [
      'Index: file.txt',
      '==============================',
      '--- a/file.txt',
      '+++ b/file.txt',
      '@@ -1,2 +1,2 @@',
      ' kept',
      '-removed',
      '+added',
    ].join('\n')

    const lines = parsePatchLines(patch)

    // Should not include any lines starting with ---, +++, Index:, ====
    const types = lines.map((l) => l.type)
    expect(types).not.toContain('file')
    expect(lines.length).toBe(4) // hunk, context, del, add
    expect(lines[0]).toEqual({ type: 'hunk', content: '@@ -1,2 +1,2 @@' })
  })

  it('returns empty array for empty input', () => {
    expect(parsePatchLines('')).toEqual([])
  })
})

describe('computePairDiff', () => {
  const makeNode = (overrides: Partial<LineageNode> = {}): LineageNode => ({
    candidateId: 'test-id',
    parentIds: [],
    generation: 0,
    island: 0,
    fitnessScore: 0.5,
    normalizedScore: -0.5,
    rejected: false,
    mutationType: 'rcc',
    survived: true,
    template: 'hello world',
    ...overrides,
  })

  it('returns correct PairDiff structure with two LineageNode fixtures', () => {
    const parent = makeNode({
      candidateId: 'parent-001',
      fitnessScore: 0.3,
      template: 'Line one\nLine two',
    })
    const child = makeNode({
      candidateId: 'child-002',
      fitnessScore: 0.7,
      mutationType: 'structural',
      template: 'Line one\nLine modified',
    })

    const result: PairDiff = computePairDiff(child, parent)

    expect(result.parentId).toBe('parent-001')
    expect(result.childId).toBe('child-002')
    expect(result.parentFitness).toBe(0.3)
    expect(result.childFitness).toBe(0.7)
    expect(result.mutationType).toBe('structural')
    expect(result.lines.length).toBeGreaterThan(0)
    // Should contain at least one del and one add line for the changed line
    const types = result.lines.map((l) => l.type)
    expect(types).toContain('del')
    expect(types).toContain('add')
  })

  it('handles undefined templates gracefully (falls back to empty string)', () => {
    const parent = makeNode({ candidateId: 'p', template: undefined })
    const child = makeNode({ candidateId: 'c', template: 'new content' })

    const result = computePairDiff(child, parent)

    expect(result.parentId).toBe('p')
    expect(result.childId).toBe('c')
    // Should have add lines for the new content (parent was empty)
    const addLines = result.lines.filter((l) => l.type === 'add')
    expect(addLines.length).toBeGreaterThan(0)
  })

  it('returns empty lines when both templates are identical', () => {
    const parent = makeNode({ candidateId: 'p', template: 'same' })
    const child = makeNode({ candidateId: 'c', template: 'same' })

    const result = computePairDiff(child, parent)

    // No diff lines for identical content (only context)
    const addDel = result.lines.filter((l) => l.type === 'add' || l.type === 'del')
    expect(addDel.length).toBe(0)
  })
})

describe('computePopoverPosition', () => {
  // POPOVER_WIDTH = 400, POPOVER_HEIGHT = 300, OFFSET = 12

  it('positions above and centered horizontally by default', () => {
    const pos = computePopoverPosition(300, 350, 800, 600)

    // Centered: left = dotX - POPOVER_WIDTH/2 = 300 - 200 = 100
    expect(pos.left).toBe(100)
    // Above: top = dotY - POPOVER_HEIGHT - OFFSET = 350 - 300 - 12 = 38
    expect(pos.top).toBe(38)
  })

  it('flips below when dotY is too close to top edge', () => {
    const pos = computePopoverPosition(300, 50, 800, 600)

    // Above would be: 50 - 300 - 12 = -262 (< 0), so flip below
    // Below: top = dotY + OFFSET = 50 + 12 = 62
    expect(pos.top).toBe(62)
  })

  it('clamps horizontal position to stay within container bounds (left edge)', () => {
    const pos = computePopoverPosition(10, 350, 800, 600)

    // Centered: left = 10 - 200 = -190, clamp to min 4
    expect(pos.left).toBe(4)
  })

  it('clamps horizontal position to stay within container bounds (right edge)', () => {
    const pos = computePopoverPosition(790, 350, 800, 600)

    // Centered: left = 790 - 200 = 590, max = 800 - 400 - 4 = 396
    expect(pos.left).toBe(396)
  })
})
