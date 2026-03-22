import { useTranslation } from 'react-i18next'
interface FitnessLegendProps {
  x: number
  y: number
  /** Unique SVG gradient ID to avoid collisions when multiple legends render in the same page. */
  gradientId?: string
  /** Minimum fitness value for the legend label. Defaults to -10. */
  minValue?: number
}

/**
 * SVG `<g>` element showing a gradient color legend for penalty-based fitness scores.
 * Designed to be placed inside an existing `<svg>` container (not a full SVG itself).
 */
export function FitnessLegend({ x, y, gradientId = 'fitness-gradient', minValue = -10 }: FitnessLegendProps) {
  const { t } = useTranslation()
  return (
    <g transform={`translate(${x}, ${y})`}>
      <defs>
        <linearGradient id={gradientId} x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stopColor="#ef4444" />
          <stop offset="50%" stopColor="#f59e0b" />
          <stop offset="100%" stopColor="#22c55e" />
        </linearGradient>
      </defs>
      {/* Title */}
      <text x={0} y={0} fontSize={10} fill="#94a3b8">
        {t('evolution.fitness')}
      </text>
      {/* Gradient bar */}
      <rect x={0} y={4} width={80} height={8} rx={2} fill={`url(#${gradientId})`} />
      {/* Labels */}
      <text x={0} y={22} fontSize={9} fill="#94a3b8">
        {minValue}
      </text>
      <text x={80} y={22} fontSize={9} fill="#94a3b8" textAnchor="end">
        0
      </text>
    </g>
  )
}
