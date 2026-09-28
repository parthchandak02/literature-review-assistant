import { useMemo, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { ClipboardCheck, Download, FolderOpen } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { FetchError } from "@/components/ui/feedback"
import { ResultsBlock } from "@/components/ui/section"
import { Skeleton } from "@/components/ui/skeleton"
import { downloadUrl } from "@/lib/api"
import { humanizeSnake } from "@/lib/humanize"
import { findArtifactPath } from "@/lib/customDiagrams"
import { AUDIT_FINDINGS_ANCHOR } from "@/lib/resultsCategories"
import { AUDIT_KIND_BADGE, auditItemsFromPayload, fetchRunManuscriptAudit, splitAuditSummary, type AuditItem } from "./auditFindings"
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
        <span className="text-sm font-medium text-foreground">{humanizeSnake(item.title) || item.title}</span>
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

export function AuditFindingsBlock({ runId, outputs, gateFailureReasons = [], onOpenFiles }: AuditFindingsBlockProps) {
  const [expanded, setExpanded] = useState(false)
  const query = useQuery({
    queryKey: ["manuscript-audit", runId],
    queryFn: () => fetchRunManuscriptAudit(runId),
    staleTime: 30_000,
  })
  const items = useMemo(() => auditItemsFromPayload(query.data), [query.data])
  const summary = query.data?.audit_summary ?? null
  const failures = items.filter((i) => i.kind === "failure").length
  const warnings = items.filter((i) => i.kind === "warning").length
  const reasons = gateFailureReasons.length > 0 ? gateFailureReasons : summary?.gate_failure_reasons ?? []
  const visible = expanded ? items : items.slice(0, COLLAPSED_COUNT)

  return (
    <div id={AUDIT_FINDINGS_ANCHOR} className="scroll-mt-4">
      <ResultsBlock
        icon={ClipboardCheck}
        title="Audit findings"
        actions={
          summary ? (
            <div className="flex items-center gap-1.5">
              {failures > 0 && <Badge variant="danger" size="sm">{failures} failing</Badge>}
              {warnings > 0 && <Badge variant="warning" size="sm">{warnings} warnings</Badge>}
              <Badge variant={summary.status_label === "passed" ? "success" : "neutral"} size="sm">
                {humanizeSnake(summary.verdict)}
              </Badge>
            </div>
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
        ) : !query.data?.latest_run ? (
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
            {summary?.summary && <AuditSummaryText text={summary.summary} />}
            {reasons.length > 0 && (
              <ul className="text-xs text-intent-warning-text list-disc pl-4">
                {reasons.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
            )}
            {items.length === 0 ? (
              <p className="text-sm text-muted">The audit passed with no findings.</p>
            ) : (
              <>
                <ul className="divide-y divide-border/60">
                  {visible.map((item) => (
                    <AuditItemRow key={item.id} item={item} />
                  ))}
                </ul>
                {items.length > COLLAPSED_COUNT && (
                  <Button
                    type="button"
                    size="xs"
                    variant="ghost"
                    className="self-start"
                    onClick={() => setExpanded((v) => !v)}
                    aria-expanded={expanded}
                  >
                    {expanded ? "Show fewer" : `Show all ${items.length} findings`}
                  </Button>
                )}
              </>
            )}
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
