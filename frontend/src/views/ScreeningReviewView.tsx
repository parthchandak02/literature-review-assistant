import { useState, useEffect, useCallback } from "react"
import { CheckCircle, XCircle, HelpCircle, ChevronDown, ChevronUp, Filter } from "lucide-react"
import { cn } from "@/lib/utils"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Spinner, FetchError, EmptyState } from "@/components/ui/feedback"
import { fetchScreeningSummary, approveScreening } from "@/lib/api"
import type { ScreenedPaper, ScreeningSummary, ScreeningOverride } from "@/lib/api"
import { confidenceToVariant, screeningDecisionToVariant } from "@/lib/constants"

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function DecisionBadge({ decision }: { decision: string }) {
  const variant = screeningDecisionToVariant(decision)
  if (decision === "include") {
    return (
      <Badge variant={variant}>
        <CheckCircle className="h-3 w-3" />
        Include
      </Badge>
    )
  }
  if (decision === "exclude") {
    return (
      <Badge variant={variant}>
        <XCircle className="h-3 w-3" />
        Exclude
      </Badge>
    )
  }
  return (
    <Badge variant={variant}>
      <HelpCircle className="h-3 w-3" />
      Uncertain
    </Badge>
  )
}

function ConfidencePill({ confidence }: { confidence: number | null }) {
  if (confidence == null) return null
  const pct = Math.round(confidence * 100)
  return (
    <Badge variant={confidenceToVariant(confidence)} size="sm" className="font-mono">
      {pct}% conf.
    </Badge>
  )
}

interface PaperRowProps {
  paper: ScreenedPaper
  override: ScreeningOverride | null
  onOverride: (override: ScreeningOverride | null) => void
}

function PaperRow({ paper, override, onOverride }: PaperRowProps) {
  const [expanded, setExpanded] = useState(false)
  const [reason, setReason] = useState("")

  const handleOverride = (decision: "include" | "exclude") => {
    if (override?.decision === decision) {
      onOverride(null)
    } else {
      onOverride({ paper_id: paper.paper_id, decision, reason: reason || undefined })
    }
  }

  const handleReasonChange = (val: string) => {
    setReason(val)
    if (override) {
      onOverride({ ...override, reason: val || undefined })
    }
  }

  return (
    <div className={cn(
      "border rounded-lg overflow-hidden",
      override ? "border-intent-primary-border bg-intent-primary-subtle" : "border-border bg-card/40"
    )}>
      <button
        className="w-full flex items-start gap-3 px-4 py-3 text-left row-hover"
        onClick={() => setExpanded((v) => !v)}
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <DecisionBadge decision={paper.decision} />
            {override && (
              <Badge variant="primary">
                Override: {override.decision}
              </Badge>
            )}
            <ConfidencePill confidence={paper.confidence} />
            {paper.year && (
              <span className="text-xs text-muted font-mono">{paper.year}</span>
            )}
            <span className="text-xs text-muted font-mono">{paper.source_database}</span>
          </div>
          <p className="text-sm text-foreground font-medium leading-snug line-clamp-2">
            {paper.title || "(no title)"}
          </p>
          {paper.authors && (
            <p className="text-xs text-muted mt-0.5 line-clamp-1">{paper.authors}</p>
          )}
        </div>
        <div className="shrink-0 text-muted mt-0.5">
          {expanded ? (
            <ChevronUp className="h-4 w-4" />
          ) : (
            <ChevronDown className="h-4 w-4" />
          )}
        </div>
      </button>

      {expanded && (
        <div className="px-4 pb-4 border-t border-border pt-3 space-y-3">
          {paper.reason && (
            <div>
              <p className="text-xs font-semibold text-muted mb-1">AI Rationale</p>
              <p className="text-sm text-foreground leading-relaxed">{paper.reason}</p>
            </div>
          )}
          {paper.abstract && (
            <div>
              <p className="text-xs font-semibold text-muted mb-1">Abstract</p>
              <p className="text-sm text-muted leading-relaxed line-clamp-6">
                {paper.abstract}
              </p>
            </div>
          )}
          {paper.doi && (
            <div>
              <p className="text-xs font-semibold text-muted mb-1">DOI</p>
              <a
                href={`https://doi.org/${paper.doi}`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-intent-primary hover:text-intent-primary font-mono"
                onClick={(e) => e.stopPropagation()}
              >
                {paper.doi}
              </a>
            </div>
          )}
          <div>
            <p className="text-xs font-semibold text-muted mb-1">Stage</p>
            <span className="text-xs text-muted font-mono">{paper.stage}</span>
          </div>

          {/* Human override controls */}
          <div className="pt-2 border-t border-border">
            <p className="text-xs font-semibold text-muted mb-2">Override AI Decision</p>
            <div className="flex items-center gap-2 flex-wrap">
              <Button
                onClick={(e) => { e.stopPropagation(); handleOverride("include") }}
                size="sm"
                variant={override?.decision === "include" ? "success" : "outline"}
                className={cn(
                  "h-7 px-2.5 text-xs",
                  override?.decision !== "include" && "hover:border-intent-success-border"
                )}
              >
                Force Include
              </Button>
              <Button
                onClick={(e) => { e.stopPropagation(); handleOverride("exclude") }}
                size="sm"
                variant={override?.decision === "exclude" ? "destructive" : "outline"}
                className={cn(
                  "h-7 px-2.5 text-xs",
                  override?.decision !== "exclude" && "hover:border-intent-danger-border"
                )}
              >
                Force Exclude
              </Button>
              {override && (
                <Button
                  onClick={(e) => { e.stopPropagation(); onOverride(null); setReason("") }}
                  variant="outline"
                  size="sm"
                  className="h-7 px-2.5 text-xs text-muted hover:text-foreground"
                >
                  Clear Override
                </Button>
              )}
            </div>
            {override && (
              <Input
                placeholder="Reason for override (optional)..."
                value={reason}
                onChange={(e) => handleReasonChange(e.target.value)}
                onClick={(e) => e.stopPropagation()}
                className="mt-2 h-8 text-xs bg-surface-2 border-border placeholder:text-muted focus-visible:ring-intent-primary-border"
              />
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// ScreeningReviewView
// ---------------------------------------------------------------------------

export function ScreeningReviewView({ runId }: { runId: string }) {
  const [summary, setSummary] = useState<ScreeningSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [approving, setApproving] = useState(false)
  const [approved, setApproved] = useState(false)
  const [filter, setFilter] = useState<"all" | "include" | "uncertain">("all")
  const [overrides, setOverrides] = useState<Map<string, ScreeningOverride>>(new Map())

  const load = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const data = await fetchScreeningSummary(runId)
      setSummary(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }, [runId])

  useEffect(() => {
    setOverrides(new Map())
    void load()
  }, [load])

  const handleOverride = (paperId: string, override: ScreeningOverride | null) => {
    setOverrides((prev) => {
      const next = new Map(prev)
      if (override === null) {
        next.delete(paperId)
      } else {
        next.set(paperId, override)
      }
      return next
    })
  }

  const handleApprove = async () => {
    if (approving || approved) return
    setApproving(true)
    try {
      const overrideList = Array.from(overrides.values())
      await approveScreening(runId, overrideList.length > 0 ? overrideList : undefined)
      setApproved(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setApproving(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-48">
        <Spinner size="md" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="py-8">
        <FetchError message={error} onRetry={() => void load()} />
      </div>
    )
  }

  if (!summary) return null

  const filtered = summary.papers.filter(
    (p) => filter === "all" || p.decision === filter,
  )

  const includedCount = summary.papers.filter((p) => p.decision === "include").length
  const uncertainCount = summary.papers.filter((p) => p.decision === "uncertain").length

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-base font-semibold text-foreground">Human Review Checkpoint</h2>
          <p className="text-sm text-muted mt-0.5">
            The workflow has paused for human review. Inspect the AI screening decisions below,
            then approve to continue with extraction.
          </p>
        </div>
      </div>

      {/* Stats bar */}
      <div className="flex items-center gap-4 p-3 rounded-lg bg-card border border-border text-sm">
        <span className="text-muted">
          <span className="text-foreground font-semibold">{summary.total}</span> papers reviewed
        </span>
        <span className="text-border">|</span>
        <span className="text-muted">
          <span className="text-intent-success font-semibold">{includedCount}</span> include
        </span>
        <span className="text-border">|</span>
        <span className="text-muted">
          <span className="text-intent-warning font-semibold">{uncertainCount}</span> uncertain
        </span>
      </div>

      {/* Approve button */}
      {approved ? (
        <div className="flex items-center gap-2 p-3 rounded-lg bg-intent-success-subtle border border-intent-success-border text-sm text-intent-success">
          <CheckCircle className="h-4 w-4" />
          Screening approved -- workflow is resuming extraction...
        </div>
      ) : (
        <div className="flex items-center gap-3 flex-wrap">
          <Button
            onClick={() => void handleApprove()}
            disabled={approving}
            variant="warning"
            className={cn(
              "h-10 px-4 rounded-lg text-sm",
              approving && "cursor-not-allowed",
            )}
          >
            {approving && <Spinner size="sm" />}
            {approving ? "Approving..." : "Approve Screening and Resume Extraction"}
          </Button>
          {overrides.size > 0 && (
            <span className="text-xs text-intent-primary font-medium">
              {overrides.size} override{overrides.size !== 1 ? "s" : ""} will be sent for active learning
            </span>
          )}
        </div>
      )}

      {/* Filter tabs */}
      <div className="flex items-center gap-1 border-b border-border pb-0">
        {(["all", "include", "uncertain"] as const).map((f) => (
          <Button
            key={f}
            onClick={() => setFilter(f)}
            variant="ghost"
            size="sm"
            className={cn(
              "px-3 h-8 text-xs font-medium border-b-2 -mb-px capitalize rounded-none",
              filter === f
                ? "border-intent-primary text-intent-primary"
                : "border-transparent text-muted hover:text-foreground",
            )}
          >
            {f === "all"
              ? `All (${summary.total})`
              : f === "include"
                ? `Include (${includedCount})`
                : `Uncertain (${uncertainCount})`}
          </Button>
        ))}
      </div>

      {/* Paper list */}
      {filtered.length === 0 ? (
        <EmptyState icon={Filter} heading="No papers match this filter." className="py-8" />
      ) : (
        <div className="space-y-2">
          {filtered.map((paper) => (
            <PaperRow
              key={`${paper.paper_id}-${paper.stage}`}
              paper={paper}
              override={overrides.get(paper.paper_id) ?? null}
              onOverride={(ov) => handleOverride(paper.paper_id, ov)}
            />
          ))}
        </div>
      )}
    </div>
  )
}
