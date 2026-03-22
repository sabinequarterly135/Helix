import { useTranslation } from 'react-i18next'
import { useMemo } from 'react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
} from 'recharts'
import type { GenerationData } from '../../types/evolution'
import { COLORS } from '../../types/evolution'

interface FitnessChartProps {
  data: GenerationData[]
}

export default function FitnessChart({ data, isLive = false }: FitnessChartProps & { isLive?: boolean }) {
  const { t } = useTranslation()
  // Filter out data points with NaN, undefined, or Infinity values
  const cleanData = useMemo(() =>
    data.filter(d =>
      Number.isFinite(d.bestFitness) &&
      Number.isFinite(d.avgFitness)
    ), [data])

  // Compute left Y-axis domain from actual fitness data, always including 0
  const [fitnessMin, fitnessMax] = useMemo(() => {
    if (cleanData.length === 0) return [0, 0]
    const min = Math.min(...cleanData.map(d => Math.min(d.bestFitness, d.avgFitness)))
    const max = Math.max(...cleanData.map(d => Math.max(d.bestFitness, d.avgFitness)))
    return [Math.min(min, 0), Math.max(max, 0)]
  }, [cleanData])

  // Compute right Y-axis domain for normalized scores from actual data
  const normalizedValues = useMemo(() =>
    cleanData.map(d => d.bestNormalized).filter(Number.isFinite),
    [cleanData])

  const showNormalized = normalizedValues.length > 0
  const [normalizedMin, normalizedMax] = useMemo(() => {
    if (normalizedValues.length === 0) return [-1, 0]
    return [
      Math.min(...normalizedValues, -1),
      Math.max(...normalizedValues, 0),
    ]
  }, [normalizedValues])

  // Add small padding to fitness domain to prevent lines sitting on axis edges
  const fitnessPadding = (fitnessMax - fitnessMin) * 0.05 || 0.1
  const fitnessDomain: [number, number] = [fitnessMin - fitnessPadding, fitnessMax + fitnessPadding]

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-4">
      <h3 className="text-slate-200 font-semibold mb-4">{t('evolution.fitnessProgression')}</h3>
      {cleanData.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-[400px] gap-3">
          {isLive ? (
            <>
              <div className="flex items-center gap-2">
                <span className="relative flex h-3 w-3">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-3 w-3 bg-blue-500"></span>
                </span>
                <p className="text-slate-400">{t('evolution.evaluatingFirstGeneration')}</p>
              </div>
              <p className="text-slate-600 text-xs">{t('evolution.evaluatingFirstGenerationHint')}</p>
            </>
          ) : (
            <p className="text-slate-500">{t('evolution.noDataYet')}</p>
          )}
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={400}>
          <LineChart data={cleanData}>
            <CartesianGrid strokeDasharray="3 3" stroke={COLORS.border} />
            <XAxis dataKey="label" stroke={COLORS.textSecondary} />
            <YAxis yAxisId="left" domain={fitnessDomain} stroke={COLORS.textSecondary} tickFormatter={(v: number) => v.toFixed(1)} />
            <YAxis yAxisId="normalized" orientation="right" domain={[normalizedMin, normalizedMax]} stroke={COLORS.purple} tickFormatter={(v: number) => v.toFixed(1)} />
            <ReferenceLine
              yAxisId="left"
              y={0}
              stroke="#22c55e"
              strokeDasharray="6 3"
              strokeWidth={1.5}
              label={{
                value: 'Perfect (0)',
                position: 'right',
                fill: '#22c55e',
                fontSize: 11,
              }}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: COLORS.cardBg,
                border: `1px solid ${COLORS.border}`,
                color: COLORS.textPrimary,
                borderRadius: '0.5rem',
              }}
              labelStyle={{ color: COLORS.textPrimary }}
              formatter={(value) => typeof value === 'number' ? value.toFixed(2) : String(value ?? '')}
            />
            <Legend />
            <Line
              yAxisId="left"
              type="monotone"
              dataKey="bestFitness"
              stroke={COLORS.green}
              strokeWidth={3}
              dot={{ fill: COLORS.green }}
              name={t('evolution.bestFitness')}
              isAnimationActive={false}
              connectNulls={true}
            />
            <Line
              yAxisId="left"
              type="monotone"
              dataKey="avgFitness"
              stroke={COLORS.blue}
              strokeWidth={3}
              dot={{ fill: COLORS.blue }}
              name={t('evolution.avgFitness')}
              isAnimationActive={false}
              connectNulls={true}
            />
            {showNormalized && (
              <Line
                yAxisId="normalized"
                type="monotone"
                dataKey="bestNormalized"
                stroke={COLORS.purple}
                strokeWidth={2}
                strokeDasharray="5 3"
                dot={{ fill: COLORS.purple }}
                name={t('evolution.bestNorm')}
                isAnimationActive={false}
                connectNulls={true}
              />
            )}
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}
