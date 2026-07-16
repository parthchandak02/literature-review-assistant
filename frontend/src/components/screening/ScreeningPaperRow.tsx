import { useState } from "react"
import { ChevronDown, ChevronUp } from "lucide-react"
import { cn } from "@/lib/utils"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import type { ScreenedPaper, ScreeningOverride } from "@/lib/api"
import { ConfidencePill, DecisionBadge } from "./screeningBadges"

export interface ScreeningPaperRowProps {
  paper: ScreenedPaper
  override: ScreeningOverride | null
  onOverride: (override: ScreeningOverride | null) => void
}

export function ScreeningPaperRow({ paper, override, onOverride }: ScreeningPaperRowProps) {
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
