/**
 * EvidenceNetworkViz: Force-directed paper relationship graph.
 *
 * Renders the knowledge graph returned by GET /api/run/{run_id}/knowledge-graph.
 * Uses pure SVG with manual force simulation (no D3 dependency) for bundle size
 * and to avoid CSP issues. Nodes are colored by community, edges by relationship type.
 *
 * Falls back gracefully when the graph has no edges or the API returns an error.
 */

import { useState, useEffect, useRef, useCallback } from "react"
import { fetchKnowledgeGraph } from "@/lib/api"
import type { KnowledgeGraph, KnowledgeGraphNode, KnowledgeGraphEdge } from "@/lib/api"
import { Spinner, FetchError, EmptyState } from "@/components/ui/feedback"
import { cn } from "@/lib/utils"

const COMMUNITY_COLORS = [
  "#7c3aed", "#2563eb", "#059669", "#d97706", "#dc2626",
  "#0891b2", "#7c3aed", "#16a34a", "#9333ea", "#f59e0b",
]

const EDGE_COLORS: Record<string, string> = {
  shared_outcome: "#6ee7b7",
  shared_intervention: "#93c5fd",
  shared_population: "#fcd34d",
  embedding_similarity: "#d8b4fe",
  citation: "#f9a8d4",
}

const GAP_TYPE_LABELS: Record<string, string> = {
  underrepresented_population: "Population Gap",
  missing_outcome: "Outcome Gap",
  methodology_gap: "Methodology Gap",
}

interface NodePosition {
  x: number
  y: number
  vx: number
  vy: number
}

function useForceLayout(
  nodes: KnowledgeGraphNode[],
  edges: KnowledgeGraphEdge[],
  width: number,
  height: number,
): Map<string, NodePosition> {
  const [positions, setPositions] = useState<Map<string, NodePosition>>(new Map())

  useEffect(() => {
    if (!nodes.length) return

    const pos = new Map<string, NodePosition>()
    const cx = width / 2
    const cy = height / 2
    const radius = Math.min(width, height) * 0.35

    nodes.forEach((node, i) => {
      const angle = (2 * Math.PI * i) / nodes.length
      pos.set(node.id, {
        x: cx + radius * Math.cos(angle),
        y: cy + radius * Math.sin(angle),
        vx: 0,
        vy: 0,
      })
    })

    // Simple force simulation: repulsion + spring + center gravity
    const REPULSION = 1200
    const SPRING_LEN = 80
    const SPRING_K = 0.05
    const DAMPING = 0.85
    const GRAVITY = 0.01

    for (let iter = 0; iter < 80; iter++) {
      // Repulsion between all pairs
      const nodeArr = nodes.map((n) => ({ id: n.id, p: pos.get(n.id)! }))
      for (let i = 0; i < nodeArr.length; i++) {
        for (let j = i + 1; j < nodeArr.length; j++) {
          const a = nodeArr[i].p
          const b = nodeArr[j].p
          const dx = b.x - a.x
          const dy = b.y - a.y
          const dist = Math.sqrt(dx * dx + dy * dy) || 1
          const force = REPULSION / (dist * dist)
          const fx = (dx / dist) * force
          const fy = (dy / dist) * force
          a.vx -= fx
          a.vy -= fy
          b.vx += fx
          b.vy += fy
        }
      }

      // Spring forces along edges
      for (const edge of edges) {
        const a = pos.get(edge.source)
        const b = pos.get(edge.target)
        if (!a || !b) continue
        const dx = b.x - a.x
        const dy = b.y - a.y
        const dist = Math.sqrt(dx * dx + dy * dy) || 1
        const force = (dist - SPRING_LEN) * SPRING_K * edge.weight
        const fx = (dx / dist) * force
        const fy = (dy / dist) * force
        a.vx += fx
        a.vy += fy
        b.vx -= fx
        b.vy -= fy
      }

      // Gravity toward center + integrate
      for (const [, p] of pos) {
        p.vx += (cx - p.x) * GRAVITY
        p.vy += (cy - p.y) * GRAVITY
        p.vx *= DAMPING
        p.vy *= DAMPING
        p.x += p.vx
        p.y += p.vy
        p.x = Math.max(20, Math.min(width - 20, p.x))
        p.y = Math.max(20, Math.min(height - 20, p.y))
      }
    }

    setPositions(new Map(pos))
  }, [nodes, edges, width, height])

  return positions
}

interface GraphCanvasProps {
  graph: KnowledgeGraph
  width: number
  height: number
}

function GraphCanvas({ graph, width, height }: GraphCanvasProps) {
  const positions = useForceLayout(graph.nodes, graph.edges, width, height)
  const [hovered, setHovered] = useState<string | null>(null)

  if (!positions.size) {
    return (
      <div className="flex items-center justify-center h-full">
        <Spinner size="md" className="text-violet-500" />
      </div>
    )
  }

  const hoveredNode = hovered ? graph.nodes.find((n) => n.id === hovered) : null

  return (
    <div className="relative" style={{ width, height }}>
      <svg width={width} height={height} className="absolute inset-0">
        <defs>
          <marker id="arrowhead" markerWidth="6" markerHeight="4" refX="6" refY="2" orient="auto">
            <polygon points="0 0, 6 2, 0 4" fill="#52525b" />
          </marker>
        </defs>

        {/* Edges */}
        {graph.edges.map((edge, i) => {
          const src = positions.get(edge.source)
          const tgt = positions.get(edge.target)
          if (!src || !tgt) return null
          const color = EDGE_COLORS[edge.rel_type] || "#52525b"
          const opacity = hovered
            ? edge.source === hovered || edge.target === hovered ? 0.9 : 0.15
            : 0.5
          return (
            <line
              key={i}
              x1={src.x}
              y1={src.y}
              x2={tgt.x}
              y2={tgt.y}
              stroke={color}
              strokeWidth={Math.max(0.5, edge.weight * 2)}
              strokeOpacity={opacity}
              markerEnd="url(#arrowhead)"
            />
          )
        })}

        {/* Nodes */}
        {graph.nodes.map((node) => {
          const pos = positions.get(node.id)
          if (!pos) return null
          const communityColor = COMMUNITY_COLORS[node.community_id % COMMUNITY_COLORS.length] || "#6b7280"
          const isHovered = hovered === node.id
          return (
            <g
              key={node.id}
              transform={`translate(${pos.x},${pos.y})`}
              onMouseEnter={() => setHovered(node.id)}
              onMouseLeave={() => setHovered(null)}
              style={{ cursor: "pointer" }}
            >
              <circle
                r={isHovered ? 10 : 7}
                fill={communityColor}
                fillOpacity={0.85}
                stroke={isHovered ? "#fff" : communityColor}
                strokeWidth={isHovered ? 2 : 1}
              />
              {isHovered && (
                <text
                  y={-14}
                  textAnchor="middle"
                  fontSize={10}
                  fill="#e4e4e7"
                  className="pointer-events-none"
                >
                  {node.title.length > 40 ? node.title.slice(0, 40) + "..." : node.title}
                </text>
              )}
            </g>
          )
        })}
      </svg>

      {/* Hover tooltip */}
      {hoveredNode && (
        <div className="absolute top-2 left-2 p-2 bg-zinc-900 border border-zinc-700 rounded text-xs text-zinc-300 max-w-xs z-10 pointer-events-none">
          <p className="font-medium text-zinc-100 mb-0.5">{hoveredNode.title}</p>
          <p className="text-zinc-500">{hoveredNode.year} | {hoveredNode.study_design}</p>
          {hoveredNode.community_id >= 0 && (
            <p className="text-violet-400">Cluster {hoveredNode.community_id}</p>
          )}
        </div>
      )}
    </div>
  )
}

interface EvidenceNetworkVizProps {
  runId: string
}

export function EvidenceNetworkViz({ runId }: EvidenceNetworkVizProps) {
  const [graph, setGraph] = useState<KnowledgeGraph | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [dims, setDims] = useState({ width: 600, height: 400 })

  useEffect(() => {
    if (!containerRef.current) return
    const obs = new ResizeObserver((entries) => {
      const entry = entries[0]
      if (entry) {
        setDims({
          width: Math.floor(entry.contentRect.width),
          height: Math.max(300, Math.floor(entry.contentRect.width * 0.55)),
        })
      }
    })
    obs.observe(containerRef.current)
    return () => obs.disconnect()
  }, [])

  useEffect(() => {
    setLoading(true)
    setError(null)
    fetchKnowledgeGraph(runId)
      .then(setGraph)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false))
  }, [runId])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-48">
        <Spinner size="md" className="text-violet-500" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="py-6">
        <FetchError message={error} onRetry={() => {
          setLoading(true); setError(null)
          fetchKnowledgeGraph(runId)
            .then(setGraph)
            .catch((e) => setError(e instanceof Error ? e.message : String(e)))
            .finally(() => setLoading(false))
        }} />
      </div>
    )
  }

  if (!graph || graph.nodes.length === 0) {
    return (
      <EmptyState
        heading="No knowledge graph data yet."
        className="py-12"
      />
    )
  }

  const relTypes = [...new Set(graph.edges.map((e) => e.rel_type))]

  return (
    <div className="space-y-4">
      {/* Stats bar */}
      <div className="flex items-center gap-4 p-3 rounded-lg bg-zinc-900 border border-zinc-800 text-sm flex-wrap">
        <span className="text-zinc-400">
          <span className="text-zinc-200 font-semibold">{graph.nodes.length}</span> papers
        </span>
        <span className="text-zinc-700">|</span>
        <span className="text-zinc-400">
          <span className="text-zinc-200 font-semibold">{graph.edges.length}</span> relationships
        </span>
        <span className="text-zinc-700">|</span>
        <span className="text-zinc-400">
          <span className="text-zinc-200 font-semibold">{graph.communities.length}</span> clusters
        </span>
        {graph.gaps.length > 0 && (
          <>
            <span className="text-zinc-700">|</span>
            <span className="text-amber-400 font-semibold">{graph.gaps.length} research gaps</span>
          </>
        )}
      </div>

      {/* Legend */}
      {relTypes.length > 0 && (
        <div className="flex items-center gap-3 flex-wrap text-xs text-zinc-500">
          <span>Edge types:</span>
          {relTypes.map((t) => (
            <span key={t} className="flex items-center gap-1">
              <span
                className="inline-block w-3 h-1 rounded-full"
                style={{ backgroundColor: EDGE_COLORS[t] || "#52525b" }}
              />
              {t.replace(/_/g, " ")}
            </span>
          ))}
        </div>
      )}

      {/* Graph canvas */}
      <div
        ref={containerRef}
        className="w-full rounded-lg border border-zinc-800 bg-zinc-950 overflow-hidden"
        style={{ height: dims.height }}
      >
        {graph.edges.length === 0 ? (
          <div className="flex items-center justify-center h-full text-sm text-zinc-500">
            No edges found -- papers may be too heterogeneous to cluster.
          </div>
        ) : (
          <GraphCanvas graph={graph} width={dims.width} height={dims.height} />
        )}
      </div>

      {/* Research gaps */}
      {graph.gaps.length > 0 && (
        <div className="space-y-2">
          <h4 className="text-sm font-semibold text-zinc-300">Detected Research Gaps</h4>
          {graph.gaps.map((gap) => (
            <div
              key={gap.id}
              className="p-3 rounded-lg border border-amber-900/50 bg-amber-900/10 text-sm"
            >
              <span className="inline-block px-1.5 py-0.5 rounded text-xs font-medium bg-amber-900/50 text-amber-300 border border-amber-800 mb-1.5">
                {GAP_TYPE_LABELS[gap.gap_type] || gap.gap_type}
              </span>
              <p className="text-zinc-300 text-xs leading-relaxed">{gap.description}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
