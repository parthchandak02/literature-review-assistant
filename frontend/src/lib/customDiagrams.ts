/** Helpers for Gemini custom research diagram artifacts on the Results tab. */

const CUSTOM_DIAGRAM_KEY = /^custom_diagram_(\d+)$/i
const CUSTOM_DIAGRAM_FILE = /^fig_custom_(\d+)\.png$/i

const DEFAULT_TITLES: Record<number, string> = {
  1: "Custom architecture diagram",
  2: "Custom methodological flow diagram",
  3: "Custom evidence relationship diagram",
}

export interface CustomDiagramItem {
  index: number
  path: string
  artifactKey: string
}

export interface DiagramBriefEntry {
  diagram_id?: string
  title?: string
}

export interface DiagramGenerationReport {
  results?: unknown[]
  warnings?: string[]
}

export function isArtifactFilePath(val: unknown): val is string {
  if (typeof val !== "string") return false
  const t = val.trim()
  return (
    t.startsWith("runs/") ||
    t.startsWith("data/") ||
    t.startsWith("./") ||
    t.startsWith("/")
  )
}

/** Resolve a run_summary artifacts key to an absolute file path. */
export function findArtifactPath(
  outputs: Record<string, unknown>,
  artifactKey: string,
): string | null {
  const artifacts = outputs.artifacts
  if (artifacts && typeof artifacts === "object" && !Array.isArray(artifacts)) {
    const direct = (artifacts as Record<string, unknown>)[artifactKey]
    if (typeof direct === "string" && isArtifactFilePath(direct)) return direct
  }

  function walk(obj: unknown): string | null {
    if (typeof obj === "string" && isArtifactFilePath(obj)) {
      return null
    }
    if (obj && typeof obj === "object" && !Array.isArray(obj)) {
      for (const [k, v] of Object.entries(obj as Record<string, unknown>)) {
        if (k === artifactKey && typeof v === "string" && isArtifactFilePath(v)) return v
        const nested = walk(v)
        if (nested) return nested
      }
    }
    return null
  }

  return walk(outputs)
}

/** Collect existing fig_custom_XX.png paths (or custom_diagram_XX artifact keys). */
export function collectCustomDiagramItems(
  outputs: Record<string, unknown>,
): CustomDiagramItem[] {
  const byIndex = new Map<number, CustomDiagramItem>()

  function register(index: number, path: string) {
    const artifactKey = `custom_diagram_${String(index).padStart(2, "0")}`
    byIndex.set(index, { index, path, artifactKey })
  }

  function walk(obj: unknown, key = "") {
    if (typeof obj === "string" && isArtifactFilePath(obj)) {
      const name = (obj.split("/").pop() ?? "").toLowerCase()
      const fileMatch = name.match(CUSTOM_DIAGRAM_FILE)
      const keyMatch = key.match(CUSTOM_DIAGRAM_KEY)
      const index = keyMatch
        ? Number.parseInt(keyMatch[1], 10)
        : fileMatch
          ? Number.parseInt(fileMatch[1], 10)
          : null
      if (index != null && name.endsWith(".png")) register(index, obj)
      return
    }
    if (obj && typeof obj === "object" && !Array.isArray(obj)) {
      for (const [k, v] of Object.entries(obj as Record<string, unknown>)) {
        walk(v, key ? `${key}.${k}` : k)
      }
    }
  }

  walk(outputs, "")
  return [...byIndex.values()].sort((a, b) => a.index - b.index)
}

export function customDiagramPipelineTouched(outputs: Record<string, unknown>): boolean {
  return Boolean(
    findArtifactPath(outputs, "diagram_generation_report") ||
    findArtifactPath(outputs, "diagram_brief_pack") ||
    collectCustomDiagramItems(outputs).length > 0,
  )
}

export function titleForCustomDiagram(
  index: number,
  briefs: DiagramBriefEntry[] | null,
): string {
  const fromBrief = briefs?.[index - 1]?.title?.trim()
  if (fromBrief) return fromBrief
  return DEFAULT_TITLES[index] ?? `Custom diagram ${index}`
}

export function parseDiagramBriefPack(raw: string): DiagramBriefEntry[] | null {
  try {
    const parsed = JSON.parse(raw) as { diagrams?: DiagramBriefEntry[] }
    return Array.isArray(parsed.diagrams) ? parsed.diagrams : null
  } catch {
    return null
  }
}

export function parseDiagramGenerationReport(raw: string): DiagramGenerationReport | null {
  try {
    return JSON.parse(raw) as DiagramGenerationReport
  } catch {
    return null
  }
}
