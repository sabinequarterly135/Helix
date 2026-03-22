import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { LineageNode } from '../types/evolution'

// Mock the diff library
vi.mock('diff', () => ({
  createTwoFilesPatch: vi.fn(
    (_oldName: string, _newName: string, oldStr: string, newStr: string) => {
      // Simple mock: return a patch string based on actual diff
      if (oldStr === newStr) return ''
      return `--- a\n+++ b\n@@ -1,1 +1,1 @@\n-${oldStr.split('\n')[0] || ''}\n+${newStr.split('\n')[0] || ''}\n`
    },
  ),
}))

const { DiffPopover } = await import('../components/evolution/DiffPopover')

function makeLineageIndex(nodes: LineageNode[]): Map<string, LineageNode> {
  const map = new Map<string, LineageNode>()
  for (const n of nodes) map.set(n.candidateId, n)
  return map
}

const seedNode: LineageNode = {
  candidateId: 'seed-001',
  parentIds: [],
  generation: 0,
  island: 0,
  fitnessScore: 0.2,
  normalizedScore: -0.8,
  rejected: false,
  mutationType: 'seed',
  survived: true,
  template: 'You are a helpful assistant.\nBe concise.',
}

const childNode: LineageNode = {
  candidateId: 'child-001',
  parentIds: ['seed-001'],
  generation: 1,
  island: 0,
  fitnessScore: 0.6,
  normalizedScore: -0.4,
  rejected: false,
  mutationType: 'rcc',
  survived: true,
  template: 'You are an expert assistant.\nBe concise.',
}

const noTemplateNode: LineageNode = {
  candidateId: 'no-template',
  parentIds: ['seed-001'],
  generation: 1,
  island: 0,
  fitnessScore: 0.3,
  normalizedScore: -0.6,
  rejected: false,
  mutationType: 'rcc',
  survived: true,
  // template undefined
}

const parentNoTemplateChild: LineageNode = {
  candidateId: 'orphan-child',
  parentIds: ['missing-parent'],
  generation: 1,
  island: 0,
  fitnessScore: 0.4,
  normalizedScore: -0.5,
  rejected: false,
  mutationType: 'rcc',
  survived: true,
  template: 'I have a template but parent does not',
}

describe('DiffPopover', () => {
  it('renders diff lines when candidate has parent with template', () => {
    const lineageIndex = makeLineageIndex([seedNode, childNode])

    render(
      <DiffPopover
        candidateId="child-001"
        x={200}
        y={200}
        containerWidth={800}
        containerHeight={600}
        lineageIndex={lineageIndex}
      />,
    )

    // Should show the candidate ID (first 8 chars)
    expect(screen.getByText('child-00')).toBeInTheDocument()
    // Should show mutation type badge
    expect(screen.getByText('rcc')).toBeInTheDocument()
  })

  it('renders full template preview for seed node', () => {
    const lineageIndex = makeLineageIndex([seedNode])

    render(
      <DiffPopover
        candidateId="seed-001"
        x={200}
        y={200}
        containerWidth={800}
        containerHeight={600}
        lineageIndex={lineageIndex}
      />,
    )

    // Seed nodes show template preview, not diff
    expect(screen.getByText(/You are a helpful assistant/)).toBeInTheDocument()
    expect(screen.getByText('seed-001')).toBeInTheDocument()
  })

  it('renders "No template data" when candidate has no template', () => {
    const lineageIndex = makeLineageIndex([seedNode, noTemplateNode])

    render(
      <DiffPopover
        candidateId="no-template"
        x={200}
        y={200}
        containerWidth={800}
        containerHeight={600}
        lineageIndex={lineageIndex}
      />,
    )

    expect(screen.getByText('No template data')).toBeInTheDocument()
  })

  it('renders "Parent template not available" when parent has no template', () => {
    const lineageIndex = makeLineageIndex([parentNoTemplateChild])

    render(
      <DiffPopover
        candidateId="orphan-child"
        x={200}
        y={200}
        containerWidth={800}
        containerHeight={600}
        lineageIndex={lineageIndex}
      />,
    )

    expect(screen.getByText('Parent template not available')).toBeInTheDocument()
  })

  it('positions correctly based on computePopoverPosition', () => {
    const lineageIndex = makeLineageIndex([seedNode, childNode])

    const { container } = render(
      <DiffPopover
        candidateId="child-001"
        x={300}
        y={350}
        containerWidth={800}
        containerHeight={600}
        lineageIndex={lineageIndex}
      />,
    )

    // The popover div should have position styles
    const popover = container.firstChild as HTMLElement
    expect(popover).toBeTruthy()
    // left = 300 - 200 = 100, top = 350 - 300 - 12 = 38
    expect(popover.style.left).toBe('100px')
    expect(popover.style.top).toBe('38px')
  })
})
