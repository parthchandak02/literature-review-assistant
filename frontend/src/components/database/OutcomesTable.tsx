import { Database } from "lucide-react"
import { EmptyState, FetchError } from "@/components/ui/feedback"
import { GlassTableShell } from "@/components/ui/glass-table-shell"
import { ViewToolbar } from "@/components/ui/view-toolbar"
import { Th, Td } from "@/components/ui/table"
import type { ExtractedOutcomePaper } from "@/lib/api"

export interface OutcomesTableProps {
  outcomePapers: ExtractedOutcomePaper[]
  error: string | null
  onRetry: () => void
}

export function OutcomesTable({ outcomePapers, error, onRetry }: OutcomesTableProps) {
  const flattenedOutcomes = outcomePapers.flatMap((paper) =>
    paper.outcomes.map((outcome, idx) => ({
      key: `${paper.paper_id}-${idx}-${String(outcome.name ?? "outcome")}`,
      paperTitle: paper.title,
      source: paper.extraction_source,
      name: typeof outcome.name === "string" ? outcome.name : "Outcome",
      effect: outcome.effect_size,
      ci:
        outcome.ci_lower != null && outcome.ci_upper != null
          ? `${outcome.ci_lower} to ${outcome.ci_upper}`
          : null,
      pValue: outcome.p_value,
      n: outcome.n,
    })),
  )

  return (
    <GlassTableShell>
      <ViewToolbar
        bordered
        className="!h-auto py-3"
        title={
          <div>
            <div className="text-sm font-semibold text-foreground">Extracted Outcomes</div>
            <div className="text-xs text-muted">
              Deterministic table extraction results from included studies.
            </div>
          </div>
        }
        actions={
          <span className="text-xs text-muted tabular-nums">
            {flattenedOutcomes.length.toLocaleString()} outcome rows
          </span>
        }
      />
      {error ? (
        <div className="p-4">
          <FetchError message={error} onRetry={onRetry} />
        </div>
      ) : flattenedOutcomes.length === 0 ? (
        <EmptyState icon={Database} heading="No extracted outcomes yet." className="py-10" />
      ) : (
        <div className="data-surface overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="glass-table-head border-b border-border/70">
                <Th>Paper</Th>
                <Th>Outcome</Th>
                <Th>Effect Size</Th>
                <Th>CI</Th>
                <Th>P Value</Th>
                <Th>N</Th>
                <Th>Source</Th>
              </tr>
            </thead>
            <tbody>
              {flattenedOutcomes.slice(0, 200).map((row) => (
                <tr key={row.key} className="border-b border-border/80">
                  <Td className="max-w-[28rem] truncate">
                    <span title={row.paperTitle}>{row.paperTitle}</span>
                  </Td>
                  <Td>{row.name}</Td>
                  <Td>{row.effect ?? "-"}</Td>
                  <Td>{row.ci ?? "-"}</Td>
                  <Td>{row.pValue ?? "-"}</Td>
                  <Td>{row.n ?? "-"}</Td>
                  <Td>{row.source}</Td>
                </tr>
              ))}
            </tbody>
          </table>
          {flattenedOutcomes.length > 200 && (
            <div className="px-4 py-3 text-xs text-muted border-t border-border/70">
              Showing the first 200 outcome rows.
            </div>
          )}
        </div>
      )}
    </GlassTableShell>
  )
}
