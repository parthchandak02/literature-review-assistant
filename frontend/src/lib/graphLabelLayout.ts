export interface LabelNode {
  id: string
  x: number
  y: number
  r: number
  width: number
  height: number
}

export interface LabelEdge {
  x1: number
  y1: number
  x2: number
  y2: number
}

export interface LabelPlacement {
  /** Label centre, relative to the node centre. */
  dx: number
  /** Text baseline, relative to the node centre. */
  dy: number
}

interface Box {
  x0: number
  y0: number
  x1: number
  y1: number
}

const GAP = 4

/** Rough width of `text` in px at `fontSize`, good enough for collision checks. */
export function estimateLabelWidth(text: string, fontSize = 10): number {
  return Math.ceil(text.length * fontSize * 0.56) + 4
}

function candidates(n: LabelNode): Box[] {
  const { x, y, r, width: w, height: h } = n
  const below = y + r + GAP
  const above = y - r - GAP - h
  const midY = y - h / 2
  return [
    { x0: x - w / 2, y0: below, x1: x + w / 2, y1: below + h },
    { x0: x - w / 2, y0: above, x1: x + w / 2, y1: above + h },
    { x0: x + r + GAP, y0: midY, x1: x + r + GAP + w, y1: midY + h },
    { x0: x - r - GAP - w, y0: midY, x1: x - r - GAP, y1: midY + h },
    { x0: x + r * 0.7, y0: below - r * 0.3, x1: x + r * 0.7 + w, y1: below - r * 0.3 + h },
    { x0: x - r * 0.7 - w, y0: below - r * 0.3, x1: x - r * 0.7, y1: below - r * 0.3 + h },
    { x0: x + r * 0.7, y0: above + r * 0.3, x1: x + r * 0.7 + w, y1: above + r * 0.3 + h },
    { x0: x - r * 0.7 - w, y0: above + r * 0.3, x1: x - r * 0.7, y1: above + r * 0.3 + h },
    { x0: x - w / 2, y0: below + h + 2, x1: x + w / 2, y1: below + 2 * h + 2 },
    { x0: x - w / 2, y0: above - h - 2, x1: x + w / 2, y1: above - 2 },
  ]
}

function overlapArea(a: Box, b: Box): number {
  const w = Math.min(a.x1, b.x1) - Math.max(a.x0, b.x0)
  const h = Math.min(a.y1, b.y1) - Math.max(a.y0, b.y0)
  return w > 0 && h > 0 ? w * h : 0
}

function circleHitsBox(cx: number, cy: number, r: number, b: Box): boolean {
  const nx = Math.max(b.x0, Math.min(cx, b.x1))
  const ny = Math.max(b.y0, Math.min(cy, b.y1))
  return (cx - nx) ** 2 + (cy - ny) ** 2 < r * r
}

/** Length of the part of edge `e` inside box `b` (Liang-Barsky clipping), 0 when it misses. */
export function edgeLengthInBox(e: LabelEdge, b: Box): number {
  const dx = e.x2 - e.x1
  const dy = e.y2 - e.y1
  let t0 = 0
  let t1 = 1
  const clips: [number, number][] = [
    [-dx, e.x1 - b.x0],
    [dx, b.x1 - e.x1],
    [-dy, e.y1 - b.y0],
    [dy, b.y1 - e.y1],
  ]
  for (const [p, q] of clips) {
    if (p === 0) {
      if (q < 0) return 0
      continue
    }
    const t = q / p
    if (p < 0) t0 = Math.max(t0, t)
    else t1 = Math.min(t1, t)
    if (t0 > t1) return 0
  }
  return (t1 - t0) * Math.hypot(dx, dy)
}

/**
 * Greedy label placement after the force layout: each label takes the
 * candidate slot around its node with the fewest collisions against labels
 * already placed, other nodes, edges and the canvas bounds.
 */
export function placeLabels(
  nodes: LabelNode[],
  edges: LabelEdge[],
  bounds: { width: number; height: number },
): Map<string, LabelPlacement> {
  const placed: Box[] = []
  const out = new Map<string, LabelPlacement>()
  for (const n of nodes) {
    let best: Box | null = null
    let bestScore = Infinity
    candidates(n).forEach((b, i) => {
      let score = i * 0.5
      for (const p of placed) score += overlapArea(b, p) * 4
      for (const m of nodes) {
        if (m.id !== n.id && circleHitsBox(m.x, m.y, m.r + 2, b)) score += 400
      }
      for (const e of edges) {
        const inside = edgeLengthInBox(e, b)
        if (inside > 0) score += 10 + inside * 2
      }
      const outside =
        Math.max(0, -b.x0) + Math.max(0, b.x1 - bounds.width) + Math.max(0, -b.y0) + Math.max(0, b.y1 - bounds.height)
      score += outside * 40
      if (score < bestScore) {
        bestScore = score
        best = b
      }
    })
    const b = best as Box | null
    if (!b) continue
    placed.push(b)
    out.set(n.id, { dx: (b.x0 + b.x1) / 2 - n.x, dy: b.y1 - n.y - 2 })
  }
  return out
}
