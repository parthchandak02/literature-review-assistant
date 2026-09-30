import { useRef } from "react"
import { AlertTriangle, ExternalLink } from "lucide-react"
import { edgeFadeMask, useEdgeFadeState } from "@/hooks/useEdgeFade"
import { Badge } from "@/components/ui/badge"
import { InfoHint } from "@/components/ui/info-hint"
import { SortButton, Td, Th } from "@/components/ui/table"
import { cn } from "@/lib/utils"
import { decodeHtmlEntities, humanizeSnake, humanizeSource } from "@/lib/humanize"
import type { PaperAllRow, PapersSort, PapersSortKey } from "@/lib/api/db"
import { automationStepLabel, REMOVED_BY_AUTOMATION, unscreenedOriginLabel } from "@/lib/automationSteps"
import { confidenceToVariant, screeningDecisionToVariant } from "@/lib/constants"
import { PAPER_COLUMNS, PRIMARY_STATUS_VARIANT, paperLink, type PaperColumnId } from "./paperColumns"

const CELL = "px-2.5 py-2"
// Header sort buttons are 20px tall; coarse pointers get a 24px floor.
const STICKY_HEAD = "sticky top-0 z-10 bg-surface-1 border-b border-border-strong pointer-coarse:[&_button]:min-h-6"
// The pinned Title column gets a right edge once rows scroll under it.
const SCROLLED_EDGE =
  "group-data-[scrolled-x=true]/papers:border-r group-data-[scrolled-x=true]/papers:border-r-border-strong group-data-[scrolled-x=true]/papers:shadow-lg"
const STICKY_TITLE = cn("sticky left-0 bg-surface-1", SCROLLED_EDGE)

export interface PapersTableProps {
  papers: PaperAllRow[]
  visibleColumns?: Set<PaperColumnId>
  sort?: PapersSort
  onSort?: (key: PapersSortKey) => void
  onOpenPaper?: (paperId: string) => void
  selectedPaperId?: string | null
}

const ALL_COLUMNS = new Set(PAPER_COLUMNS.map((c) => c.id))

export function PapersTable({
  papers,
  visibleColumns = ALL_COLUMNS,
  sort = { sort: null, dir: "desc" },
  onSort,
  onOpenPaper,
  selectedPaperId,
}: PapersTableProps) {
  const scrollRef = useRef<HTMLDivElement | null>(null)
  const scrollEdges = useEdgeFadeState(scrollRef)
  const dirFor = (key: PapersSortKey) => (sort.sort === key ? sort.dir : null)
  const sortProps = (key: PapersSortKey) =>
    onSort ? { sortable: true, sortDirection: dirFor(key), onSort: () => onSort(key) } : {}
  const show = (id: PaperColumnId) => visibleColumns.has(id)
  const screeningKeys: PapersSortKey[] = ["ta_decision", "ft_decision", "primary_status"]
  const screeningSorted = screeningKeys.some((k) => sort.sort === k)
  const screeningAriaSort = !screeningSorted
    ? "none"
    : sort.dir === "asc"
      ? "ascending"
      : "descending"

  return (
    <div
      ref={scrollRef}
      className="group/papers max-h-[70vh] overflow-auto"
      style={edgeFadeMask({ start: false, end: scrollEdges.end })}
      data-scrolled-x={scrollEdges.start}
      data-overflow-end={scrollEdges.end}
      data-testid="papers-table-scroll"
    >
      <table className="w-full border-separate border-spacing-0 text-xs">
        <thead>
          <tr>
            <Th className={cn(CELL, STICKY_HEAD, "left-0 z-20 min-w-36 sm:min-w-64", SCROLLED_EDGE)} {...sortProps("title")}>
              Title
            </Th>
            {show("authors") && <Th className={cn(CELL, STICKY_HEAD, "min-w-32")}>Authors</Th>}
            {show("year") && (
              <Th className={cn(CELL, STICKY_HEAD)} align="right" {...sortProps("year")}>
                Year
              </Th>
            )}
            {show("source") && (
              <Th className={cn(CELL, STICKY_HEAD)} {...sortProps("source")}>
                Source
              </Th>
            )}
            {show("country") && <Th className={cn(CELL, STICKY_HEAD)}>Country</Th>}
            {show("screening") && (
              <Th
                className={cn(CELL, STICKY_HEAD)}
                ariaSort={onSort ? screeningAriaSort : undefined}
              >
                {onSort ? (
                  <span className="inline-flex items-center gap-2">
                    <ScreeningHeaderLabel />
                    <SortButton direction={dirFor("ta_decision")} onSort={() => onSort("ta_decision")}>
                      <span className="sr-only">Sort by title/abstract decision: </span>TA
                    </SortButton>
                    <SortButton direction={dirFor("ft_decision")} onSort={() => onSort("ft_decision")}>
                      <span className="sr-only">Sort by full-text decision: </span>FT
                    </SortButton>
                    <SortButton
                      direction={dirFor("primary_status")}
                      onSort={() => onSort("primary_status")}
                    >
                      <span className="sr-only">Sort by primary status: </span>Status
                    </SortButton>
                  </span>
                ) : (
                  <ScreeningHeaderLabel />
                )}
              </Th>
            )}
            {show("confidence") && (
              <Th className={cn(CELL, STICKY_HEAD)} align="right" {...sortProps("confidence")}>
                Confidence
              </Th>
            )}
            {show("rob") && <Th className={cn(CELL, STICKY_HEAD)}>RoB source</Th>}
          </tr>
        </thead>
        <tbody>
          {papers.map((p) => {
            const selected = p.paper_id === selectedPaperId
            return (
              <tr
                key={p.paper_id}
                onClick={onOpenPaper ? () => onOpenPaper(p.paper_id) : undefined}
                aria-selected={onOpenPaper ? selected : undefined}
                className={cn(
                  "group glass-table-row [&>td]:border-b [&>td]:border-border/40 last:[&>td]:border-0",
                  onOpenPaper && "cursor-pointer",
                  selected && "[&>td]:bg-intent-primary-subtle",
                )}
              >
                <TitleCell paper={p} onOpen={onOpenPaper} />
                {show("authors") && <TextCell value={decodeHtmlEntities(p.authors)} className="min-w-32 max-w-48" />}
                {show("year") && (
                  <Td align="right" className={cn(CELL, "font-mono tabular-nums glass-table-cell-muted")}>
                    {p.year ?? "--"}
                  </Td>
                )}
                {show("source") && <TextCell value={humanizeSource(p.source_database)} />}
                {show("country") && <TextCell value={p.country} />}
                {show("screening") && <ScreeningCell paper={p} />}
                {show("confidence") && <ExtractionConfidenceCell value={p.extraction_confidence} />}
                {show("rob") && <AssessmentSourceCell value={p.assessment_source} />}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function TextCell({ value, className }: { value: string | null | undefined; className?: string }) {
  if (!value) return <Td className={cn(CELL, "text-muted")}>--</Td>
  return (
    <Td className={cn(CELL, "glass-table-cell-muted", className)}>
      <span className="line-clamp-1" title={value}>
        {value}
      </span>
    </Td>
  )
}

function TitleCell({ paper, onOpen }: { paper: PaperAllRow; onOpen?: (id: string) => void }) {
  const href = paperLink(paper)
  const title = decodeHtmlEntities(paper.title)
  return (
    <Td className={cn(CELL, STICKY_TITLE, "z-[5] max-w-sm min-w-36 sm:min-w-64 group-hover:bg-surface-2")}>
      {/* Table cells ignore max-width, so the phone cap lives on the content box. */}
      <div className="flex items-start gap-1 max-sm:w-32">
        {onOpen ? (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation()
              onOpen(paper.paper_id)
            }}
            title={title}
            className="line-clamp-2 rounded-control text-left text-foreground hover:underline underline-offset-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            {title}
          </button>
        ) : (
          <span className="line-clamp-2 text-foreground" title={title}>
            {title}
          </span>
        )}
        {href && (
          <a
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            onClick={(e) => e.stopPropagation()}
            aria-label="Open publisher page"
            title={href}
            className="mt-0.5 shrink-0 rounded-control text-muted pointer-coarse:-mx-1.5 pointer-coarse:-mb-1.5 pointer-coarse:-mt-1 pointer-coarse:p-1.5 transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <ExternalLink className="h-3 w-3" />
          </a>
        )}
      </div>
    </Td>
  )
}

function ScreeningHeaderLabel() {
  return (
    <span className="inline-flex items-center gap-1">
      Screening
      <InfoHint label="Screening abbreviations">TA = title/abstract, FT = full text.</InfoHint>
    </span>
  )
}

function ScreeningCell({ paper }: { paper: PaperAllRow }) {
  const status = (paper.primary_study_status ?? "unknown").toLowerCase()
  const stages: Array<{ label: string; value: string | null }> = [
    { label: "TA", value: paper.ta_decision },
    { label: "FT", value: paper.ft_decision },
  ]
  return (
    <Td className={CELL}>
      <div className="flex flex-wrap items-center gap-1 [&>*]:whitespace-nowrap">
        {stages.map(({ label, value }) =>
          value === REMOVED_BY_AUTOMATION ? (
            <Badge
              key={label}
              variant="neutral"
              size="sm"
              title={
                paper.automation_step
                  ? `Removed by automation: ${automationStepLabel(paper.automation_step)}`
                  : "Removed by automation"
              }
            >
              <span className="font-mono opacity-70">{label}</span>
              Auto-removed
            </Badge>
          ) : unscreenedOriginLabel(value) ? (
            <Badge key={label} variant="neutral" size="sm" title="Not screened: removed before screening">
              <span className="font-mono opacity-70">{label}</span>
              {unscreenedOriginLabel(value)}
            </Badge>
          ) : value ? (
            <Badge key={label} variant={screeningDecisionToVariant(value)} size="sm">
              <span className="font-mono opacity-70">{label}</span>
              {humanizeSnake(value)}
            </Badge>
          ) : null,
        )}
        {status !== "unknown" && (
          <Badge variant={PRIMARY_STATUS_VARIANT[status] ?? "neutral"} size="sm">
            {humanizeSnake(status)}
          </Badge>
        )}
        {!paper.ta_decision && !paper.ft_decision && status === "unknown" && (
          <span className="text-muted">Not screened</span>
        )}
      </div>
    </Td>
  )
}

function ExtractionConfidenceCell({ value }: { value: number | null }) {
  if (value == null) {
    return (
      <Td align="right" className={cn(CELL, "text-muted")}>
        --
      </Td>
    )
  }
  return (
    <Td align="right" className={CELL}>
      <Badge variant={confidenceToVariant(value)} size="sm" className="font-mono tabular-nums">
        {Math.round(value * 100)}%
      </Badge>
    </Td>
  )
}

function AssessmentSourceCell({ value }: { value: string | null }) {
  if (!value) return <Td className={cn(CELL, "text-muted")}>--</Td>
  const heuristic = value === "heuristic"
  return (
    <Td className={CELL}>
      <Badge variant={heuristic ? "warning" : "neutral"} size="sm">
        {heuristic && <AlertTriangle />}
        {humanizeSnake(value)}
      </Badge>
    </Td>
  )
}
