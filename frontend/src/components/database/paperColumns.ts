import type { BadgeVariant } from "@/components/ui/badge"
import type { PaperAllRow } from "@/lib/api/db"

/**
 * Crossref display guidelines: DOIs render as https://doi.org/10.xxxx/xxxxx.
 * Falls back to the connector-provided source URL when no DOI is available.
 */
export function paperLink(p: { doi: string | null; url: string | null }): string | null {
  if (p.doi) {
    const raw = p.doi.replace(/^https?:\/\/(dx\.)?doi\.org\//i, "")
    return `https://doi.org/${raw}`
  }
  return p.url ?? null
}

export const PRIMARY_STATUS_VARIANT: Record<string, BadgeVariant> = {
  primary: "success",
  secondary_review: "danger",
  protocol_only: "warning",
}

export type PaperColumnId =
  | "authors"
  | "year"
  | "source"
  | "country"
  | "screening"
  | "confidence"
  | "rob"

export const PAPER_COLUMNS: ReadonlyArray<{ id: PaperColumnId; label: string }> = [
  { id: "authors", label: "Authors" },
  { id: "year", label: "Year" },
  { id: "source", label: "Source" },
  { id: "country", label: "Country" },
  { id: "screening", label: "Screening" },
  { id: "confidence", label: "Confidence" },
  { id: "rob", label: "RoB source" },
]

export type ColumnOverrides = Partial<Record<PaperColumnId, boolean>>

function isBlank(value: unknown): boolean {
  return value == null || (typeof value === "string" && value.trim() === "")
}

const HAS_VALUE: Record<PaperColumnId, (p: PaperAllRow) => boolean> = {
  authors: (p) => !isBlank(p.authors),
  year: (p) => p.year != null,
  source: (p) => !isBlank(p.source_database),
  country: (p) => !isBlank(p.country),
  screening: (p) =>
    !isBlank(p.ta_decision) ||
    !isBlank(p.ft_decision) ||
    (!isBlank(p.primary_study_status) && p.primary_study_status !== "unknown"),
  confidence: (p) => p.extraction_confidence != null,
  rob: (p) => !isBlank(p.assessment_source),
}

/** Columns with no value on any row of the current page. */
export function emptyColumns(papers: PaperAllRow[]): Set<PaperColumnId> {
  const empty = new Set<PaperColumnId>()
  for (const { id } of PAPER_COLUMNS) {
    if (!papers.some(HAS_VALUE[id])) empty.add(id)
  }
  return empty
}

/** Explicit user choice wins; otherwise a column shows only when it has data on this page. */
export function resolveVisibleColumns(
  papers: PaperAllRow[],
  overrides: ColumnOverrides,
): Set<PaperColumnId> {
  const empty = papers.length > 0 ? emptyColumns(papers) : new Set<PaperColumnId>()
  const visible = new Set<PaperColumnId>()
  for (const { id } of PAPER_COLUMNS) {
    const override = overrides[id]
    if (override ?? !empty.has(id)) visible.add(id)
  }
  return visible
}
