import { useMemo, useState, type ReactNode } from "react"
import { useQuery } from "@tanstack/react-query"
import { ClipboardCheck, Download, FolderOpen } from "lucide-react"
import { Badge, type BadgeVariant } from "@/components/ui/badge"
import { InfoHint } from "@/components/ui/info-hint"
import { Button } from "@/components/ui/button"
import { FetchError } from "@/components/ui/feedback"
import { ResultsBlock } from "@/components/ui/section"
import { Skeleton } from "@/components/ui/skeleton"
import { downloadUrl } from "@/lib/api"
import { humanizeSnake } from "@/lib/humanize"
import { findArtifactPath } from "@/lib/customDiagrams"
import { AUDIT_FINDINGS_ANCHOR } from "@/lib/resultsCategories"
import { useWorkflowValidationSummaryWithChecks } from "@/hooks/useDbCosts"
import {
  AUDIT_KIND_BADGE,
  auditGateCountLine,
  auditGates,
  contractGateCountLine,
  fetchRunManuscriptAudit,
  gateOverviewLine,
  humanizeGateReason,
  splitAuditSummary,
  verdictBadgeVariant,
  type AuditItem,
} from "./auditFindings"
import { QualityStatusBadge } from "./QualityStatusBadge"
import { RESULTS_DOWNLOAD_BTN_CLS } from "./resultsShared"
import { cn } from "@/lib/utils"

const COLLAPSED_COUNT = 8

interface AuditFindingsBlockProps {
  runId: string
  outputs: Record<string, unknown>
  gateFailureReasons?: string[]
  onOpenFiles?: () => void
}

function AuditItemRow({ item }: { item: AuditItem }) {
  return (
    <li className="flex flex-col gap-1 py-2.5">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={AUDIT_KIND_BADGE[item.kind]} size="sm">
          {humanizeSnake(item.severityLabel)}
        </Badge>
        <span className="text-sm font-medium text-foreground">
          {item.gate === "contract" ? item.title : humanizeSnake(item.title) || item.title}
        </span>
        {item.section && <span className="text-2xs text-muted">{item.section}</span>}
      </div>
      {item.detail && <p className="text-xs text-muted leading-relaxed">{item.detail}</p>}
      {item.recommendation && (
        <p className="text-xs text-foreground/80 leading-relaxed">
          <span className="font-medium">Fix: </span>
          {item.recommendation}
        </p>
      )}
    </li>
  )
}

function AuditFallback({
  outputs,
  onOpenFiles,
  message,
}: {
  outputs: Record<string, unknown>
  onOpenFiles?: () => void
  message: string
}) {
  const summaryPath = findArtifactPath(outputs, "run_summary")
  return (
    <div className="rounded-panel border border-dashed border-border bg-surface-1/40 p-4 flex flex-col gap-3">
      <p className="text-sm text-muted">{message}</p>
      <div className="flex flex-wrap items-center gap-2">
        {summaryPath && (
          <Button size="sm" variant="outline" asChild className={RESULTS_DOWNLOAD_BTN_CLS}>
            <a href={downloadUrl(summaryPath)} download>
              <Download className="h-3 w-3" />
              run_summary.json
            </a>
          </Button>
        )}
        {onOpenFiles && (
          <Button type="button" size="xs" variant="ghost" onClick={onOpenFiles}>
            <FolderOpen />
            Open Files
          </Button>
        )}
      </div>
    </div>
  )
}

function GateGroup({
  title,
  hint,
  statusVariant,
  statusLabel,
  countLine,
  items,
  collapseAfter,
}: {
  title: string
  hint?: ReactNode
  statusVariant: BadgeVariant
  statusLabel: string
  countLine: string
  items: AuditItem[]
  collapseAfter?: number
}) {
  const [expanded, setExpanded] = useState(false)
  const limit = collapseAfter ?? items.length
  const visible = expanded ? items : items.slice(0, limit)
  return (
    <section className="flex flex-col gap-1 pt-2" aria-label={title}>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 border-b border-border/60 pb-1.5">
        <h4 className="text-sm font-semibold text-foreground">{title}</h4>
        {hint}
        <QualityStatusBadge variant={statusVariant} label={statusLabel} />
        <span className="text-xs text-muted tabular-nums">{countLine}</span>
      </div>
      {items.length > 0 && (
        <ul className="divide-y divide-border/60">
          {visible.map((item) => (
            <AuditItemRow key={item.id} item={item} />
          ))}
        </ul>
      )}
      {items.length > limit && (
        <Button
          type="button"
          size="xs"
          variant="link"
          className="self-start px-0"
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
        >
          {expanded ? "Show fewer" : `Show all ${items.length} findings`}
        </Button>
      )}
    </section>
  )
}

export function AuditFindingsBlock({ runId, outputs, gateFailureReasons = [], onOpenFiles }: AuditFindingsBlockProps) {
  const query = useQuery({
    queryKey: ["manuscript-audit", runId],
    queryFn: () => fetchRunManuscriptAudit(runId),
    staleTime: 30_000,
  })
  const validationQuery = useWorkflowValidationSummaryWithChecks(query.data?.workflow_id)
  const gates = useMemo(() => auditGates(query.data), [query.data])
  const summary = query.data?.audit_summary ?? null
  const rawReasons = gateFailureReasons.length > 0 ? gateFailureReasons : summary?.gate_failure_reasons ?? []
  const reasons = rawReasons.map(humanizeGateReason)
  const overview = gateOverviewLine(validationQuery.data?.latest_run?.status, gates)

  return (
    <div id={AUDIT_FINDINGS_ANCHOR} className="scroll-mt-4 mb-4 border-b border-border/60 pb-4">
      <ResultsBlock
        icon={ClipboardCheck}
        title="Final manuscript checks"
        actions={
          summary ? (
            <QualityStatusBadge
              variant={verdictBadgeVariant(summary.verdict, summary.status_label === "passed")}
              label={humanizeSnake(summary.verdict)}
            />
          ) : null
        }
      >
        {query.isPending ? (
          <Skeleton className="h-20 w-full" />
        ) : query.isError ? (
          <FetchError
            message={query.error instanceof Error ? query.error.message : "Could not load audit findings"}
            onRetry={() => void query.refetch()}
          />
        ) : !gates ? (
          <AuditFallback
            outputs={outputs}
            onOpenFiles={onOpenFiles}
            message={
              reasons.length > 0
                ? `No audit record was saved for this run. The gate reported: ${reasons.join("; ")}. The run summary in Files has the raw gate output.`
                : "No manuscript audit was recorded for this run. The run summary in Files has the raw gate output."
            }
          />
        ) : (
          <div className="flex flex-col gap-2">
            {overview && <p className="text-sm font-medium text-foreground">{overview}</p>}
            {summary?.summary && <AuditSummaryText text={summary.summary} />}
            <GateGroup
              title="Consistency checks"
              hint={
                <InfoHint label="About consistency checks">
                  Automated consistency checks between the manuscript and the run data.
                </InfoHint>
              }
              statusVariant={gates.contract.passed ? "success" : "danger"}
              statusLabel={gates.contract.passed ? "Passed" : "Failed"}
              countLine={contractGateCountLine(gates.contract)}
              items={gates.contract.items}
            />
            <GateGroup
              title="Manuscript audit"
              statusVariant={verdictBadgeVariant(gates.audit.verdict, gates.audit.passed)}
              statusLabel={humanizeSnake(gates.audit.verdict) || (gates.audit.passed ? "Passed" : "Failed")}
              countLine={auditGateCountLine(gates.audit)}
              items={gates.audit.items}
              collapseAfter={COLLAPSED_COUNT}
            />
          </div>
        )}
      </ResultsBlock>
    </div>
  )
}

function AuditSummaryText({ text }: { text: string }) {
  const [expanded, setExpanded] = useState(false)
  const parts = splitAuditSummary(text)
  return (
    <div className="flex flex-col gap-2 max-w-[68ch]">
      {parts.map((part, i) => (
        <div key={i} className="flex flex-col gap-0.5">
          {part.title && <span className="label-caps text-muted">{part.title}</span>}
          <p className={cn("text-sm text-foreground/90 leading-relaxed", !expanded && "line-clamp-3")}>{part.body}</p>
        </div>
      ))}
      <Button type="button" variant="link" size="xs" className="self-start px-0" onClick={() => setExpanded((v) => !v)} aria-expanded={expanded}>
        {expanded ? "Show less" : "Show full summary"}
      </Button>
    </div>
  )
}
