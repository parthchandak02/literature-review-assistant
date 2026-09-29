import { Database, FilterX } from "lucide-react"
import { EmptyState, FetchError } from "@/components/ui/feedback"
import { GlassTableShell } from "@/components/ui/glass-table-shell"
import { ViewToolbar } from "@/components/ui/view-toolbar"
import { Pagination, Th, Td } from "@/components/ui/table"
import { decodeHtmlEntities, humanizeRetrievalSource } from "@/lib/humanize"
import { cn } from "@/lib/utils"
import type { ExtractedTablesResponse } from "@/lib/api/db"
import { formatCi, formatPValue, formatStat, outcomesCaption } from "./outcomeFormat"

export const OUTCOMES_PAGE_SIZE = 50

export interface OutcomesTableProps {
  data: ExtractedTablesResponse | undefined
  page: number
  onPageChange: (page: number) => void
  /** Papers matching the Data tab filters, or null when no filter is active. */
  filteredPaperCount: number | null
  error: string | null
  onRetry: () => void
}

const CELL = "px-2.5 py-2"
const NUM = cn(CELL, "font-mono tabular-nums")

export function OutcomesTable({
  data,
  page,
  onPageChange,
  filteredPaperCount,
  error,
  onRetry,
}: OutcomesTableProps) {
  const total = data?.total_rows ?? 0
  const rowOffset = data?.offset ?? 0
  const rows = (data?.papers ?? [])
    .flatMap((paper) =>
      paper.outcomes.map((outcome) => ({
        paperTitle: decodeHtmlEntities(paper.title),
        source: humanizeRetrievalSource(paper.extraction_source),
        name: typeof outcome.name === "string" ? outcome.name : "Outcome",
        effect: formatStat(outcome.effect_size),
        ci: formatCi(outcome.ci_lower, outcome.ci_upper),
        pValue: formatPValue(outcome.p_value),
        n: formatStat(outcome.n),
        paperId: paper.paper_id,
      })),
    )
    .map((row, idx) => ({ ...row, key: `${rowOffset + idx}-${row.paperId}` }))
  const lastPage = Math.max(0, Math.ceil(total / OUTCOMES_PAGE_SIZE) - 1)
  const safePage = Math.min(page, lastPage)
  const filtered = filteredPaperCount != null

  return (
    <GlassTableShell>
      <ViewToolbar
        bordered
        height="auto"
        className="py-3"
        title={
          <div>
            <div className="text-sm font-semibold text-foreground">Extracted outcomes</div>
            <div className="text-xs text-muted">{outcomesCaption(filteredPaperCount)}</div>
          </div>
        }
        actions={
          <span className="text-xs text-muted tabular-nums">
            {total.toLocaleString()} outcome {total === 1 ? "row" : "rows"}
          </span>
        }
      />
      {error ? (
        <div className="p-4">
          <FetchError message={error} onRetry={onRetry} />
        </div>
      ) : total === 0 ? (
        filtered ? (
          <EmptyState icon={FilterX} heading="No extracted outcomes for the filtered papers." className="py-10" />
        ) : (
          <EmptyState icon={Database} heading="No extracted outcomes yet." className="py-10" />
        )
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="glass-table-head border-b border-border/70">
                  <Th className={CELL}>Paper</Th>
                  <Th className={CELL}>Outcome</Th>
                  <Th className={CELL} align="right">Effect size</Th>
                  <Th className={CELL} align="right">95% CI</Th>
                  <Th className={CELL} align="right">p</Th>
                  <Th className={CELL} align="right">N</Th>
                  <Th className={CELL}>Source</Th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.key} className="glass-table-row border-b border-border/40 last:border-0">
                    <Td className={cn(CELL, "max-w-md")}>
                      <span className="line-clamp-1" title={row.paperTitle}>
                        {row.paperTitle}
                      </span>
                    </Td>
                    <Td className={cn(CELL, "max-w-56")}>
                      <span className="line-clamp-1" title={row.name}>
                        {row.name}
                      </span>
                    </Td>
                    <Td className={NUM} align="right">{row.effect}</Td>
                    <Td className={cn(NUM, "whitespace-nowrap")} align="right">{row.ci}</Td>
                    <Td className={NUM} align="right">{row.pValue}</Td>
                    <Td className={NUM} align="right">{row.n}</Td>
                    <Td className={cn(CELL, "glass-table-cell-muted")}>{row.source}</Td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination
            className="border-t border-border/70 px-3 py-2"
            page={safePage}
            pageSize={OUTCOMES_PAGE_SIZE}
            total={total}
            itemLabel="outcome rows"
            onPrev={() => onPageChange(Math.max(0, safePage - 1))}
            onNext={() => onPageChange(Math.min(lastPage, safePage + 1))}
          />
        </>
      )}
    </GlassTableShell>
  )
}
