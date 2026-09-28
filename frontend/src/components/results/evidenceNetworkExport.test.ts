// @vitest-environment jsdom
import { describe, expect, it } from "vitest"
import { communityColor, inlineCssVars, prepareSvgForExport } from "./evidenceNetworkExport"

const vars: Record<string, string> = {
  "--a": " #111111 ",
  "--b": "var(--a)",
}
const lookup = (name: string) => vars[name] ?? ""

describe("inlineCssVars", () => {
  it("resolves nested variables and fallbacks", () => {
    expect(inlineCssVars("var(--a)", lookup)).toBe("#111111")
    expect(inlineCssVars("var(--b)", lookup)).toBe("#111111")
    expect(inlineCssVars("var(--missing, red)", lookup)).toBe("red")
    expect(inlineCssVars("background: var(--a); color: var(--a)", lookup)).toBe("background: #111111; color: #111111")
  })
})

describe("prepareSvgForExport", () => {
  it("inlines colours on a clone and leaves the live SVG alone", () => {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg")
    svg.setAttribute("style", "background: var(--a)")
    const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle")
    circle.setAttribute("fill", "var(--b)")
    circle.setAttribute("stroke", "var(--a)")
    circle.setAttribute("tabindex", "0")
    svg.appendChild(circle)

    const out = prepareSvgForExport(svg, lookup)
    const outCircle = out.querySelector("circle")!
    expect(outCircle.getAttribute("fill")).toBe("#111111")
    expect(outCircle.getAttribute("stroke")).toBe("#111111")
    expect(outCircle.hasAttribute("tabindex")).toBe(false)
    expect(out.getAttribute("style")).toBe("background: #111111")
    expect(circle.getAttribute("fill")).toBe("var(--b)")
  })
})

describe("communityColor", () => {
  it("cycles through ten tokens", () => {
    expect(communityColor(3)).toBe("var(--color-graph-community-3)")
    expect(communityColor(13)).toBe("var(--color-graph-community-3)")
    expect(communityColor(-1)).toBe("var(--color-graph-community-9)")
  })
})
