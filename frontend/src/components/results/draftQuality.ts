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
