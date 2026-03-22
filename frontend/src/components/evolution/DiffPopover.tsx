import { useTranslation } from 'react-i18next'
import { useMemo } from 'react'
import type { LineageNode } from '../../types/evolution'
import { MUTATION_COLORS, COLORS } from '../../types/evolution'
import { computePairDiff, computePopoverPosition } from '../../lib/diff-utils'
import type { DiffLine } from '../../lib/diff-utils'

interface DiffPopoverProps {
  candidateId: string
  x: number
  y: number
  containerWidth: number
  containerHeight: number
  lineageIndex: Map<string, LineageNode>
}

function DiffLineRow({ line }: { line: DiffLine }) {
  if (line.type === 'hunk') {
    return <div className="text-blue-400 mt-1 mb-0.5">{line.content}</div>
  }
  if (line.type === 'add') {
    return (
      <div className="text-emerald-400 bg-emerald-500/5">+{line.content}</div>
    )
  }
  if (line.type === 'del') {
    return (
      <div className="text-red-400 bg-red-500/5 line-through opacity-70">
        -{line.content}
      </div>
    )
  }
  return <div className="text-slate-500"> {line.content}</div>
}

export function DiffPopover({
  candidateId,
  x,
  y,
  containerWidth,
  containerHeight,
  lineageIndex,
}: DiffPopoverProps) {
  const { t } = useTranslation()
  const candidate = lineageIndex.get(candidateId)
  const { left, top } = computePopoverPosition(x, y, containerWidth, containerHeight)

  // Compute diff (memoized on candidateId since templates are immutable)
  const diffResult = useMemo(() => {
    if (!candidate || candidate.template === undefined) return null
    if (candidate.mutationType === 'seed') return { type: 'seed' as const }

    const parentId = candidate.parentIds[0]
    if (!parentId) return { type: 'no-parent' as const }

    const parent = lineageIndex.get(parentId)
    if (!parent || parent.template === undefined) return { type: 'no-parent-template' as const }

    const pairDiff = computePairDiff(candidate, parent)
    return { type: 'diff' as const, pairDiff }
  }, [candidateId, candidate, lineageIndex])

  // No template data
  if (!candidate || candidate.template === undefined) {
    return (
      <div
        className="absolute pointer-events-none w-[400px] h-[300px] bg-slate-900 border border-slate-600 rounded-lg shadow-xl z-30 flex items-center justify-center"
        style={{ left: `${left}px`, top: `${top}px` }}
      >
        <p className="text-slate-400 text-sm">{t('evolution.noTemplateData')}</p>
      </div>
    )
  }

  // Seed node: show full template preview
  if (diffResult?.type === 'seed') {
    return (
      <div
        className="absolute pointer-events-none w-[400px] h-[300px] bg-slate-900 border border-slate-600 rounded-lg shadow-xl z-30 flex flex-col overflow-hidden"
        style={{ left: `${left}px`, top: `${top}px` }}
      >
        <div className="flex items-center gap-2 px-3 py-2 bg-slate-700/50 border-b border-slate-600 shrink-0">
          <span className="font-mono text-slate-200 text-xs font-bold">
            {candidate.candidateId}
          </span>
          <span
            className="text-[10px] px-1.5 py-0.5 rounded-full"
            style={{
              backgroundColor:
                (MUTATION_COLORS[candidate.mutationType] ?? COLORS.textMuted) + '22',
              color: MUTATION_COLORS[candidate.mutationType] ?? COLORS.textMuted,
            }}
          >
            {candidate.mutationType}
          </span>
          <span className="text-emerald-400 font-bold text-xs ml-auto">
            {candidate.fitnessScore.toFixed(3)}
          </span>
        </div>
        <div className="overflow-y-auto max-h-[260px] px-3 py-2">
          <pre className="font-mono text-xs leading-relaxed text-slate-300 whitespace-pre-wrap">
            {candidate.template}
          </pre>
        </div>
      </div>
    )
  }

  // Parent template not available
  if (diffResult?.type === 'no-parent' || diffResult?.type === 'no-parent-template') {
    return (
      <div
        className="absolute pointer-events-none w-[400px] h-[300px] bg-slate-900 border border-slate-600 rounded-lg shadow-xl z-30 flex items-center justify-center"
        style={{ left: `${left}px`, top: `${top}px` }}
      >
        <p className="text-slate-400 text-sm">{t('evolution.parentTemplateNotAvailable')}</p>
      </div>
    )
  }

  // Diff view
  if (diffResult?.type === 'diff') {
    const { pairDiff } = diffResult
    const addCount = pairDiff.lines.filter((l) => l.type === 'add').length
    const delCount = pairDiff.lines.filter((l) => l.type === 'del').length

    return (
      <div
        className="absolute pointer-events-none w-[400px] h-[300px] bg-slate-900 border border-slate-600 rounded-lg shadow-xl z-30 flex flex-col overflow-hidden"
        style={{ left: `${left}px`, top: `${top}px` }}
      >
        {/* Header */}
        <div className="flex items-center gap-2 px-3 py-2 bg-slate-700/50 border-b border-slate-600 shrink-0">
          <span className="font-mono text-slate-200 text-xs font-bold">
            {candidate.candidateId.slice(0, 8)}
          </span>
          <span
            className="text-[10px] px-1.5 py-0.5 rounded-full"
            style={{
              backgroundColor:
                (MUTATION_COLORS[candidate.mutationType] ?? COLORS.textMuted) + '22',
              color: MUTATION_COLORS[candidate.mutationType] ?? COLORS.textMuted,
            }}
          >
            {candidate.mutationType}
          </span>
          <span className="text-emerald-400 font-bold text-xs">
            {candidate.fitnessScore.toFixed(3)}
          </span>
          {(addCount > 0 || delCount > 0) && (
            <span className="text-xs text-slate-400 ml-auto font-mono">
              +{addCount} -{delCount}
            </span>
          )}
        </div>

        {/* Diff body */}
        <div className="overflow-y-auto font-mono text-[11px] leading-relaxed px-3 py-2">
          {pairDiff.lines.map((line, i) => (
            <DiffLineRow key={i} line={line} />
          ))}
        </div>
      </div>
    )
  }

  return null
}
