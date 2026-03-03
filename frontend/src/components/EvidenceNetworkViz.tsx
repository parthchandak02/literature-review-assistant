/**
 * EvidenceNetworkViz: Force-directed paper relationship graph.
 *
 * Renders the knowledge graph returned by GET /api/run/{run_id}/knowledge-graph.
 * Uses pure SVG with manual force simulation (no D3 dependency) for bundle size
 * and to avoid CSP issues. Nodes are colored by community, edges by relationship type.
 *
 * Falls back gracefully when the graph has no edges or the API returns an error.
 *
 * UI features:
 *   - VOS-style distance-aware layout (high-similarity edges cluster nodes closer)
 *   - Always-visible truncated node labels below each circle
 *   - Click-to-detail sidebar panel with full paper metadata
 *   - Download SVG button
 *   - Amber dashed outer ring on gap-related nodes
 */

import { useState, useEffect, useRef, useCallback } from "react"
import { Network, Download, X } from "lucide-react"
import { fetchKnowledgeGraph } from "@/lib/api"
import type { KnowledgeGraph, KnowledgeGraphNode, KnowledgeGraphEdge } from "@/lib/api"
import { Spinner, FetchError, EmptyState } from "@/components/ui/feedback"

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

function truncateTitle(title: string, max = 18): string {
  return title.length <= max ? title : title.slice(0, max - 2) + ".."
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

    // VOS-style force simulation: repulsion + distance-aware spring + center gravity.
    // SPRING_LEN is dynamic per edge: shorter for high-weight (similar) edges,
    // longer for low-weight edges -- this clusters semantically related nodes.
    const REPULSION = 1800
    const SPRING_K = 0.06
    const DAMPING = 0.82
    const GRAVITY = 0.012

    for (let iter = 0; iter < 120; iter++) {
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

      // Distance-aware spring forces: high weight -> short rest length -> pull together
      for (const edge of edges) {
        const a = pos.get(edge.source)
        const b = pos.get(edge.target)
        if (!a || !b) continue
        const dx = b.x - a.x
        const dy = b.y - a.y
        const dist = Math.sqrt(dx * dx + dy * dy) || 1
        // VOS-style: spring rest length inversely proportional to similarity weight
        const SPRING_LEN = 180 / (edge.weight + 0.1)
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
        // Leave margin for labels below the node
        p.x = Math.max(40, Math.min(width - 40, p.x))
        p.y = Math.max(24, Math.min(height - 36, p.y))
      }
    }

    // eslint-disable-next-line react-hooks/set-state-in-effect -- computing layout positions synchronously in effect is intentional
    setPositions(new Map(pos))
  }, [nodes, edges, width, height])

  return positions
}

interface GraphCanvasProps {
  graph: KnowledgeGraph
  width: number
  height: number
  gapPaperIds: Set<string>
  selectedId: string | null
  onSelect: (id: string | null) => void
  svgRef: React.RefObject<SVGSVGElement | null>
}

function GraphCanvas({ graph, width, height, gapPaperIds, selectedId, onSelect, svgRef }: GraphCanvasProps) {
  const positions = useForceLayout(graph.nodes, graph.edges, width, height)
  const [hovered, setHovered] = useState<string | null>(null)

  if (!positions.size) {
    return (
      <div className="flex items-center justify-center h-full">
        <Spinner size="md" className="text-violet-500" />
      </div>
    )
  }

  return (
    <svg
      ref={svgRef}
      width={width}
      height={height}
      className="absolute inset-0"
      style={{ background: "#09090b" }}
    >
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
        const isHighlighted =
          selectedId
            ? edge.source === selectedId || edge.target === selectedId
            : hovered
              ? edge.source === hovered || edge.target === hovered
              : true
        const opacity = isHighlighted ? 0.75 : 0.12
        return (
          <line
            key={i}
            x1={src.x}
            y1={src.y}
            x2={tgt.x}
            y2={tgt.y}
            stroke={color}
            strokeWidth={Math.max(0.5, edge.weight * 2.5)}
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
        const isSelected = selectedId === node.id
        const isGap = gapPaperIds.has(node.id)
        const nodeR = isSelected ? 12 : isHovered ? 10 : 7

        return (
          <g
            key={node.id}
            transform={`translate(${pos.x},${pos.y})`}
            onMouseEnter={() => setHovered(node.id)}
            onMouseLeave={() => setHovered(null)}
            onClick={() => onSelect(isSelected ? null : node.id)}
            style={{ cursor: "pointer" }}
          >
            {/* Gap highlight: amber dashed outer ring */}
            {isGap && (
              <circle
                r={nodeR + 5}
                fill="none"
                stroke="#f59e0b"
                strokeWidth={1.5}
                strokeDasharray="3 2"
                strokeOpacity={0.85}
              />
            )}

            {/* Node circle */}
            <circle
              r={nodeR}
              fill={communityColor}
              fillOpacity={0.88}
              stroke={isSelected ? "#fff" : isHovered ? "#d4d4d8" : communityColor}
              strokeWidth={isSelected ? 2.5 : isHovered ? 1.5 : 0.8}
            />

            {/* Always-visible truncated label below the node */}
            <text
              y={nodeR + 11}
              textAnchor="middle"
              fontSize={9}
              fill="#a1a1aa"
              className="pointer-events-none select-none"
              style={{ userSelect: "none" }}
            >
              {truncateTitle(node.title)}
            </text>

            {/* Hover tooltip label (larger, above node) */}
            {isHovered && !isSelected && (
              <text
                y={-(nodeR + 5)}
                textAnchor="middle"
                fontSize={10}
                fill="#e4e4e7"
                className="pointer-events-none select-none"
                style={{ userSelect: "none" }}
              >
                {node.title.length > 45 ? node.title.slice(0, 45) + "..." : node.title}
              </text>
            )}
          </g>
        )
      })}
    </svg>
  )
}

interface DetailSidebarProps {
  node: KnowledgeGraphNode
  graph: KnowledgeGraph
  gapPaperIds: Set<string>
  onClose: () => void
}

function DetailSidebar({ node, graph, gapPaperIds, onClose }: DetailSidebarProps) {
  const communityColor = COMMUNITY_COLORS[node.community_id % COMMUNITY_COLORS.length] || "#6b7280"
  const community = graph.communities.find((c) => c.paper_ids.includes(node.id))
  const connectedEdges = graph.edges.filter(
    (e) => e.source === node.id || e.target === node.id,
  )
  const connectedPaperIds = new Set(
    connectedEdges.flatMap((e) => [e.source, e.target]).filter((id) => id !== node.id),
  )
  const connectedPapers = graph.nodes.filter((n) => connectedPaperIds.has(n.id))
  const isGap = gapPaperIds.has(node.id)

  return (
    <div className="border border-zinc-800 rounded-lg bg-zinc-900 p-4 space-y-3 text-sm relative">
      <button
        onClick={onClose}
        className="absolute top-3 right-3 text-zinc-500 hover:text-zinc-200 transition-colors"
        aria-label="Close detail panel"
      >
        <X size={14} />
      </button>

      <div className="flex items-start gap-2 pr-6">
        <span
          className="mt-0.5 flex-shrink-0 w-3 h-3 rounded-full"
          style={{ backgroundColor: communityColor }}
        />
        <div>
          <p className="text-zinc-100 font-medium leading-snug">{node.title}</p>
          <p className="text-zinc-500 text-xs mt-0.5">
            {node.year ? `${node.year}  |  ` : ""}
            {node.study_design}
          </p>
        </div>
      </div>

      {community && (
        <p className="text-violet-400 text-xs">
          Cluster {node.community_id}: {community.label}
        </p>
      )}

      {isGap && (
        <p className="text-amber-400 text-xs font-medium">
          Related to a detected research gap
        </p>
      )}

      {connectedPapers.length > 0 && (
        <div>
          <p className="text-zinc-400 text-xs font-medium mb-1.5">
            Connected papers ({connectedPapers.length})
          </p>
          <ul className="space-y-1">
            {connectedPapers.slice(0, 6).map((p) => {
              const edgeToP = connectedEdges.find(
                (e) => (e.source === p.id || e.target === p.id),
              )
              const color = edgeToP ? (EDGE_COLORS[edgeToP.rel_type] || "#71717a") : "#71717a"
              return (
                <li key={p.id} className="flex items-center gap-1.5 text-xs text-zinc-400">
                  <span className="w-2 h-0.5 rounded-full flex-shrink-0" style={{ backgroundColor: color }} />
                  {p.title.length > 50 ? p.title.slice(0, 50) + "..." : p.title}
                </li>
              )
            })}
            {connectedPapers.length > 6 && (
              <li className="text-xs text-zinc-600">+{connectedPapers.length - 6} more</li>
            )}
          </ul>
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
  const svgRef = useRef<SVGSVGElement | null>(null)
  const [dims, setDims] = useState({ width: 600, height: 400 })
  const [selectedId, setSelectedId] = useState<string | null>(null)

  useEffect(() => {
    if (!containerRef.current) return
    const obs = new ResizeObserver((entries) => {
      const entry = entries[0]
      if (entry) {
        setDims({
          width: Math.floor(entry.contentRect.width),
          height: Math.max(320, Math.floor(entry.contentRect.width * 0.55)),
        })
      }
    })
    obs.observe(containerRef.current)
    return () => obs.disconnect()
  }, [])

  const loadGraph = useCallback(() => {
    setLoading(true)
    setError(null)
    setSelectedId(null)
    fetchKnowledgeGraph(runId)
      .then(setGraph)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false))
  }, [runId])

  // eslint-disable-next-line react-hooks/set-state-in-effect -- loadGraph is a useCallback that triggers data fetching; setState inside is indirect
  useEffect(() => { loadGraph() }, [loadGraph])

  const handleDownloadSvg = useCallback(() => {
    if (!svgRef.current) return
    const serializer = new XMLSerializer()
    const svgStr = serializer.serializeToString(svgRef.current)
    const blob = new Blob([svgStr], { type: "image/svg+xml;charset=utf-8" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = `evidence-network-${runId}.svg`
    a.click()
    URL.revokeObjectURL(url)
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
        <FetchError message={error} onRetry={loadGraph} />
      </div>
    )
  }

  if (!graph || graph.nodes.length === 0) {
    return (
      <EmptyState
        icon={Network}
        heading="No knowledge graph data yet."
        className="py-12"
      />
    )
  }

  const relTypes = [...new Set(graph.edges.map((e) => e.rel_type))]
  const gapPaperIds = new Set(graph.gaps.flatMap((g) => g.related_paper_ids))
  const selectedNode = selectedId ? graph.nodes.find((n) => n.id === selectedId) ?? null : null

  return (
    <div className="space-y-4">
      {/* Stats bar + Download SVG */}
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
        <div className="ml-auto">
          <button
            onClick={handleDownloadSvg}
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded border border-zinc-700 text-xs text-zinc-400 hover:text-zinc-200 hover:border-zinc-500 transition-colors"
            title="Download evidence network as SVG"
          >
            <Download size={12} />
            Download SVG
          </button>
        </div>
      </div>

      {/* Edge type legend */}
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
          {gapPaperIds.size > 0 && (
            <span className="flex items-center gap-1 text-amber-500">
              <span className="inline-block w-3 h-3 rounded-full border border-amber-500 border-dashed" />
              research gap
            </span>
          )}
          <span className="ml-auto text-zinc-600 italic">Click a node for details</span>
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
          <div className="relative" style={{ width: dims.width, height: dims.height }}>
            <GraphCanvas
              graph={graph}
              width={dims.width}
              height={dims.height}
              gapPaperIds={gapPaperIds}
              selectedId={selectedId}
              onSelect={setSelectedId}
              svgRef={svgRef}
            />
          </div>
        )}
      </div>

      {/* Click-to-detail sidebar panel */}
      {selectedNode && (
        <DetailSidebar
          node={selectedNode}
          graph={graph}
          gapPaperIds={gapPaperIds}
          onClose={() => setSelectedId(null)}
        />
      )}

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
              {gap.related_paper_ids.length > 0 && (
                <p className="text-zinc-600 text-xs mt-1">
                  {gap.related_paper_ids.length} related paper(s)
                </p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
