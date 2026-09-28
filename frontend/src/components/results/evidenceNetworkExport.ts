const COMMUNITY_COLOR_COUNT = 10

export function communityColor(communityId: number): string {
  const index = ((communityId % COMMUNITY_COLOR_COUNT) + COMMUNITY_COLOR_COUNT) % COMMUNITY_COLOR_COUNT
  return `var(--color-graph-community-${index})`
}

const VAR_RE = /var\(\s*(--[\w-]+)\s*(?:,\s*([^()]*(?:\([^()]*\))?[^()]*))?\)/g

export function inlineCssVars(value: string, lookup: (name: string) => string): string {
  let current = value
  for (let pass = 0; pass < 4 && current.includes("var("); pass += 1) {
    current = current.replace(VAR_RE, (_match, name: string, fallback?: string) => {
      const resolved = lookup(name).trim()
      return resolved || (fallback ?? "").trim()
    })
  }
  return current
}

const COLOR_ATTRS = ["fill", "stroke", "stop-color", "flood-color", "lighting-color"]

export function prepareSvgForExport(
  svg: SVGSVGElement,
  lookup: (name: string) => string = (name) =>
    getComputedStyle(document.documentElement).getPropertyValue(name),
): SVGSVGElement {
  const clone = svg.cloneNode(true) as SVGSVGElement
  clone.setAttribute("xmlns", "http://www.w3.org/2000/svg")
  clone.removeAttribute("class")
  const elements = [clone, ...Array.from(clone.querySelectorAll<SVGElement>("*"))]
  for (const el of elements) {
    for (const attr of COLOR_ATTRS) {
      const v = el.getAttribute(attr)
      if (v && v.includes("var(")) el.setAttribute(attr, inlineCssVars(v, lookup))
    }
    const style = el.getAttribute("style")
    if (style && style.includes("var(")) el.setAttribute("style", inlineCssVars(style, lookup))
    el.removeAttribute("tabindex")
  }
  const fontFamily = getComputedStyle(svg).fontFamily
  if (fontFamily) clone.setAttribute("font-family", fontFamily)
  return clone
}
