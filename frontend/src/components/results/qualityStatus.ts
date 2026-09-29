import { AlertTriangle, CheckCircle2, CircleDashed, XCircle } from "lucide-react"
import type { LucideIcon } from "lucide-react"
import type { BadgeVariant } from "@/components/ui/badge"
import { humanizeIdentifier } from "@/lib/humanize"

export interface StatusStyle {
  variant: BadgeVariant
  icon: LucideIcon
}

export function validationStatusStyle(status: string | null | undefined): StatusStyle {
  const s = (status ?? "").toLowerCase()
  if (s === "error" || s === "fail" || s === "failed") return { variant: "danger", icon: XCircle }
  if (s === "warn" || s === "warning") return { variant: "warning", icon: AlertTriangle }
  if (s === "pass" || s === "passed" || s === "ok" || s === "success") return { variant: "success", icon: CheckCircle2 }
  return { variant: "neutral", icon: CircleDashed }
}

const VALIDATION_CHECK_TITLES: Record<string, string> = {
  prisma_arithmetic_valid: "PRISMA counts add up",
  review_facts_cross_artifact: "Counts match across outputs",
  extraction_coverage: "Data extracted for every included study",
  quality_coverage: "Quality appraised for every included study",
  rag_chunk_coverage: "Evidence passages indexed for every included study",
  rag_embedding_validity: "Evidence passages are searchable",
  citation_catalog_integrity: "Every citation resolves to a reference",
  citation_lineage: "Citations trace back to included studies",
  finalize_checkpoint: "Finalize step completed",
  manuscript_audit: "Manuscript audit passed",
  manuscript_contracts: "Manuscript consistency checks passed",
  fallback_events: "No sections used fallback text",
  prisma_checklist: "PRISMA checklist complete",
  submission_pdf_present: "Submission PDF generated",
}

export function validationCheckTitle(name: string): string {
  return VALIDATION_CHECK_TITLES[name.toLowerCase()] ?? humanizeIdentifier(name)
}
