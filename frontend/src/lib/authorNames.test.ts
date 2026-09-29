import { describe, expect, it } from "vitest"
import { familyName } from "./authorNames"
import { edgeLengthInBox, estimateLabelWidth, placeLabels } from "./graphLabelLayout"

describe("familyName", () => {
  it.each([
    ["Jennifer K. Roth", "Roth"],
    ["J. K. Roth", "Roth"],
    ["Roth, Jennifer K.", "Roth"],
    ["Roth J.", "Roth"],
    ["Roth JK", "Roth"],
    ["Yu, Jennifer", "Yu"],
    ["Zeng, Ziwei", "Zeng"],
    ["van der Berg, Anna", "van der Berg"],
    ["Anna van der Berg", "van der Berg"],
    ["Dr. John Smith Jr.", "Smith"],
    ["Nguyen Van An", "Nguyen"],
    ["Nguyễn Thị Lan", "Nguyễn"],
    ["彭淑敏", "彭淑敏"],
    ["彭 淑敏", "彭"],
    ["Roth", "Roth"],
    ["", ""],
  ])("%s -> %s", (input, expected) => {
    expect(familyName(input)).toBe(expected)
  })

  it("handles null", () => {
    expect(familyName(null)).toBe("")
  })
})

describe("placeLabels", () => {
  const node = (id: string, x: number, y: number, text = "Roth et al. (2025)") => ({
    id,
    x,
    y,
    r: 7,
    width: estimateLabelWidth(text),
    height: 13,
  })

  it("keeps the default below-node slot when nothing collides", () => {
    const out = placeLabels([node("a", 200, 100)], [], { width: 400, height: 300 })
    const p = out.get("a")!
    expect(p.dx).toBe(0)
    expect(p.dy).toBeGreaterThan(7)
  })

  it("moves a label off a node sitting directly below", () => {
    const out = placeLabels([node("a", 200, 100), node("b", 200, 118)], [], { width: 400, height: 300 })
    const p = out.get("a")!
    expect(p.dy < 0 || p.dx !== 0).toBe(true)
  })

  it("separates two labels that would overlap", () => {
    const nodes = [node("a", 200, 100), node("b", 230, 100)]
    const out = placeLabels(nodes, [], { width: 400, height: 300 })
    const a = out.get("a")!
    const b = out.get("b")!
    const sameRow = Math.abs(a.dy - b.dy) < 13
    const ax = 200 + a.dx
    const bx = 230 + b.dx
    const apart = Math.abs(ax - bx) >= (nodes[0].width + nodes[1].width) / 2
    expect(!sameRow || apart).toBe(true)
  })

  it("avoids a horizontal edge running under the node", () => {
    const out = placeLabels(
      [node("a", 200, 100)],
      [{ x1: 100, y1: 118, x2: 300, y2: 118 }],
      { width: 400, height: 300 },
    )
    expect(out.get("a")!.dy).toBeLessThan(0)
  })

  it("keeps labels inside the canvas", () => {
    const out = placeLabels([node("a", 200, 292)], [], { width: 400, height: 300 })
    expect(out.get("a")!.dy).toBeLessThan(0)
  })
})

describe("edgeLengthInBox", () => {
  const box = { x0: 0, y0: 0, x1: 10, y1: 10 }
  it("measures the clipped segment", () => {
    expect(edgeLengthInBox({ x1: -5, y1: 5, x2: 15, y2: 5 }, box)).toBeCloseTo(10)
    expect(edgeLengthInBox({ x1: 2, y1: 2, x2: 4, y2: 2 }, box)).toBeCloseTo(2)
    expect(edgeLengthInBox({ x1: -5, y1: 20, x2: 15, y2: 20 }, box)).toBe(0)
  })
})
