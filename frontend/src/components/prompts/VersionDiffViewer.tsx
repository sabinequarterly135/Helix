import { useMemo } from 'react'
import { createTwoFilesPatch } from 'diff'
import { parsePatchLines } from '@/lib/diff-utils'

interface VersionDiffViewerProps {
  fromTemplate: string
  toTemplate: string
  fromLabel: string
  toLabel: string
}

export default function VersionDiffViewer({
  fromTemplate,
  toTemplate,
  fromLabel,
  toLabel,
}: VersionDiffViewerProps) {
  const diffLines = useMemo(() => {
    if (fromTemplate === toTemplate) return null

    const patch = createTwoFilesPatch(
      fromLabel,
      toLabel,
      fromTemplate,
      toTemplate,
      '',
      '',
      { context: 3 },
    )
    return parsePatchLines(patch)
  }, [fromTemplate, toTemplate, fromLabel, toLabel])

  return (
    <div className="rounded-lg border border-slate-700 bg-slate-800/50 overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-3 bg-slate-700/50">
        <span className="font-semibold text-foreground text-sm">
          {fromLabel} &rarr; {toLabel}
        </span>
      </div>

      {/* Diff content */}
      <div className="px-4 py-3">
        {diffLines === null ? (
          <p className="text-sm text-muted-foreground text-center py-4">
            No differences between these versions.
          </p>
        ) : (
          <div className="font-mono text-xs leading-relaxed overflow-x-auto whitespace-pre-wrap">
            {diffLines.map((line, i) => {
              if (line.type === 'hunk') {
                return (
                  <div
                    key={i}
                    data-diff-type="hunk"
                    className="text-blue-400 mt-2 mb-1"
                  >
                    {line.content}
                  </div>
                )
              }
              if (line.type === 'add') {
                return (
                  <div
                    key={i}
                    data-diff-type="add"
                    className="text-emerald-400 bg-emerald-500/5"
                  >
                    +{line.content}
                  </div>
                )
              }
              if (line.type === 'del') {
                return (
                  <div
                    key={i}
                    data-diff-type="del"
                    className="text-red-400 bg-red-500/5"
                  >
                    -{line.content}
                  </div>
                )
              }
              return (
                <div key={i} data-diff-type="context" className="text-slate-500">
                  {' '}
                  {line.content}
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
