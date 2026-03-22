import { createTwoFilesPatch } from 'diff'
import type { LineageNode } from '../types/evolution'

export interface DiffLine {
  type: 'add' | 'del' | 'context' | 'hunk' | 'file'
  content: string
}

export interface PairDiff {
  parentId: string
  childId: string
  parentFitness: number
  childFitness: number
  mutationType: string
  lines: DiffLine[]
}

/**
 * Parse a unified diff patch string into typed DiffLine entries.
 * Skips file header lines (---, +++, Index:, ====).
 */
export function parsePatchLines(patch: string): DiffLine[] {
  const rawLines = patch.split('\n')
  const lines: DiffLine[] = []

  for (const line of rawLines) {
    // Skip file header lines (--- and +++)
    if (line.startsWith('---') || line.startsWith('+++')) continue
    // Skip the diff header line
    if (line.startsWith('Index:') || line.startsWith('====')) continue

    if (line.startsWith('@@')) {
      lines.push({ type: 'hunk', content: line })
    } else if (line.startsWith('+')) {
      lines.push({ type: 'add', content: line.slice(1) })
    } else if (line.startsWith('-')) {
      lines.push({ type: 'del', content: line.slice(1) })
    } else if (line.startsWith(' ')) {
      lines.push({ type: 'context', content: line.slice(1) })
    }
    // Skip empty lines that are just artifacts
  }

  return lines
}

/**
 * Compute a unified diff between a child and parent LineageNode.
 * Returns a PairDiff with parsed diff lines and metadata.
 */
export function computePairDiff(
  child: LineageNode,
  parent: LineageNode,
): PairDiff {
  const patch = createTwoFilesPatch(
    `${parent.candidateId.slice(0, 8)} (fit=${parent.fitnessScore.toFixed(3)})`,
    `${child.candidateId.slice(0, 8)} (fit=${child.fitnessScore.toFixed(3)})`,
    parent.template ?? '',
    child.template ?? '',
    '',
    '',
    { context: 3 },
  )

  return {
    parentId: parent.candidateId,
    childId: child.candidateId,
    parentFitness: parent.fitnessScore,
    childFitness: child.fitnessScore,
    mutationType: child.mutationType,
    lines: parsePatchLines(patch),
  }
}

const POPOVER_WIDTH = 400
const POPOVER_HEIGHT = 300
const OFFSET = 12

/**
 * Compute popover position relative to a container.
 * Positions above the dot by default, flips below when near the top edge.
 * Clamps horizontal position to stay within container bounds.
 */
export function computePopoverPosition(
  dotX: number,
  dotY: number,
  containerWidth: number,
  _containerHeight: number,
): { left: number; top: number } {
  // Default: center horizontally above the dot
  let left = dotX - POPOVER_WIDTH / 2
  let top = dotY - POPOVER_HEIGHT - OFFSET

  // Flip below if top goes above the container
  if (top < 0) {
    top = dotY + OFFSET
  }

  // Clamp horizontal position
  const minLeft = 4
  const maxLeft = containerWidth - POPOVER_WIDTH - 4
  left = Math.max(minLeft, Math.min(maxLeft, left))

  return { left, top }
}
