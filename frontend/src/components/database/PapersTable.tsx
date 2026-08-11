import { AlertTriangle, ExternalLink } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Th, Td } from "@/components/ui/table"
import { cn } from "@/lib/utils"
import type { PaperAllRow } from "@/lib/api"
import { confidenceToVariant, screeningDecisionToVariant } from "@/lib/constants"

/**
 * Resolve the best clickable link for a paper following Crossref DOI display
 * guidelines (https://www.crossref.org/display-guidelines/):
 * DOIs must be displayed as full HTTPS URLs: https://doi.org/10.xxxx/xxxxx
 * Falls back to the connector-provided source URL when no DOI is available.
 */
function paperLink(p: PaperAllRow): string | null {
  if (p.doi) {
    const raw = p.doi.replace(/^https?:\/\/(dx\.)?doi\.org\//i, "")
    return `https://doi.org/${raw}`
  }
  return p.url ?? null
}

export interface PapersTableProps {
  papers: PaperAllRow[]
}

export function PapersTable({ papers }: PapersTableProps) {
  const hasConfidenceData = papers.some((p) => p.extraction_confidence != null)

  return (
    <div className="data-surface overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="glass-table-head border-b border-border/70">
            <Th>Title</Th>
            <Th>Authors</Th>
            <Th>Year</Th>
            <Th>Source</Th>
            <Th>Country</Th>
            <Th>Title/Abstract</Th>
            <Th>Full-Text</Th>
            <Th>Primary Status</Th>
            {hasConfidenceData && <Th>Confidence</Th>}
            <Th>RoB Source</Th>
          </tr>
        </thead>
        <tbody>
          {papers.map((p, i) => (
            <tr
              key={p.paper_id}
              className={cn(
                "glass-table-row border-b border-border/40",
                i === papers.length - 1 && "border-0",
              )}
            >
              <TitleCell paper={p} />
              <Td className="glass-table-cell-muted max-w-[160px]">
                <span className="line-clamp-1">{p.authors}</span>
              </Td>
              <Td className="tabular-nums glass-table-cell-muted">{p.year ?? "--"}</Td>
              <Td className="glass-table-cell-muted">{p.source_database}</Td>
              <Td className="glass-table-cell-muted">{p.country ?? "--"}</Td>
              <DecisionCell value={p.ta_decision} />
              <DecisionCell value={p.ft_decision} />
              <PrimaryStatusCell value={p.primary_study_status} />
              {hasConfidenceData && <ExtractionConfidenceCell value={p.extraction_confidence} />}
              <AssessmentSourceCell value={p.assessment_source} />
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function TitleCell({ paper }: { paper: PaperAllRow }) {
  const href = paperLink(paper)
  return (
    <Td className="max-w-xs">
      {href ? (
        <a
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          className="group flex items-start gap-1"
        >
          <span className="line-clamp-2 text-foreground group-hover:text-foreground group-hover:underline underline-offset-2">
            {paper.title}
          </span>
          <ExternalLink className="h-3 w-3 shrink-0 mt-0.5 text-muted group-hover:text-foreground transition-colors" />
        </a>
      ) : (
        <span className="line-clamp-2 text-foreground">{paper.title}</span>
      )}
    </Td>
  )
}

function PrimaryStatusCell({ value }: { value: string | null }) {
  const normalized = (value ?? "unknown").toLowerCase()
  const color =
    normalized === "primary"
      ? "bg-intent-success-subtle text-intent-success border-intent-success-border"
      : normalized === "secondary_review"
        ? "bg-intent-danger-subtle text-intent-danger border-intent-danger-border"
        : normalized === "protocol_only"
          ? "bg-intent-warning-subtle text-intent-warning border-intent-warning-border"
          : normalized === "non_empirical"
            ? "bg-surface-2 text-foreground border-border"
            : "bg-card/60 text-muted border-border"
  return (
    <Td>
      <span className={cn("inline-block px-1.5 py-0.5 rounded text-[10px] font-medium border", color)}>
        {normalized}
      </span>
    </Td>
  )
}

function DecisionCell({ value }: { value: string | null }) {
  if (!value) {
    return <Td className="text-muted">--</Td>
  }
  return (
    <Td>
      <Badge variant={screeningDecisionToVariant(value)} size="sm" className="capitalize">
        {value}
      </Badge>
    </Td>
  )
}

function ExtractionConfidenceCell({ value }: { value: number | null }) {
  if (value == null) {
    return <Td className="text-muted">--</Td>
  }
  const pct = Math.round(value * 100)
  return (
    <Td>
      <Badge variant={confidenceToVariant(value)} size="sm" className="font-mono">
        {pct}%
      </Badge>
    </Td>
  )
}

function AssessmentSourceCell({ value }: { value: string | null }) {
  if (!value) {
    return <Td className="text-muted">--</Td>
  }
  if (value === "heuristic") {
    return (
      <Td>
        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-intent-warning-subtle text-intent-warning border border-intent-warning-border">
          <AlertTriangle className="h-2.5 w-2.5" />
          heuristic
        </span>
      </Td>
    )
  }
  return (
    <Td>
      <span className="inline-block px-1.5 py-0.5 rounded text-[10px] font-medium bg-surface-2 text-muted border border-border">
        {value}
      </span>
    </Td>
  )
}
