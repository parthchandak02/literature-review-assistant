import type { PaperReference } from "@/lib/api"
import { decodeHtmlEntities, humanizeSource } from "@/lib/humanize"

export interface ReferenceFilters {
  query: string
  fullTextOnly: boolean
}

export function hasFullText(paper: Pick<PaperReference, "has_file" | "file_type">): boolean {
  return paper.has_file && paper.file_type != null
}

function haystack(paper: PaperReference): string {
  return [
    decodeHtmlEntities(paper.title),
    decodeHtmlEntities(paper.authors),
    paper.year != null ? String(paper.year) : "",
    paper.doi ?? "",
    paper.source_database ?? "",
    humanizeSource(paper.source_database),
  ]
    .join(" ")
    .toLowerCase()
}

export function filterReferences<T extends PaperReference>(papers: T[], filters: ReferenceFilters): T[] {
  const terms = filters.query.toLowerCase().split(/\s+/).filter(Boolean)
  return papers.filter((paper) => {
    if (filters.fullTextOnly && !hasFullText(paper)) return false
    if (terms.length === 0) return true
    const text = haystack(paper)
    return terms.every((t) => text.includes(t))
  })
}
