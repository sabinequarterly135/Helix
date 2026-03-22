import { useTranslation } from 'react-i18next'
import { useEffect, useMemo, useRef, useState } from 'react'
import type { Simulation } from 'd3-force'
import { forceSimulation, forceX, forceY, forceCollide } from 'd3-force'
import type { CandidateData, MigrationData, EvolutionStatus, LineageNode } from '../../types/evolution'
import { COLORS } from '../../types/evolution'
import { scaleLinear } from 'd3-scale'
import { getDotRadius, REJECTED_OPACITY, ACTIVE_OPACITY } from '../../lib/scoring'
import { FitnessLegend } from './FitnessLegend'
import { DiffPopover } from './DiffPopover'

interface IslandsViewProps {
  candidates: CandidateData[]
  migrations: MigrationData[]
  islandCount: number
  status: EvolutionStatus
  lineageEvents?: LineageNode[]
}

interface IslandPosition {
  cx: number
  cy: number
  radius: number
}

interface SimNode {
  x: number
  y: number
  candidateId: string
  fitnessScore: number
  rejected: boolean
  mutationType: string
  island: number
}

const SVG_WIDTH = 600
const SVG_HEIGHT = 400
const MAX_CANDIDATES_PER_ISLAND = 20

function getIslandPositions(count: number, width: number, height: number): IslandPosition[] {
  if (count <= 0) return []
  const cols = Math.ceil(Math.sqrt(count))
  const rows = Math.ceil(count / cols)
  const cellW = width / cols
  const cellH = height / rows
  const radius = Math.min(cellW, cellH) * 0.4
  return Array.from({ length: count }, (_, i) => ({
    cx: (i % cols + 0.5) * cellW,
    cy: (Math.floor(i / cols) + 0.5) * cellH,
    radius,
  }))
}

export default function IslandsView({ candidates, migrations, islandCount, status: _status, seedFitness, lineageEvents }: IslandsViewProps & { seedFitness?: number | null }) {
  const { t } = useTranslation()
  const simulationRef = useRef<Simulation<SimNode, undefined> | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [nodePositions, setNodePositions] = useState<SimNode[]>([])
  const [recentMigration, setRecentMigration] = useState(false)
  const [tooltip, setTooltip] = useState<{ x: number; y: number; text: string } | null>(null)
  const [containerDims, setContainerDims] = useState({ width: 600, height: 400 })

  // Track container dimensions for DiffPopover positioning
  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const ro = new ResizeObserver(() => {
      setContainerDims({ width: el.clientWidth, height: el.clientHeight })
    })
    ro.observe(el)
    setContainerDims({ width: el.clientWidth, height: el.clientHeight })
    return () => ro.disconnect()
  }, [])

  // Hover state for DiffPopover (300ms delay)
  const hoverTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [hoverTarget, setHoverTarget] = useState<{
    candidateId: string; x: number; y: number
  } | null>(null)

  // Build lineage index from lineageEvents prop
  const lineageIndex = useMemo(() => {
    const map = new Map<string, LineageNode>()
    if (lineageEvents) {
      for (const e of lineageEvents) map.set(e.candidateId, e)
    }
    return map
  }, [lineageEvents])

  // Clean up hover timer on unmount
  useEffect(() => {
    return () => {
      if (hoverTimerRef.current) clearTimeout(hoverTimerRef.current)
    }
  }, [])

  // Dynamic color scale based on actual seed fitness range
  const fitnessColor = useMemo(() => {
    const min = seedFitness != null && seedFitness < -10 ? seedFitness : -10
    const mid = min / 3  // ~33% of the way from min to 0
    return scaleLinear<string>()
      .domain([min, mid, 0])
      .range(['#ef4444', '#f59e0b', '#22c55e'])
      .clamp(true)
  }, [seedFitness])

  const islandPositions = useMemo(
    () => getIslandPositions(islandCount, SVG_WIDTH, SVG_HEIGHT),
    [islandCount],
  )

  // Group candidates by island and cap per island
  const candidatesByIsland = useMemo(() => {
    const grouped = new Map<number, CandidateData[]>()
    for (const c of candidates) {
      const arr = grouped.get(c.island) || []
      arr.push(c)
      grouped.set(c.island, arr)
    }
    // Cap each island to last N candidates
    const capped = new Map<number, CandidateData[]>()
    const overflow = new Map<number, number>()
    for (const [island, arr] of grouped) {
      if (arr.length > MAX_CANDIDATES_PER_ISLAND) {
        overflow.set(island, arr.length - MAX_CANDIDATES_PER_ISLAND)
        capped.set(island, arr.slice(-MAX_CANDIDATES_PER_ISLAND))
      } else {
        capped.set(island, arr)
      }
    }
    return { capped, overflow }
  }, [candidates])

  // Build flat list of visible candidates
  const visibleCandidates = useMemo(() => {
    const flat: CandidateData[] = []
    for (const arr of candidatesByIsland.capped.values()) {
      flat.push(...arr)
    }
    return flat
  }, [candidatesByIsland])

  // Run d3-force simulation when visible candidates change
  useEffect(() => {
    if (visibleCandidates.length === 0 || islandPositions.length === 0) {
      setNodePositions([])
      return
    }

    // Stop previous simulation
    if (simulationRef.current) {
      simulationRef.current.stop()
    }

    const nodes: SimNode[] = visibleCandidates.map((c) => {
      const pos = islandPositions[c.island] || islandPositions[0]
      return {
        x: pos.cx + (Math.random() - 0.5) * pos.radius * 0.5,
        y: pos.cy + (Math.random() - 0.5) * pos.radius * 0.5,
        candidateId: c.candidateId,
        fitnessScore: c.fitnessScore,
        rejected: c.rejected,
        mutationType: c.mutationType,
        island: c.island,
      }
    })

    const sim = forceSimulation<SimNode>(nodes)

    // Apply per-island centering forces
    sim.force(
      'x',
      forceX<SimNode>((d) => {
        const pos = islandPositions[d.island] || islandPositions[0]
        return pos.cx
      }).strength(0.1),
    )
    sim.force(
      'y',
      forceY<SimNode>((d) => {
        const pos = islandPositions[d.island] || islandPositions[0]
        return pos.cy
      }).strength(0.1),
    )
    sim.force('collide', forceCollide<SimNode>((d) => getDotRadius(d.fitnessScore) + 1))

    sim.alpha(0.3).restart()

    let rafId: number
    sim.on('tick', () => {
      rafId = requestAnimationFrame(() => {
        // Clamp nodes within island circles
        for (const node of nodes) {
          const pos = islandPositions[node.island] || islandPositions[0]
          const dx = node.x - pos.cx
          const dy = node.y - pos.cy
          const dist = Math.sqrt(dx * dx + dy * dy)
          const maxDist = pos.radius - getDotRadius(node.fitnessScore) - 2
          if (dist > maxDist && maxDist > 0) {
            const scale = maxDist / dist
            node.x = pos.cx + dx * scale
            node.y = pos.cy + dy * scale
          }
        }
        setNodePositions([...nodes])
      })
    })

    simulationRef.current = sim

    return () => {
      cancelAnimationFrame(rafId)
      sim.stop()
    }
  }, [visibleCandidates, islandPositions])

  // Track recent migration events (show for 3 seconds)
  useEffect(() => {
    if (migrations.length === 0) return
    const lastMigration = migrations[migrations.length - 1]
    const migrationTime = new Date(lastMigration.timestamp).getTime()
    const now = Date.now()
    if (now - migrationTime < 3000) {
      setRecentMigration(true)
      const timeout = setTimeout(() => setRecentMigration(false), 3000 - (now - migrationTime))
      return () => clearTimeout(timeout)
    }
  }, [migrations])

  const isEmpty = candidates.length === 0 && islandCount === 0

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-4">
      <h3 className="text-sm font-medium text-slate-300 mb-3">{t('evolution.islands')}</h3>

      {isEmpty ? (
        <div className="flex items-center justify-center min-h-[400px]">
          <p style={{ color: COLORS.textMuted }}>{t('evolution.noIslandData')}</p>
        </div>
      ) : (
        <div className="relative" ref={containerRef}>
          <svg
            viewBox={`0 0 ${SVG_WIDTH} ${SVG_HEIGHT}`}
            className="w-full"
            style={{ minHeight: 300 }}
          >
            {/* Island circles (petri dishes) */}
            {islandPositions.map((pos, i) => (
              <g key={`island-${i}`}>
                <circle
                  cx={pos.cx}
                  cy={pos.cy}
                  r={pos.radius}
                  fill={COLORS.cardBg}
                  stroke={COLORS.border}
                  strokeWidth={2}
                />
                <text
                  x={pos.cx}
                  y={pos.cy - pos.radius - 8}
                  textAnchor="middle"
                  fill={COLORS.textSecondary}
                  fontSize={12}
                >
                  {t('evolution.island', { index: i })}
                </text>
                {/* Overflow badge */}
                {candidatesByIsland.overflow.get(i) && (
                  <text
                    x={pos.cx}
                    y={pos.cy + pos.radius + 16}
                    textAnchor="middle"
                    fill={COLORS.textMuted}
                    fontSize={10}
                  >
                    +{candidatesByIsland.overflow.get(i)} more
                  </text>
                )}
              </g>
            ))}

            {/* Migration arrows between islands */}
            {recentMigration && islandPositions.length >= 2 && (
              <>
                {islandPositions.map((from, i) =>
                  islandPositions
                    .filter((_, j) => j !== i)
                    .map((to, j) => (
                      <line
                        key={`migration-${i}-${j}`}
                        x1={from.cx}
                        y1={from.cy}
                        x2={to.cx}
                        y2={to.cy}
                        stroke={COLORS.blue}
                        strokeWidth={2}
                        strokeDasharray="5,5"
                        opacity={0.6}
                        style={{
                          animation: 'dash 0.5s linear infinite',
                        }}
                      />
                    )),
                )}
              </>
            )}

            {/* Candidate dots - use simulation positions when available, fallback to island center */}
            {(nodePositions.length > 0 ? nodePositions : visibleCandidates.map((c) => {
              const pos = islandPositions[c.island] || islandPositions[0]
              return {
                x: pos?.cx ?? 0,
                y: pos?.cy ?? 0,
                candidateId: c.candidateId,
                fitnessScore: c.fitnessScore,
                rejected: c.rejected,
                mutationType: c.mutationType,
                island: c.island,
              } as SimNode
            })).map((node) => (
              <circle
                key={node.candidateId}
                data-candidate={node.candidateId}
                cx={node.x}
                cy={node.y}
                r={getDotRadius(node.fitnessScore)}
                fill={fitnessColor(node.fitnessScore)}
                opacity={node.rejected ? REJECTED_OPACITY : ACTIVE_OPACITY}
                style={{ cursor: 'pointer', transition: 'cx 0.1s, cy 0.1s' }}
                onMouseEnter={(e) => {
                  const rect = (e.target as SVGCircleElement).ownerSVGElement?.getBoundingClientRect()
                  if (rect) {
                    const posX = e.clientX - rect.left
                    const posY = e.clientY - rect.top
                    setTooltip({
                      x: posX,
                      y: posY - 20,
                      text: (() => {
                        const pct = (seedFitness != null && seedFitness < 0)
                          ? Math.round(((node.fitnessScore - seedFitness) / (0 - seedFitness)) * 100)
                          : null
                        const fitnessStr = pct !== null
                          ? `${node.fitnessScore.toFixed(1)} (${pct}%)`
                          : node.fitnessScore.toFixed(3)
                        return `${node.candidateId.slice(0, 8)} | ${fitnessStr} | ${node.mutationType}`
                      })(),
                    })
                    // Start 300ms hover timer for DiffPopover (only in post-run mode)
                    if (lineageEvents && lineageIndex.has(node.candidateId)) {
                      if (hoverTimerRef.current) clearTimeout(hoverTimerRef.current)
                      hoverTimerRef.current = setTimeout(() => {
                        setHoverTarget({ candidateId: node.candidateId, x: posX, y: posY })
                      }, 300)
                    }
                  }
                }}
                onMouseLeave={() => {
                  setTooltip(null)
                  if (hoverTimerRef.current) clearTimeout(hoverTimerRef.current)
                  setHoverTarget(null)
                }}
              />
            ))}

            {/* Fitness color scale legend */}
            <FitnessLegend
              x={SVG_WIDTH - 110}
              y={SVG_HEIGHT - 35}
              gradientId="fitness-gradient-islands"
              minValue={seedFitness != null && seedFitness < -10 ? Math.round(seedFitness) : -10}
            />
          </svg>

          {/* Tooltip overlay */}
          {tooltip && (
            <div
              className="absolute pointer-events-none bg-slate-900 text-slate-200 text-xs px-2 py-1 rounded border border-slate-600 whitespace-nowrap"
              style={{ left: tooltip.x, top: tooltip.y, transform: 'translateX(-50%)' }}
            >
              {tooltip.text}
            </div>
          )}

          {/* DiffPopover (post-run mode only) */}
          {hoverTarget && lineageEvents && lineageEvents.length > 0 && (
            <DiffPopover
              candidateId={hoverTarget.candidateId}
              x={hoverTarget.x}
              y={hoverTarget.y}
              containerWidth={containerDims.width}
              containerHeight={containerDims.height}
              lineageIndex={lineageIndex}
            />
          )}

          {/* Migration indicator text */}
          {recentMigration && (
            <div className="absolute top-2 right-2 text-xs text-blue-400 flex items-center gap-1">
              <span className="h-1.5 w-1.5 rounded-full bg-blue-400 animate-pulse" />
              {t('evolution.migrationInProgress')}
            </div>
          )}

          {/* Status-based migration display for tests (always shows if migrations exist) */}
          {migrations.length > 0 && !recentMigration && (
            <div className="text-xs text-slate-500 mt-1">
              {migrations.length} migration{migrations.length !== 1 ? 's' : ''} recorded
            </div>
          )}

          {/* CSS for dash animation */}
          <style>{`
            @keyframes dash {
              to { stroke-dashoffset: -20; }
            }
          `}</style>
        </div>
      )}
    </div>
  )
}
