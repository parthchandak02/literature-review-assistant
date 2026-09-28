import { useState } from "react"
import { Database } from "lucide-react"
import { EmptyState, FetchError } from "@/components/ui/feedback"
import { GlassTableShell } from "@/components/ui/glass-table-shell"
import { ViewToolbar } from "@/components/ui/view-toolbar"
import { Pagination, Th, Td } from "@/components/ui/table"
import { decodeHtmlEntities } from "@/lib/humanize"
import { cn } from "@/lib/utils"
import type { ExtractedOutcomePaper } from "@/lib/api/db"
import { formatCi, formatPValue, formatStat } from "./outcomeFormat"

export const OUTCOMES_PAGE_SIZE = 50

export interface OutcomesTableProps {
  outcomePapers: ExtractedOutcomePaper[]
  error: string | null
  onRetry: () => void
}

const CELL = "px-2.5 py-2"
const NUM = cn(CELL, "font-mono tabular-nums")

export function OutcomesTable({ outcomePapers, error, onRetry }: OutcomesTableProps) {
  const [page, setPage] = useState(0)
  const rows = outcomePapers.flatMap((paper) =>
    paper.outcomes.map((outcome, idx) => ({
      key: `${paper.paper_id}-${idx}-${String(outcome.name ?? "outcome")}`,
      paperTitle: decodeHtmlEntities(paper.title),
      source: paper.extraction_source,
      name: typeof outcome.name === "string" ? outcome.name : "Outcome",
      effect: formatStat(outcome.effect_size),
      ci: formatCi(outcome.ci_lower, outcome.ci_upper),
      pValue: formatPValue(outcome.p_value),
      n: formatStat(outcome.n),
    })),
  )
  const lastPage = Math.max(0, Math.ceil(rows.length / OUTCOMES_PAGE_SIZE) - 1)
  const safePage = Math.min(page, lastPage)
  const visible = rows.slice(safePage * OUTCOMES_PAGE_SIZE, (safePage + 1) * OUTCOMES_PAGE_SIZE)

  return (
    <GlassTableShell>
      <ViewToolbar
        bordered
        height="auto"
        className="py-3"
        title={
          <div>
            <div className="text-sm font-semibold text-foreground">Extracted outcomes</div>
            <div className="text-xs text-muted">
              Quantitative results from every extracted study. Paper filters above don't apply here.
            </div>
          </div>
        }
        actions={
          <span className="text-xs text-muted tabular-nums">
            {rows.length.toLocaleString()} outcome rows
          </span>
        }
      />
      {error ? (
        <div className="p-4">
          <FetchError message={error} onRetry={onRetry} />
        </div>
      ) : rows.length === 0 ? (
        <EmptyState icon={Database} heading="No extracted outcomes yet." className="py-10" />
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
                {visible.map((row) => (
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
            total={rows.length}
            itemLabel="outcome rows"
            onPrev={() => setPage(Math.max(0, safePage - 1))}
            onNext={() => setPage(Math.min(lastPage, safePage + 1))}
          />
        </>
      )}
    </GlassTableShell>
  )
}
