import { Filter } from "lucide-react"
import { EmptyState } from "@/components/ui/feedback"
import type { ScreenedPaper, ScreeningOverride } from "@/lib/api"
import { ScreeningPaperRow } from "./ScreeningPaperRow"

export interface ScreeningPaperListProps {
  papers: ScreenedPaper[]
  overrides: Map<string, ScreeningOverride>
  onOverride: (paperId: string, override: ScreeningOverride | null) => void
}

export function ScreeningPaperList({ papers, overrides, onOverride }: ScreeningPaperListProps) {
  if (papers.length === 0) {
    return (
      <EmptyState icon={Filter} heading="No papers match this filter." className="py-8" />
    )
  }

  return (
    <div className="space-y-2">
      {papers.map((paper) => (
        <ScreeningPaperRow
          key={`${paper.paper_id}-${paper.stage}`}
          paper={paper}
          override={overrides.get(paper.paper_id) ?? null}
          onOverride={(ov) => onOverride(paper.paper_id, ov)}
        />
      ))}
    </div>
  )
}
