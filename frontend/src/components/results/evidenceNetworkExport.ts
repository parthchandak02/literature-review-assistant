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

type VarMap = Record<string, string>

function selectorParts(selectorText: string): string[] {
  return selectorText.split(",").map((part) => part.replace(/["'\s]/g, ""))
}

const LIGHT_SELECTORS = new Set(["html[data-theme=light]", "[data-theme=light]", ":root[data-theme=light]"])
const BASE_SELECTORS = new Set([":root", "html", ":host"])

function readVars(style: CSSStyleDeclaration, into: VarMap) {
  for (let i = 0; i < style.length; i += 1) {
    const name = style.item(i)
    if (name.startsWith("--")) into[name] = style.getPropertyValue(name).trim()
  }
}

function walkRules(rules: CSSRuleList, base: VarMap, light: VarMap) {
  for (const rule of Array.from(rules)) {
    if ("selectorText" in rule && "style" in rule) {
      const styleRule = rule as CSSStyleRule
      const parts = selectorParts(styleRule.selectorText)
      if (parts.some((p) => LIGHT_SELECTORS.has(p))) readVars(styleRule.style, light)
      else if (parts.some((p) => BASE_SELECTORS.has(p))) readVars(styleRule.style, base)
      continue
    }
    if ("media" in rule && "cssRules" in rule) {
      const media = (rule as CSSMediaRule).media.mediaText
      if (media && typeof matchMedia === "function" && !matchMedia(media).matches) continue
    }
    if ("cssRules" in rule) walkRules((rule as CSSGroupingRule).cssRules, base, light)
  }
}

/**
 * Resolve CSS variables as the light theme defines them, whatever theme is active.
 * Light tokens are scoped to `html[data-theme="light"]`, which a nested element can't match,
 * so they are read from the stylesheets. Unknown names fall back to the live computed value.
 */
export function lightThemeLookup(
  sheets: Iterable<CSSStyleSheet> = typeof document === "undefined" ? [] : Array.from(document.styleSheets),
  fallback: (name: string) => string = (name) =>
    typeof document === "undefined" ? "" : getComputedStyle(document.documentElement).getPropertyValue(name),
): (name: string) => string {
  const base: VarMap = {}
  const light: VarMap = {}
  for (const sheet of sheets) {
    let rules: CSSRuleList
    try {
      rules = sheet.cssRules
    } catch {
      continue
    }
    walkRules(rules, base, light)
  }
  return (name) => light[name] || base[name] || fallback(name)
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
