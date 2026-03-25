import { useEffect, useMemo, useRef, useState } from 'react'
import { zoom as d3Zoom } from 'd3-zoom'
import { select as d3Select } from 'd3-selection'
import type { LineageNode } from '../../types/evolution'
import { COLORS, MUTATION_COLORS } from '../../types/evolution'
import { traceWinningPath, deduplicateEvents } from '../../lib/lineage-utils'
import { fitnessColor, REJECTED_OPACITY, ACTIVE_OPACITY, ISLAND_COLORS } from '../../lib/scoring'
import { FitnessLegend } from './FitnessLegend'
import { DiffPopover } from './DiffPopover'

interface PhyloTreeProps {
  lineageEvents: LineageNode[]
  bestCandidateId: string | null
}

interface SimNode {
  x: number
  y: number
  candidateId: string
  parentIds: string[]
  generation: number
  island: number
  fitnessScore: number
  rejected: boolean
  mutationType: string
}

const SVG_WIDTH = 800
const ROW_SPACING = 80

export default function PhyloTree({ lineageEvents, bestCandidateId }: PhyloTreeProps) {
  const svgRef = useRef<SVGSVGElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const zoomRef = useRef<ReturnType<typeof d3Zoom<SVGSVGElement, unknown>> | null>(null)
  const [transform, setTransform] = useState({ x: 0, y: 0, k: 1 })
  const [tooltip, setTooltip] = useState<{
    x: number
    y: number
    node: SimNode
  } | null>(null)
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null)
  const [containerDims, setContainerDims] = useState({ width: 800, height: 600 })

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

  // Deduplicate events (last event per candidateId wins)
  const dedupedEvents = useMemo(
    () => deduplicateEvents(lineageEvents),
    [lineageEvents],
  )

  // Build lineage index from deduplicated events for DiffPopover
  const lineageIndex = useMemo(() => {
    const map = new Map<string, LineageNode>()
    for (const e of dedupedEvents) map.set(e.candidateId, e)
    return map
  }, [dedupedEvents])

  // Clean up hover timer on unmount
  useEffect(() => {
    return () => {
      if (hoverTimerRef.current) clearTimeout(hoverTimerRef.current)
    }
  }, [])

  // Compute winning path
  const winningPath = useMemo(
    () => traceWinningPath(dedupedEvents, bestCandidateId),
    [dedupedEvents, bestCandidateId],
  )

  // Get unique generations for Y-axis layout
  const generationSet = useMemo(() => {
    const gens = new Set<number>()
    for (const e of dedupedEvents) gens.add(e.generation)
    return Array.from(gens).sort((a, b) => a - b)
  }, [dedupedEvents])

  // Dynamic SVG height based on generation count
  const svgHeight = useMemo(
    () => Math.max(600, (generationSet.length + 1) * ROW_SPACING),
    [generationSet],
  )

  // Deterministic hierarchical layout computed synchronously
  const layoutNodes = useMemo(() => {
    if (dedupedEvents.length === 0) return []

    const genIndex = new Map(generationSet.map((g, i) => [g, i]))

    // First pass: assign initial positions to compute parent X averages
    const nodeMap = new Map<string, SimNode>()
    const nodesByGen = new Map<number, SimNode[]>()

    // Create all nodes with placeholder X
    for (const e of dedupedEvents) {
      const node: SimNode = {
        x: 0,
        y: ((genIndex.get(e.generation) ?? 0) + 1) * ROW_SPACING,
        candidateId: e.candidateId,
        parentIds: e.parentIds,
        generation: e.generation,
        island: e.island,
        fitnessScore: e.fitnessScore,
        rejected: e.rejected,
        mutationType: e.mutationType,
      }
      nodeMap.set(e.candidateId, node)

      const gen = e.generation
      if (!nodesByGen.has(gen)) nodesByGen.set(gen, [])
      nodesByGen.get(gen)!.push(node)
    }

    // Process generations in order (seeds first)
    for (const gen of generationSet) {
      const nodesInRow = nodesByGen.get(gen) ?? []

      // Compute ideal X for each node based on parent positions
      const idealXMap = new Map<string, number>()
      for (const node of nodesInRow) {
        const parentXValues: number[] = []
        for (const pid of node.parentIds) {
          const parent = nodeMap.get(pid)
          if (parent) parentXValues.push(parent.x)
        }
        if (parentXValues.length > 0) {
          // Average parent X position
          idealXMap.set(
            node.candidateId,
            parentXValues.reduce((a, b) => a + b, 0) / parentXValues.length,
          )
        } else {
          // Seeds: sort by island number, spread across width
          idealXMap.set(node.candidateId, node.island * 1000)
        }
      }

      // Sort nodes in this row by ideal X position
      nodesInRow.sort((a, b) => {
        const aIdeal = idealXMap.get(a.candidateId) ?? 0
        const bIdeal = idealXMap.get(b.candidateId) ?? 0
        return aIdeal - bIdeal
      })

      // Assign evenly spaced X positions
      const count = nodesInRow.length
      for (let i = 0; i < count; i++) {
        nodesInRow[i].x = (i + 1) * (SVG_WIDTH / (count + 1))
      }
    }

    return Array.from(nodeMap.values())
  }, [dedupedEvents, generationSet])

  // D3-zoom
  useEffect(() => {
    if (!svgRef.current) return

    const zoomBehavior = d3Zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.3, 3])
      .on('zoom', (event) => {
        setTransform({
          x: event.transform.x,
          y: event.transform.y,
          k: event.transform.k,
        })
      })

    d3Select(svgRef.current).call(zoomBehavior)
    zoomRef.current = zoomBehavior
  }, [])

  // Zoom control handlers
  const handleZoomIn = () => {
    if (!svgRef.current || !zoomRef.current) return
    const sel = d3Select(svgRef.current)
    zoomRef.current.scaleBy(sel as never, 1.3)
  }

  const handleZoomOut = () => {
    if (!svgRef.current || !zoomRef.current) return
    const sel = d3Select(svgRef.current)
    zoomRef.current.scaleBy(sel as never, 0.77)
  }

  const handleZoomReset = () => {
    if (!svgRef.current || !zoomRef.current) return
    setTransform({ x: 0, y: 0, k: 1 })
  }

  // Build node position index for drawing edges
  const nodeIndex = useMemo(() => {
    const map = new Map<string, SimNode>()
    for (const n of layoutNodes) map.set(n.candidateId, n)
    return map
  }, [layoutNodes])

  // Edge data
  const edges = useMemo(() => {
    const result: {
      x1: number
      y1: number
      x2: number
      y2: number
      winning: boolean
      isMigration: boolean
      key: string
    }[] = []
    for (const node of layoutNodes) {
      for (const pid of node.parentIds) {
        const parent = nodeIndex.get(pid)
        if (parent) {
          const bothWinning =
            winningPath.has(node.candidateId) && winningPath.has(pid)
          const isMigration = parent.island !== node.island
          result.push({
            x1: parent.x,
            y1: parent.y,
            x2: node.x,
            y2: node.y,
            winning: bothWinning,
            isMigration,
            key: `${pid}->${node.candidateId}`,
          })
        }
      }
    }
    return result
  }, [layoutNodes, nodeIndex, winningPath])

  // Separate edges: non-winning first, winning on top
  const nonWinningEdges = useMemo(() => edges.filter((e) => !e.winning), [edges])
  const winningEdges = useMemo(() => edges.filter((e) => e.winning), [edges])

  if (lineageEvents.length === 0) {
    return (
      <div className="rounded-lg border border-border bg-card/50 p-8 text-center">
        <p style={{ color: COLORS.textMuted }}>No lineage data</p>
      </div>
    )
  }

  return (
    <div ref={containerRef} className="rounded-lg border border-border bg-card/50 relative overflow-hidden">
      {/* Mutation Legend */}
      <div className="absolute top-3 right-3 z-10 bg-background/90 border border-border rounded-lg p-3">
        <p className="text-xs font-medium text-muted-foreground mb-2">Mutation Types</p>
        <div className="flex flex-col gap-1">
          {Object.entries(MUTATION_COLORS).map(([type, color]) => (
            <div key={type} className="flex items-center gap-2">
              <span
                className="w-3 h-3 rounded-full inline-block"
                style={{ backgroundColor: color }}
              />
              <span className="text-xs text-foreground">{type}</span>
            </div>
          ))}
        </div>
      </div>

      {/* SVG Canvas */}
      <svg
        ref={svgRef}
        viewBox={`0 0 ${SVG_WIDTH} ${svgHeight}`}
        className="w-full"
        style={{ minHeight: 500 }}
      >
        {/* Arrowhead markers */}
        <defs>
          <marker id="arrowhead" viewBox="0 0 10 10" refX="10" refY="5"
            markerWidth="6" markerHeight="6" orient="auto-start-reverse"
            fill="#64748b">
            <path d="M 0 0 L 10 5 L 0 10 z" />
          </marker>
          <marker id="arrowhead-winning" viewBox="0 0 10 10" refX="10" refY="5"
            markerWidth="6" markerHeight="6" orient="auto-start-reverse"
            fill="#22c55e">
            <path d="M 0 0 L 10 5 L 0 10 z" />
          </marker>
        </defs>

        <g transform={`translate(${transform.x},${transform.y}) scale(${transform.k})`}>
          {/* Non-winning edges (rendered first, below) */}
          {nonWinningEdges.map((edge) => (
            <path
              key={edge.key}
              d={`M ${edge.x1},${edge.y1} C ${edge.x1},${(edge.y1 + edge.y2) / 2} ${edge.x2},${(edge.y1 + edge.y2) / 2} ${edge.x2},${edge.y2}`}
              fill="none"
              stroke={edge.isMigration ? '#8b5cf6' : COLORS.border}
              strokeWidth={1}
              strokeDasharray={edge.isMigration ? '4 2' : undefined}
              opacity={edge.isMigration ? 0.5 : 0.25}
              markerEnd="url(#arrowhead)"
            />
          ))}

          {/* Winning edges (rendered on top) */}
          {winningEdges.map((edge) => (
            <path
              key={edge.key}
              d={`M ${edge.x1},${edge.y1} C ${edge.x1},${(edge.y1 + edge.y2) / 2} ${edge.x2},${(edge.y1 + edge.y2) / 2} ${edge.x2},${edge.y2}`}
              fill="none"
              stroke="#22c55e"
              strokeWidth={3}
              opacity={0.9}
              markerEnd="url(#arrowhead-winning)"
            />
          ))}

          {/* Nodes */}
          {layoutNodes.map((node) => {
            const isWinning = winningPath.has(node.candidateId)
            const nodeOpacity =
              hoveredNodeId === node.candidateId
                ? ACTIVE_OPACITY
                : node.rejected
                  ? REJECTED_OPACITY
                  : ACTIVE_OPACITY
            return (
              <g key={node.candidateId}>
                {/* Island identity ring */}
                <circle
                  cx={node.x}
                  cy={node.y}
                  r={isWinning ? 10 : 8}
                  fill="none"
                  stroke={ISLAND_COLORS[node.island % ISLAND_COLORS.length]}
                  strokeWidth={2}
                  opacity={nodeOpacity}
                />
                {/* Fitness-colored fill */}
                <circle
                  data-candidate={node.candidateId}
                  data-winning={isWinning ? 'true' : 'false'}
                  cx={node.x}
                  cy={node.y}
                  r={isWinning ? 8 : 6}
                  fill={fitnessColor(node.fitnessScore)}
                  stroke={isWinning ? COLORS.green : 'none'}
                  strokeWidth={isWinning ? 2 : 0}
                  opacity={nodeOpacity}
                  style={{ cursor: 'pointer' }}
                  onMouseEnter={(e) => {
                    setHoveredNodeId(node.candidateId)
                    const rect = (
                      e.target as SVGCircleElement
                    ).ownerSVGElement?.getBoundingClientRect()
                    if (rect) {
                      const posX = e.clientX - rect.left
                      const posY = e.clientY - rect.top
                      setTooltip({
                        x: posX,
                        y: posY - 30,
                        node,
                      })
                      // Start 300ms hover timer for DiffPopover
                      if (hoverTimerRef.current) clearTimeout(hoverTimerRef.current)
                      hoverTimerRef.current = setTimeout(() => {
                        setHoverTarget({ candidateId: node.candidateId, x: posX, y: posY })
                      }, 300)
                    }
                  }}
                  onMouseLeave={() => {
                    setHoveredNodeId(null)
                    setTooltip(null)
                    if (hoverTimerRef.current) clearTimeout(hoverTimerRef.current)
                    setHoverTarget(null)
                  }}
                />
              </g>
            )
          })}
        </g>

        {/* Fitness color scale legend */}
        <FitnessLegend
          x={SVG_WIDTH - 110}
          y={svgHeight - 130}
          gradientId="fitness-gradient-phylo"
        />
      </svg>

      {/* Tooltip */}
      {tooltip && (
        <div
          className="absolute pointer-events-none bg-background text-foreground text-xs px-3 py-2 rounded border border-border whitespace-nowrap z-20"
          style={{
            left: tooltip.x,
            top: tooltip.y,
            transform: 'translateX(-50%)',
          }}
        >
          <div className="font-mono font-bold">
            {tooltip.node.candidateId.slice(0, 8)}
          </div>
          <div>
            Fitness:{' '}
            <span className="text-emerald-400">
              {tooltip.node.fitnessScore.toFixed(3)}
            </span>
          </div>
          <div>Type: {tooltip.node.mutationType}</div>
          <div>Gen: {tooltip.node.generation} | Island: {tooltip.node.island}</div>
        </div>
      )}

      {/* DiffPopover */}
      {hoverTarget && (
        <DiffPopover
          candidateId={hoverTarget.candidateId}
          x={hoverTarget.x}
          y={hoverTarget.y}
          containerWidth={containerDims.width}
          containerHeight={containerDims.height}
          lineageIndex={lineageIndex}
        />
      )}

      {/* Zoom Controls */}
      <div className="absolute bottom-3 right-3 flex flex-col gap-1 z-10">
        <button
          aria-label="Zoom in"
          onClick={handleZoomIn}
          className="w-9 h-9 rounded-lg bg-secondary hover:bg-secondary/80 text-foreground text-lg font-bold flex items-center justify-center border border-border"
        >
          +
        </button>
        <button
          aria-label="Zoom out"
          onClick={handleZoomOut}
          className="w-9 h-9 rounded-lg bg-secondary hover:bg-secondary/80 text-foreground text-lg font-bold flex items-center justify-center border border-border"
        >
          -
        </button>
        <button
          aria-label="Reset zoom"
          onClick={handleZoomReset}
          className="w-9 h-9 rounded-lg bg-secondary hover:bg-secondary/80 text-foreground text-xs font-medium flex items-center justify-center border border-border"
        >
          1:1
        </button>
      </div>
    </div>
  )
}
