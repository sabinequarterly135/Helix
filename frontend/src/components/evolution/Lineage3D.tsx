import { useRef, useState, useMemo, useCallback, useEffect } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import { OrbitControls, Line, Html } from '@react-three/drei'
import { EffectComposer, Bloom } from '@react-three/postprocessing'
import * as THREE from 'three'
import type { LineageNode } from '../../types/evolution'
import { MUTATION_COLORS } from '../../types/evolution'
import { fitnessColor, ISLAND_COLORS, REJECTED_OPACITY, ACTIVE_OPACITY } from '../../lib/scoring'
import { traceWinningPath, deduplicateEvents } from '../../lib/lineage-utils'
import { DiffPopover } from './DiffPopover'

// ---------------------------------------------------------------------------
// WebGL availability check
// ---------------------------------------------------------------------------
function isWebGLAvailable(): boolean {
  try {
    const canvas = document.createElement('canvas')
    return !!(canvas.getContext('webgl2') || canvas.getContext('webgl'))
  } catch {
    return false
  }
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
interface Lineage3DProps {
  lineageEvents: LineageNode[]
  bestCandidateId: string | null
}

interface SimNode3D {
  id: string
  parentIds: string[]
  generation: number
  island: number
  fitnessScore: number
  rejected: boolean
  mutationType: string
  isWinning: boolean
  x: number
  y: number
  z: number
}

interface EdgeData {
  sourceId: string
  targetId: string
  isWinning: boolean
  isMigration: boolean
}

// ---------------------------------------------------------------------------
// Layout constants
// ---------------------------------------------------------------------------
const GEN_SPACING = 3.0
const ISLAND_SPACING = 5.0
const NODE_SPACING = 1.5

// ---------------------------------------------------------------------------
// Performance constant: reduce helix detail for large graphs
// ---------------------------------------------------------------------------
const HELIX_DETAIL_THRESHOLD = 80

// ---------------------------------------------------------------------------
// DNA Helix Edge sub-component
// ---------------------------------------------------------------------------
function DnaHelixEdge({
  source,
  target,
  isWinning,
  lowDetail,
}: {
  source: [number, number, number]
  target: [number, number, number]
  isWinning: boolean
  lowDetail: boolean
}) {
  const { strandGeomA, strandGeomB, rungPositions } = useMemo(() => {
    const srcVec = new THREE.Vector3(...source)
    const tgtVec = new THREE.Vector3(...target)
    const distance = srcVec.distanceTo(tgtVec)

    // Build central axis as a gentle arc
    const mid = new THREE.Vector3().addVectors(srcVec, tgtVec).multiplyScalar(0.5)
    mid.y += distance * 0.15
    const axisCurve = new THREE.CatmullRomCurve3([srcVec, mid, tgtVec])

    const sampleCount = lowDetail && !isWinning ? 20 : 40
    const helixRadius = isWinning ? 0.12 : 0.08
    const tubeRadius = isWinning ? 0.025 : 0.015
    const twistRate = Math.PI * 6 // 3 full rotations

    // Build a consistent up reference for computing perpendicular offsets
    const globalUp = new THREE.Vector3(0, 1, 0)

    const helixPointsA: THREE.Vector3[] = []
    const helixPointsB: THREE.Vector3[] = []
    const rungs: Array<{ a: THREE.Vector3; b: THREE.Vector3 }> = []

    for (let i = 0; i <= sampleCount; i++) {
      const t = i / sampleCount
      const axisPoint = axisCurve.getPointAt(t)
      const tangent = axisCurve.getTangentAt(t).normalize()

      // Compute perpendicular frame
      const perp = new THREE.Vector3().crossVectors(tangent, globalUp)
      if (perp.lengthSq() < 0.001) {
        // Tangent is nearly parallel to up -- use alternate reference
        perp.crossVectors(tangent, new THREE.Vector3(1, 0, 0))
      }
      perp.normalize()
      const biperp = new THREE.Vector3().crossVectors(tangent, perp).normalize()

      const angle = t * twistRate
      const cosA = Math.cos(angle) * helixRadius
      const sinA = Math.sin(angle) * helixRadius

      // Strand A
      const pA = axisPoint.clone()
        .addScaledVector(perp, cosA)
        .addScaledVector(biperp, sinA)
      helixPointsA.push(pA)

      // Strand B (180 degrees offset)
      const pB = axisPoint.clone()
        .addScaledVector(perp, -cosA)
        .addScaledVector(biperp, -sinA)
      helixPointsB.push(pB)

      // Add rungs every ~5 samples (skip if lowDetail and not winning)
      const skipRungs = lowDetail && !isWinning
      if (!skipRungs && i > 0 && i < sampleCount && i % 5 === 0) {
        rungs.push({ a: pA.clone(), b: pB.clone() })
      }
    }

    const curveA = new THREE.CatmullRomCurve3(helixPointsA)
    const curveB = new THREE.CatmullRomCurve3(helixPointsB)

    const segCount = lowDetail && !isWinning ? 20 : 40
    const radialSegs = 4

    const geomA = new THREE.TubeGeometry(curveA, segCount, tubeRadius, radialSegs, false)
    const geomB = new THREE.TubeGeometry(curveB, segCount, tubeRadius, radialSegs, false)

    return {
      strandGeomA: geomA,
      strandGeomB: geomB,
      rungPositions: rungs,
    }
  }, [source, target, isWinning, lowDetail])

  if (isWinning) {
    return (
      <group>
        {/* Winning helix strand A */}
        <mesh geometry={strandGeomA}>
          <meshBasicMaterial
            color={new THREE.Color(0.1, 2.0, 0.3)}
            toneMapped={false}
          />
        </mesh>
        {/* Winning helix strand B */}
        <mesh geometry={strandGeomB}>
          <meshBasicMaterial
            color={new THREE.Color(0.1, 2.0, 0.3)}
            toneMapped={false}
          />
        </mesh>
        {/* Rungs */}
        {rungPositions.map((rung, ri) => (
          <Line
            key={`rung-${ri}`}
            points={[[rung.a.x, rung.a.y, rung.a.z], [rung.b.x, rung.b.y, rung.b.z]]}
            color="#4ade80"
            lineWidth={1}
            transparent
            opacity={0.5}
          />
        ))}
      </group>
    )
  }

  return (
    <group>
      {/* Regular helix strand A */}
      <mesh geometry={strandGeomA}>
        <meshStandardMaterial
          color="#475569"
          transparent
          opacity={0.5}
        />
      </mesh>
      {/* Regular helix strand B */}
      <mesh geometry={strandGeomB}>
        <meshStandardMaterial
          color="#475569"
          transparent
          opacity={0.5}
        />
      </mesh>
      {/* Rungs */}
      {rungPositions.map((rung, ri) => (
        <Line
          key={`rung-${ri}`}
          points={[[rung.a.x, rung.a.y, rung.a.z], [rung.b.x, rung.b.y, rung.b.z]]}
          color="#334155"
          lineWidth={0.5}
          transparent
          opacity={0.3}
        />
      ))}
    </group>
  )
}

// ---------------------------------------------------------------------------
// Winning Helix Pulse wrapper (animated emissive breathing for winning edges)
// ---------------------------------------------------------------------------
function WinningHelixPulse({
  source,
  target,
  lowDetail,
}: {
  source: [number, number, number]
  target: [number, number, number]
  lowDetail: boolean
}) {
  const groupRef = useRef<THREE.Group>(null!)

  useFrame(({ clock }) => {
    if (!groupRef.current) return
    // Sinusoidal pulse: period ~2s
    const intensity = 0.3 + 0.7 * (0.5 + 0.5 * Math.sin(clock.elapsedTime * Math.PI))
    // Apply to all mesh children's material emissiveIntensity
    groupRef.current.traverse((child) => {
      if (child instanceof THREE.Mesh && child.material) {
        const mat = child.material as THREE.MeshBasicMaterial
        if (mat.color) {
          // Scale the HDR green channel for pulsing bloom effect
          mat.color.setRGB(0.1, 0.3 + intensity * 1.7, 0.3)
        }
      }
    })
  })

  return (
    <group ref={groupRef}>
      <DnaHelixEdge source={source} target={target} isWinning={true} lowDetail={lowDetail} />
    </group>
  )
}

// ---------------------------------------------------------------------------
// WinningNode sub-component (uses useFrame for pulse animation)
// ---------------------------------------------------------------------------
function WinningNode({
  position,
  onPointerOver,
  onPointerOut,
  children,
}: {
  position: [number, number, number]
  onPointerOver: (event: React.PointerEvent) => void
  onPointerOut: () => void
  children?: React.ReactNode
}) {
  const meshRef = useRef<THREE.Mesh>(null!)

  useFrame(({ clock }) => {
    if (meshRef.current) {
      const s = 1.0 + 0.15 * Math.sin(clock.elapsedTime * Math.PI)
      meshRef.current.scale.setScalar(s)
    }
  })

  return (
    <mesh
      ref={meshRef}
      position={position}
      onPointerOver={onPointerOver}
      onPointerOut={onPointerOut}
    >
      <sphereGeometry args={[0.4, 16, 16]} />
      <meshBasicMaterial
        color={[0.3, 1.5, 0.3]}
        toneMapped={false}
      />
      {children}
    </mesh>
  )
}

// ---------------------------------------------------------------------------
// RegularNode sub-component
// ---------------------------------------------------------------------------
function RegularNode({
  position,
  color,
  opacity,
  islandColor,
  onPointerOver,
  onPointerOut,
  children,
}: {
  position: [number, number, number]
  color: string
  opacity: number
  islandColor: string
  onPointerOver: (event: React.PointerEvent) => void
  onPointerOut: () => void
  children?: React.ReactNode
}) {
  return (
    <group position={position}>
      {/* Island identity ring */}
      <mesh>
        <sphereGeometry args={[0.38, 16, 16]} />
        <meshBasicMaterial
          color={islandColor}
          wireframe
          transparent
          opacity={0.2}
        />
      </mesh>
      {/* Main node */}
      <mesh onPointerOver={onPointerOver} onPointerOut={onPointerOut}>
        <sphereGeometry args={[0.3, 16, 16]} />
        <meshStandardMaterial
          color={color}
          transparent
          opacity={opacity}
        />
        {children}
      </mesh>
    </group>
  )
}

// ---------------------------------------------------------------------------
// Tooltip sub-component
// ---------------------------------------------------------------------------
function NodeTooltip({ node }: { node: SimNode3D }) {
  return (
    <Html distanceFactor={10} style={{ pointerEvents: 'none' }}>
      <div className="bg-slate-900 text-slate-200 text-xs px-3 py-2 rounded border border-slate-600 whitespace-nowrap">
        <div className="font-mono font-bold">{node.id.slice(0, 8)}</div>
        <div>Fitness: {node.fitnessScore.toFixed(3)}</div>
        <div>Gen: {node.generation} | Island: {node.island}</div>
        <div>Type: {node.mutationType}</div>
      </div>
    </Html>
  )
}

// ---------------------------------------------------------------------------
// Inner scene component (avoids hooks-after-conditional-return)
// ---------------------------------------------------------------------------
function Lineage3DScene({
  lineageEvents,
  bestCandidateId,
}: Lineage3DProps) {
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [containerDims, setContainerDims] = useState({ width: 800, height: 500 })

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

  // DiffPopover hover state (300ms delay)
  const hoverTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [hoverTarget, setHoverTarget] = useState<{
    candidateId: string; x: number; y: number
  } | null>(null)

  // Build lineage index for DiffPopover
  const lineageIndex = useMemo(() => {
    const map = new Map<string, LineageNode>()
    for (const e of lineageEvents) map.set(e.candidateId, e)
    return map
  }, [lineageEvents])

  // Clean up hover timer on unmount
  useEffect(() => {
    return () => { if (hoverTimerRef.current) clearTimeout(hoverTimerRef.current) }
  }, [])

  // --- Data processing with deterministic layout ---
  const { nodes, edges } = useMemo(() => {
    const deduped = deduplicateEvents(lineageEvents)
    const winning = traceWinningPath(deduped, bestCandidateId)

    // Assign unique island indices for Z-positioning
    const uniqueIslands = [...new Set(deduped.map((e) => e.island))].sort((a, b) => a - b)
    const islandIndexMap = new Map(uniqueIslands.map((island, idx) => [island, idx]))
    const numIslands = uniqueIslands.length

    // Group by (generation, island) for X-axis spread
    const groupKey = (gen: number, island: number) => `${gen}:${island}`
    const groups = new Map<string, LineageNode[]>()
    for (const e of deduped) {
      const key = groupKey(e.generation, e.island)
      if (!groups.has(key)) groups.set(key, [])
      groups.get(key)!.push(e)
    }

    // Build node array first with placeholder X for parent-alignment pass
    const nodeMap = new Map<string, SimNode3D>()
    const nodeArray: SimNode3D[] = deduped.map((e) => {
      const islandIdx = islandIndexMap.get(e.island) ?? 0
      const node: SimNode3D = {
        id: e.candidateId,
        parentIds: e.parentIds,
        generation: e.generation,
        island: e.island,
        fitnessScore: e.fitnessScore,
        rejected: e.rejected,
        mutationType: e.mutationType,
        isWinning: winning.has(e.candidateId),
        x: 0, // will be computed below
        y: -e.generation * GEN_SPACING, // seeds at y=0 (top), deeper gens go negative
        z: (islandIdx - (numIslands - 1) / 2) * ISLAND_SPACING,
      }
      nodeMap.set(e.candidateId, node)
      return node
    })

    // Sort generations ascending for ordered processing
    const uniqueGens = [...new Set(deduped.map((e) => e.generation))].sort((a, b) => a - b)

    // Compute X positions generation by generation (so parents are positioned first)
    for (const gen of uniqueGens) {
      // Group nodes in this generation by island
      const genIslandGroups = new Map<number, SimNode3D[]>()
      for (const node of nodeArray) {
        if (node.generation !== gen) continue
        if (!genIslandGroups.has(node.island)) genIslandGroups.set(node.island, [])
        genIslandGroups.get(node.island)!.push(node)
      }

      // For each island group, sort by parent X average and spread evenly
      for (const [, group] of genIslandGroups) {
        // Compute ideal X for each node based on parent positions
        const idealXMap = new Map<string, number>()
        for (const node of group) {
          const parentXValues: number[] = []
          for (const pid of node.parentIds) {
            const parent = nodeMap.get(pid)
            if (parent) parentXValues.push(parent.x)
          }
          if (parentXValues.length > 0) {
            idealXMap.set(
              node.id,
              parentXValues.reduce((a, b) => a + b, 0) / parentXValues.length,
            )
          } else {
            idealXMap.set(node.id, 0)
          }
        }

        // Sort by ideal X
        group.sort((a, b) => {
          const aIdeal = idealXMap.get(a.id) ?? 0
          const bIdeal = idealXMap.get(b.id) ?? 0
          return aIdeal - bIdeal
        })

        // Spread evenly along X axis, centered around 0
        const groupSize = group.length
        for (let i = 0; i < groupSize; i++) {
          group[i].x = (i - (groupSize - 1) / 2) * NODE_SPACING
        }
      }
    }

    // Build edge array
    const nodeIndex = new Map(deduped.map((e) => [e.candidateId, e]))
    const edgeArray: EdgeData[] = []
    for (const e of deduped) {
      for (const pid of e.parentIds) {
        if (nodeIndex.has(pid)) {
          const parent = nodeIndex.get(pid)!
          edgeArray.push({
            sourceId: pid,
            targetId: e.candidateId,
            isWinning: winning.has(pid) && winning.has(e.candidateId),
            isMigration: parent.island !== e.island,
          })
        }
      }
    }

    return { nodes: nodeArray, edges: edgeArray, winningIds: winning }
  }, [lineageEvents, bestCandidateId])

  // --- Build position lookup ---
  const nodePositions = useMemo(() => {
    const map = new Map<string, [number, number, number]>()
    for (const n of nodes) {
      map.set(n.id, [n.x, n.y, n.z])
    }
    return map
  }, [nodes])

  const hoveredNode = useMemo(() => {
    if (!hoveredNodeId) return null
    return nodes.find((n) => n.id === hoveredNodeId) ?? null
  }, [nodes, hoveredNodeId])

  const handlePointerOver = useCallback((id: string, event: React.PointerEvent) => {
    setHoveredNodeId(id)
    // Start 300ms timer for DiffPopover
    if (hoverTimerRef.current) clearTimeout(hoverTimerRef.current)
    const container = containerRef.current
    if (container) {
      const rect = container.getBoundingClientRect()
      const x = (event.clientX ?? event.nativeEvent?.clientX ?? 0) - rect.left
      const y = (event.clientY ?? event.nativeEvent?.clientY ?? 0) - rect.top
      hoverTimerRef.current = setTimeout(() => {
        setHoverTarget({ candidateId: id, x, y })
      }, 300)
    }
  }, [])

  const handlePointerOut = useCallback(() => {
    setHoveredNodeId(null)
    if (hoverTimerRef.current) clearTimeout(hoverTimerRef.current)
    setHoverTarget(null)
  }, [])

  // Determine if we should use low detail helix (performance optimization)
  const lowDetail = edges.length > HELIX_DETAIL_THRESHOLD

  return (
    <div ref={containerRef} className="bg-slate-800 border border-slate-700 rounded-lg p-4 h-[500px] relative">
      {/* Mutation type legend overlay */}
      <div className="absolute top-3 right-3 z-10 bg-slate-900/80 border border-slate-700 rounded px-3 py-2 text-xs text-slate-300">
        {Object.entries(MUTATION_COLORS).map(([type, color]) => (
          <div key={type} className="flex items-center gap-2 py-0.5">
            <span
              className="inline-block w-2.5 h-2.5 rounded-full"
              style={{ backgroundColor: color }}
            />
            <span>{type}</span>
          </div>
        ))}
      </div>

      <Canvas camera={{ position: [0, -8, -20], fov: 45 }}>
        <ambientLight intensity={0.35} />
        <pointLight position={[10, 10, -15]} intensity={0.8} />
        <pointLight position={[-5, -5, 10]} intensity={0.3} color="#6366f1" />
        <OrbitControls enableDamping />

        {/* Edges */}
        {nodes.length > 0 && edges.map((edge, i) => {
          const sourcePos = nodePositions.get(edge.sourceId)
          const targetPos = nodePositions.get(edge.targetId)
          if (!sourcePos || !targetPos) return null

          if (edge.isWinning) {
            return (
              <WinningHelixPulse
                key={`edge-${i}`}
                source={sourcePos}
                target={targetPos}
                lowDetail={lowDetail}
              />
            )
          }
          if (edge.isMigration) {
            return (
              <Line
                key={`edge-${i}`}
                points={[sourcePos, targetPos]}
                color="#8b5cf6"
                lineWidth={1.5}
                transparent
                opacity={0.7}
                dashed={false}
              />
            )
          }
          return (
            <DnaHelixEdge
              key={`edge-${i}`}
              source={sourcePos}
              target={targetPos}
              isWinning={false}
              lowDetail={lowDetail}
            />
          )
        })}

        {/* Nodes */}
        {nodes.map((node) => {
          const pos = nodePositions.get(node.id)
          if (!pos) return null

          if (node.isWinning) {
            return (
              <WinningNode
                key={node.id}
                position={pos}
                onPointerOver={(e) => handlePointerOver(node.id, e)}
                onPointerOut={handlePointerOut}
              >
                {hoveredNode && hoveredNode.id === node.id && (
                  <NodeTooltip node={hoveredNode} />
                )}
              </WinningNode>
            )
          }

          const nodeColor = fitnessColor(node.fitnessScore) as string
          const nodeOpacity = node.rejected ? REJECTED_OPACITY : ACTIVE_OPACITY
          const islandColor = ISLAND_COLORS[node.island % ISLAND_COLORS.length]

          return (
            <RegularNode
              key={node.id}
              position={pos}
              color={nodeColor}
              opacity={nodeOpacity}
              islandColor={islandColor}
              onPointerOver={(e) => handlePointerOver(node.id, e)}
              onPointerOut={handlePointerOut}
            >
              {hoveredNode && hoveredNode.id === node.id && (
                <NodeTooltip node={hoveredNode} />
              )}
            </RegularNode>
          )
        })}

        {/* Bloom postprocessing for selective glow */}
        <EffectComposer>
          <Bloom
            luminanceThreshold={1.5}
            luminanceSmoothing={0.3}
            intensity={0.8}
            mipmapBlur
          />
        </EffectComposer>
      </Canvas>

      {/* DiffPopover overlay (appears after 300ms hover) */}
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
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main Lineage3D component (exported) -- WebGL gate before hooks
// ---------------------------------------------------------------------------
export default function Lineage3D({
  lineageEvents,
  bestCandidateId,
}: Lineage3DProps) {
  if (!isWebGLAvailable()) {
    return (
      <div className="flex items-center justify-center h-[500px] bg-slate-800 border border-slate-700 rounded-lg">
        <p className="text-slate-400">
          WebGL is not supported in your browser. Use the 2D view instead.
        </p>
      </div>
    )
  }

  if (lineageEvents.length === 0) {
    return (
      <div className="flex items-center justify-center h-[500px] bg-slate-800 border border-slate-700 rounded-lg">
        <p className="text-slate-400">No lineage data</p>
      </div>
    )
  }

  return (
    <Lineage3DScene
      lineageEvents={lineageEvents}
      bestCandidateId={bestCandidateId}
    />
  )
}
