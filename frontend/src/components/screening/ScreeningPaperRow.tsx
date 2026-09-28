import { memo } from "react"
import { ChevronDown, ChevronRight } from "lucide-react"
import { cn } from "@/lib/utils"
import { humanizeStage } from "@/lib/humanize"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import type { ScreeningOverride } from "@/lib/api"
import { ConfidenceMeter, DecisionBadge, OverrideBadge } from "./screeningBadges"
import { ROW_DATA_ATTRIBUTE } from "./screeningKeyboard"
import {
  effectiveDecision,
  humanizeDecidedBy,
  humanizeExclusionReason,
  isHumanDecision,
  screeningRowDomId,
  type HumanDecision,
  type ScreeningRowData,
} from "./screeningModel"

export interface ScreeningPaperRowProps {
  row: ScreeningRowData
  override: ScreeningOverride | null
  focused: boolean
  expanded: boolean
  selected: boolean
  onDecide: (key: string, decision: HumanDecision) => void
  onClearOverride: (key: string) => void
  onReasonChange: (key: string, reason: string) => void
  onToggleExpanded: (key: string) => void
  onToggleSelected: (key: string) => void
  onFocusRow: (key: string) => void
}

export const ScreeningPaperRow = memo(function ScreeningPaperRow({
  row,
  override,
  focused,
  expanded,
  selected,
  onDecide,
  onClearOverride,
  onReasonChange,
  onToggleExpanded,
  onToggleSelected,
  onFocusRow,
}: ScreeningPaperRowProps) {
  const { key, paper, title, authors, abstract, reason } = row
  const rowId = screeningRowDomId(key)
  const detailsId = `${rowId}-details`
  const finalDecision = effectiveDecision(paper.decision, override)
  const innerTab = focused ? 0 : -1
  const displayTitle = title || "(no title)"
  const meta = [paper.year ? String(paper.year) : null, paper.source_database || null].filter(Boolean).join(" · ")

  return (
    <div
      role="row"
      id={rowId}
      {...{ [ROW_DATA_ATTRIBUTE]: "" }}
      tabIndex={focused ? 0 : -1}
      aria-selected={selected}
      aria-label={displayTitle}
      onFocus={() => onFocusRow(key)}
      className={cn(
        "rounded-panel border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        "focus-within:border-border-strong",
        override ? "border-intent-primary-border bg-intent-primary-subtle" : "border-border bg-card/40",
      )}
    >
      <div role="gridcell" className="flex items-start gap-3 px-3 py-2.5">
        <input
          type="checkbox"
          tabIndex={innerTab}
          checked={selected}
          onChange={() => onToggleSelected(key)}
          aria-label={`Select ${displayTitle}`}
          className="mt-1 size-4 shrink-0 accent-intent-primary cursor-pointer"
        />
        <button
          type="button"
          tabIndex={innerTab}
          aria-expanded={expanded}
          aria-controls={detailsId}
          onClick={() => onToggleExpanded(key)}
          className="flex-1 min-w-0 flex items-start gap-1.5 text-left rounded-control focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          {expanded ? (
            <ChevronDown aria-hidden className="size-4 mt-0.5 shrink-0 text-muted" />
          ) : (
            <ChevronRight aria-hidden className="size-4 mt-0.5 shrink-0 text-muted" />
          )}
          <span className="min-w-0">
            <span className={cn("block text-sm font-medium text-foreground leading-snug", !expanded && "line-clamp-2")}>
              {displayTitle}
            </span>
            {(meta || authors) && (
              <span className="block text-xs text-muted mt-0.5 line-clamp-1">
                {[meta, authors].filter(Boolean).join(" · ")}
              </span>
            )}
          </span>
        </button>
        <div className="flex items-center gap-2 shrink-0 flex-wrap justify-end">
          <DecisionBadge decision={paper.decision} prefix={isHumanDecision(paper) ? "Human" : "AI"} />
          {override && <OverrideBadge decision={override.decision} />}
          <ConfidenceMeter confidence={paper.confidence} />
          <div className="flex items-center gap-1" role="group" aria-label="Your decision">
            <Button
              type="button"
              size="xs"
              tabIndex={innerTab}
              variant={finalDecision === "include" ? "success" : "outline"}
              aria-pressed={finalDecision === "include"}
              title="Include (i)"
              onClick={() => onDecide(key, "include")}
            >
              Include
            </Button>
            <Button
              type="button"
              size="xs"
              tabIndex={innerTab}
              variant={finalDecision === "exclude" ? "destructive" : "outline"}
              aria-pressed={finalDecision === "exclude"}
              title="Exclude (e)"
              onClick={() => onDecide(key, "exclude")}
            >
              Exclude
            </Button>
          </div>
        </div>
      </div>

      {expanded && (
        <div role="gridcell" id={detailsId} className="px-4 pb-4 pt-3 ml-7 border-t border-border space-y-3">
          {reason && (
            <section>
              <h4 className="text-xs font-semibold text-muted mb-1">AI reason</h4>
              <p className="text-sm text-foreground leading-relaxed whitespace-pre-line">{reason}</p>
            </section>
          )}
          <section>
            <h4 className="text-xs font-semibold text-muted mb-1">Abstract</h4>
            <p className="text-sm text-foreground leading-relaxed whitespace-pre-line">
              {abstract || "No abstract available."}
            </p>
          </section>
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-xs">
            <dt className="text-muted">Stage</dt>
            <dd className="text-foreground">{humanizeStage(paper.stage) || "Unknown"}</dd>
            {paper.decided_by && (
              <>
                <dt className="text-muted">Decided by</dt>
                <dd className="text-foreground">{humanizeDecidedBy(paper.decided_by)}</dd>
              </>
            )}
            {paper.exclusion_reason && (
              <>
                <dt className="text-muted">Exclusion reason</dt>
                <dd className="text-foreground">{humanizeExclusionReason(paper.exclusion_reason)}</dd>
              </>
            )}
            {paper.doi && (
              <>
                <dt className="text-muted">DOI</dt>
                <dd>
                  <a
                    href={`https://doi.org/${paper.doi}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    tabIndex={innerTab}
                    className="text-intent-primary-text hover:underline font-mono"
                  >
                    {paper.doi}
                  </a>
                </dd>
              </>
            )}
          </dl>
          {override && (
            <div className="flex items-center gap-2 pt-2 border-t border-border">
              <Input
                aria-label="Reason for override"
                placeholder="Reason for override (optional)"
                value={override.reason ?? ""}
                tabIndex={innerTab}
                onChange={(e) => onReasonChange(key, e.target.value)}
                className="h-8 text-xs flex-1"
              />
              <Button
                type="button"
                variant="ghost"
                size="xs"
                tabIndex={innerTab}
                onClick={() => onClearOverride(key)}
              >
                Clear override
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  )
})
