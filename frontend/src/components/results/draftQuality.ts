import { apiFetch } from "@/lib/api"

export interface TemplateTextMatch {
  id: string
  label: string
  excerpt: string
}

interface TemplatePattern {
  id: string
  label: string
  re: RegExp
}

const TEMPLATE_PATTERNS: TemplatePattern[] = [
  {
    id: "configured-protocol",
    label: "Generic methods boilerplate",
    re: /using the configured protocol(?: and settings)?/i,
  },
  { id: "for-the-topic", label: "Topic placeholder", re: /\bfor the topic\b/i },
  {
    id: "synthesis-generated",
    label: "Pipeline wording in the text",
    re: /evidence synthesis was generated from/i,
  },
  { id: "question-period", label: "Question pasted into a sentence", re: /\?\.(?=\s|$|["'”)\]])/ },
  {
    id: "inline-question",
    label: "Question pasted into a sentence",
    re: /\b(?:evaluated|examined|investigated|assessed|explored|addressed)\s+(?:What|How|Which|Does|Do|Is|Are|Can|Should)\s/,
  },
  {
    id: "placeholder-token",
    label: "Unfilled placeholder",
    re: /\[(?:TBD|TODO|TK|INSERT[^\]]*|PLACEHOLDER[^\]]*)\]|\{\{[^}]+\}\}|\blorem ipsum\b/i,
  },
]

function excerptAround(text: string, index: number, length: number, radius = 40): string {
  const start = Math.max(0, index - radius)
  const end = Math.min(text.length, index + length + radius)
  const body = text.slice(start, end).replace(/\s+/g, " ").trim()
  return `${start > 0 ? "…" : ""}${body}${end < text.length ? "…" : ""}`
}

function stripCode(markdown: string): string {
  return markdown.replace(/```[\s\S]*?```/g, " ").replace(/`[^`\n]*`/g, " ")
}

export function detectTemplateText(markdown: string | null | undefined): TemplateTextMatch[] {
  if (!markdown) return []
  const text = stripCode(markdown)
  const matches: TemplateTextMatch[] = []
  const seenLabels = new Set<string>()
  for (const { id, label, re } of TEMPLATE_PATTERNS) {
    const m = re.exec(text)
    if (!m || seenLabels.has(label)) continue
    seenLabels.add(label)
    matches.push({ id, label, excerpt: excerptAround(text, m.index, m[0].length) })
  }
  return matches
}

const FRONT_MATTER = "Title"

function headingText(raw: string): string {
  return raw.replace(/\s+#+\s*$/, "").replace(/[*_`]/g, "").trim()
}

/** Top-level (`##`) sections that contain template text; text before the first `##` counts as "Title". */
export function detectTemplateSections(markdown: string | null | undefined): string[] {
  if (!markdown) return []
  const sections: Array<{ title: string; lines: string[] }> = [{ title: FRONT_MATTER, lines: [] }]
  let inFence = false
  for (const line of markdown.split("\n")) {
    if (/^\s*```/.test(line)) inFence = !inFence
    const heading = inFence ? null : /^##\s+(.+)$/.exec(line)
    if (heading) {
      sections.push({ title: headingText(heading[1]) || "Untitled section", lines: [] })
      continue
    }
    sections[sections.length - 1].lines.push(line)
  }
  const flagged: string[] = []
  for (const { title, lines } of sections) {
    if (!flagged.includes(title) && detectTemplateText(lines.join("\n")).length > 0) flagged.push(title)
  }
  return flagged
}

export function templateTextWarning(sections: string[]): string {
  return `The manuscript still contains template text in: ${sections.join(", ")}. Package anyway?`
}

/** Sections of the run's current manuscript that still contain template text. Empty when it can't be loaded. */
export async function fetchManuscriptTemplateSections(runId: string): Promise<string[]> {
  try {
    const res = await apiFetch<{ content?: string }>(`/run/${encodeURIComponent(runId)}/manuscript`)
    return detectTemplateSections(res?.content)
  } catch {
    return []
  }
}
