import { useTranslation } from 'react-i18next'
import { useMemo } from 'react'
import type { LineageNode, MutationStat } from '../../types/evolution'
import { MUTATION_COLORS } from '../../types/evolution'

interface MutationStatsProps {
  lineageEvents: LineageNode[]
}

/**
 * Port of Python lineage/renderer.py:compute_mutation_stats.
 * Computes per-mutation-type effectiveness from lineage events.
 */
export function computeMutationStats(
  events: LineageNode[],
): Map<string, MutationStat> {
  const index = new Map(events.map((e) => [e.candidateId, e]))
  const stats = new Map<
    string,
    { count: number; improved: number; totalDelta: number }
  >()

  for (const event of events) {
    if (event.mutationType === 'seed') continue

    const mtype = event.mutationType
    if (!stats.has(mtype))
      stats.set(mtype, { count: 0, improved: 0, totalDelta: 0 })
    const s = stats.get(mtype)!
    s.count++

    const parentFitnesses = event.parentIds
      .filter((pid) => index.has(pid))
      .map((pid) => index.get(pid)!.fitnessScore)
    const delta =
      parentFitnesses.length > 0
        ? event.fitnessScore - Math.max(...parentFitnesses)
        : 0
    s.totalDelta += delta
    if (delta > 0) s.improved++
  }

  const result = new Map<string, MutationStat>()
  for (const [mtype, s] of stats) {
    result.set(mtype, {
      count: s.count,
      improved: s.improved,
      avgDelta: s.count > 0 ? s.totalDelta / s.count : 0,
    })
  }
  return result
}

export default function MutationStats({ lineageEvents }: MutationStatsProps) {
  const { t } = useTranslation()
  const stats = useMemo(
    () => computeMutationStats(lineageEvents),
    [lineageEvents],
  )

  const entries = useMemo(() => Array.from(stats.entries()), [stats])
  const totalCount = useMemo(
    () => entries.reduce((sum, [, s]) => sum + s.count, 0),
    [entries],
  )

  if (entries.length === 0) {
    return (
      <div className="rounded-lg border border-slate-700 bg-slate-800/50 p-8 text-center text-slate-400">
        {t('evolution.noMutationData')}
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Distribution bar */}
      <div className="rounded-lg border border-slate-700 bg-slate-800 p-4">
        <p className="mb-2 text-xs font-medium uppercase tracking-wider text-slate-400">
          {t('evolution.mutationDistribution')}
        </p>
        <div className="flex h-4 overflow-hidden rounded-full">
          {entries.map(([mtype, s]) => {
            const pct = totalCount > 0 ? (s.count / totalCount) * 100 : 0
            return (
              <div
                key={mtype}
                title={`${mtype}: ${s.count} (${pct.toFixed(1)}%)`}
                style={{
                  width: `${pct}%`,
                  backgroundColor: MUTATION_COLORS[mtype] ?? '#64748b',
                }}
              />
            )
          })}
        </div>
        <div className="mt-2 flex flex-wrap gap-3 text-xs text-slate-400">
          {entries.map(([mtype, s]) => (
            <span key={mtype} className="flex items-center gap-1">
              <span
                className="inline-block h-2 w-2 rounded-full"
                style={{
                  backgroundColor: MUTATION_COLORS[mtype] ?? '#64748b',
                }}
              />
              {mtype}: {s.count}
            </span>
          ))}
        </div>
      </div>

      {/* Table */}
      <div className="overflow-hidden rounded-lg border border-slate-700 bg-slate-800">
        <table className="w-full">
          <thead>
            <tr className="bg-slate-700/50">
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-slate-400">
                {t('evolution.mutationType')}
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-slate-400">
                Count
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-slate-400">
                Improved
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-slate-400">
                Improvement Rate
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-slate-400">
                Avg Delta
              </th>
            </tr>
          </thead>
          <tbody>
            {entries.map(([mtype, s], idx) => {
              const rate = s.count > 0 ? (s.improved / s.count) * 100 : 0
              const deltaColor =
                s.avgDelta > 0
                  ? '#22c55e'
                  : s.avgDelta < 0
                    ? '#ef4444'
                    : '#94a3b8'

              return (
                <tr
                  key={mtype}
                  className={`${
                    idx % 2 === 0 ? 'bg-slate-800/50' : 'bg-slate-900/30'
                  } hover:bg-slate-700/30`}
                >
                  <td className="px-4 py-3">
                    <span
                      className="inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold"
                      style={{
                        background: `${MUTATION_COLORS[mtype] ?? '#64748b'}22`,
                        color: MUTATION_COLORS[mtype] ?? '#64748b',
                      }}
                    >
                      {mtype}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right text-sm text-slate-300">
                    {s.count}
                  </td>
                  <td className="px-4 py-3 text-right text-sm text-slate-300">
                    {s.improved}
                  </td>
                  <td className="px-4 py-3 text-right text-sm text-slate-300">
                    {rate.toFixed(1)}%
                  </td>
                  <td
                    className="px-4 py-3 text-right text-sm font-mono"
                    style={{ color: deltaColor }}
                  >
                    {s.avgDelta >= 0 ? '+' : ''}
                    {s.avgDelta.toFixed(4)}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
