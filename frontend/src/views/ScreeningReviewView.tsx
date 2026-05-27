import { useState, useEffect, useCallback } from "react"
import { CheckCircle, XCircle, HelpCircle, ChevronDown, ChevronUp, Filter } from "lucide-react"
import { cn } from "@/lib/utils"
import { Spinner, FetchError, EmptyState } from "@/components/ui/feedback"
import { fetchScreeningSummary, approveScreening } from "@/lib/api"
import type { ScreenedPaper, ScreeningSummary, ScreeningOverride } from "@/lib/api"

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function DecisionBadge({ decision }: { decision: string }) {
  if (decision === "include") {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-intent-success-subtle text-intent-success border border-intent-success-border">
        <CheckCircle className="h-3 w-3" />
        Include
      </span>
    )
  }
  if (decision === "exclude") {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-intent-danger-subtle text-intent-danger border border-intent-danger-border">
        <XCircle className="h-3 w-3" />
        Exclude
      </span>
    )
  }
  return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-intent-warning-subtle text-intent-warning border border-intent-warning-border">
      <HelpCircle className="h-3 w-3" />
      Uncertain
    </span>
  )
}

function ConfidencePill({ confidence }: { confidence: number | null }) {
  if (confidence == null) return null
  const pct = Math.round(confidence * 100)
  const color =
    pct >= 80 ? "text-intent-success" : pct >= 60 ? "text-intent-warning" : "text-intent-danger"
  return (
    <span className={cn("text-xs font-mono", color)}>
      {pct}% conf.
    </span>
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
      override ? "border-intent-primary-border bg-intent-primary-subtle" : "border-zinc-800 bg-zinc-900/40"
    )}>
      <button
        className="w-full flex items-start gap-3 px-4 py-3 text-left row-hover"
        onClick={() => setExpanded((v) => !v)}
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <DecisionBadge decision={paper.decision} />
            {override && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-intent-primary-subtle text-intent-primary border border-intent-primary-border">
                Override: {override.decision}
              </span>
            )}
            <ConfidencePill confidence={paper.confidence} />
            {paper.year && (
              <span className="text-xs text-zinc-500 font-mono">{paper.year}</span>
            )}
            <span className="text-xs text-zinc-600 font-mono">{paper.source_database}</span>
          </div>
          <p className="text-sm text-zinc-200 font-medium leading-snug line-clamp-2">
            {paper.title || "(no title)"}
          </p>
          {paper.authors && (
            <p className="text-xs text-zinc-500 mt-0.5 line-clamp-1">{paper.authors}</p>
          )}
        </div>
        <div className="shrink-0 text-zinc-600 mt-0.5">
          {expanded ? (
            <ChevronUp className="h-4 w-4" />
          ) : (
            <ChevronDown className="h-4 w-4" />
          )}
        </div>
      </button>

      {expanded && (
        <div className="px-4 pb-4 border-t border-zinc-800 pt-3 space-y-3">
          {paper.reason && (
            <div>
              <p className="text-xs font-semibold text-zinc-400 mb-1">AI Rationale</p>
              <p className="text-sm text-zinc-300 leading-relaxed">{paper.reason}</p>
            </div>
          )}
          {paper.abstract && (
            <div>
              <p className="text-xs font-semibold text-zinc-400 mb-1">Abstract</p>
              <p className="text-sm text-zinc-400 leading-relaxed line-clamp-6">
                {paper.abstract}
              </p>
            </div>
          )}
          {paper.doi && (
            <div>
              <p className="text-xs font-semibold text-zinc-400 mb-1">DOI</p>
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
            <p className="text-xs font-semibold text-zinc-400 mb-1">Stage</p>
            <span className="text-xs text-zinc-500 font-mono">{paper.stage}</span>
          </div>

          {/* Human override controls */}
          <div className="pt-2 border-t border-zinc-800">
            <p className="text-xs font-semibold text-zinc-400 mb-2">Override AI Decision</p>
            <div className="flex items-center gap-2 flex-wrap">
              <button
                onClick={(e) => { e.stopPropagation(); handleOverride("include") }}
                className={cn(
                  "px-2.5 py-1 rounded text-xs font-medium border transition-colors",
                  override?.decision === "include"
                    ? "bg-intent-success border-intent-success-border text-white"
                    : "bg-zinc-800 border-zinc-700 text-zinc-300 hover:border-intent-success-border"
                )}
              >
                Force Include
              </button>
              <button
                onClick={(e) => { e.stopPropagation(); handleOverride("exclude") }}
                className={cn(
                  "px-2.5 py-1 rounded text-xs font-medium border transition-colors",
                  override?.decision === "exclude"
                    ? "bg-intent-danger border-intent-danger-border text-white"
                    : "bg-zinc-800 border-zinc-700 text-zinc-300 hover:border-intent-danger-border"
                )}
              >
                Force Exclude
              </button>
              {override && (
                <button
                  onClick={(e) => { e.stopPropagation(); onOverride(null); setReason("") }}
                  className="px-2.5 py-1 rounded text-xs font-medium border border-zinc-700 bg-zinc-800 text-zinc-400 hover:text-zinc-200"
                >
                  Clear Override
                </button>
              )}
            </div>
            {override && (
              <input
                type="text"
                placeholder="Reason for override (optional)..."
                value={reason}
                onChange={(e) => handleReasonChange(e.target.value)}
                onClick={(e) => e.stopPropagation()}
                className="mt-2 w-full px-2 py-1.5 rounded text-xs bg-zinc-800 border border-zinc-700 text-zinc-300 placeholder-zinc-600 focus:outline-none focus:border-intent-primary-border"
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
        <Spinner size="md" className="text-intent-primary" />
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
          <h2 className="text-base font-semibold text-zinc-200">Human Review Checkpoint</h2>
          <p className="text-sm text-zinc-500 mt-0.5">
            The workflow has paused for human review. Inspect the AI screening decisions below,
            then approve to continue with extraction.
          </p>
        </div>
      </div>

      {/* Stats bar */}
      <div className="flex items-center gap-4 p-3 rounded-lg bg-zinc-900 border border-zinc-800 text-sm">
        <span className="text-zinc-400">
          <span className="text-zinc-200 font-semibold">{summary.total}</span> papers reviewed
        </span>
        <span className="text-zinc-700">|</span>
        <span className="text-zinc-400">
          <span className="text-intent-success font-semibold">{includedCount}</span> include
        </span>
        <span className="text-zinc-700">|</span>
        <span className="text-zinc-400">
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
          <button
            onClick={() => void handleApprove()}
            disabled={approving}
            className={cn(
              "flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition-colors",
              approving
                ? "bg-zinc-800 text-zinc-500 cursor-not-allowed"
                : "bg-intent-warning hover:bg-intent-warning text-white",
            )}
          >
            {approving && <Spinner size="sm" className="text-zinc-400" />}
            {approving ? "Approving..." : "Approve Screening and Resume Extraction"}
          </button>
          {overrides.size > 0 && (
            <span className="text-xs text-intent-primary font-medium">
              {overrides.size} override{overrides.size !== 1 ? "s" : ""} will be sent for active learning
            </span>
          )}
        </div>
      )}

      {/* Filter tabs */}
      <div className="flex items-center gap-1 border-b border-zinc-800 pb-0">
        {(["all", "include", "uncertain"] as const).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={cn(
              "px-3 py-2 text-xs font-medium border-b-2 -mb-px capitalize transition-colors",
              filter === f
                ? "border-intent-primary text-intent-primary"
                : "border-transparent text-zinc-500 hover:text-zinc-300",
            )}
          >
            {f === "all"
              ? `All (${summary.total})`
              : f === "include"
                ? `Include (${includedCount})`
                : `Uncertain (${uncertainCount})`}
          </button>
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
