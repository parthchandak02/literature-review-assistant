import { memo } from "react"
import { ChevronDown, ChevronRight } from "lucide-react"
import { cn } from "@/lib/utils"
import { humanizeSource, humanizeStage } from "@/lib/humanize"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import type { ScreeningOverride } from "@/lib/api"
import {
  AutomationBadge,
  ConfidenceMeter,
  DecisionBadge,
  DecisionButton,
  OverrideBadge,
  type DecisionSource,
} from "./screeningBadges"
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
  readOnly?: boolean
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
  readOnly = false,
}: ScreeningPaperRowProps) {
  const { key, paper, title, authors, abstract, reason, automationStep } = row
  const rowId = screeningRowDomId(key)
  const detailsId = `${rowId}-details`
  const finalDecision = effectiveDecision(paper.decision, override)
  const decisionSource: DecisionSource = override || isHumanDecision(paper) ? "human" : "ai"
  const innerTab = focused ? 0 : -1
  const displayTitle = title || "(no title)"
  const meta = [paper.year ? String(paper.year) : null, paper.source_database ? humanizeSource(paper.source_database) : null].filter(Boolean).join(" · ")

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
      <div role="gridcell" className="flex flex-wrap sm:flex-nowrap items-start gap-x-3 gap-y-2 px-3 py-2.5">
        {!readOnly && (
          <input
            type="checkbox"
            tabIndex={innerTab}
            checked={selected}
            onChange={() => onToggleSelected(key)}
            aria-label={`Select ${displayTitle}`}
            className="mt-1 size-4 shrink-0 accent-intent-primary cursor-pointer"
          />
        )}
        <button
          type="button"
          tabIndex={innerTab}
          aria-expanded={expanded}
          aria-controls={detailsId}
          onClick={() => onToggleExpanded(key)}
          className="flex-1 min-w-[12rem] flex items-start gap-1.5 text-left rounded-control focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
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
        <div
          className={cn(
            "flex items-center gap-2 shrink-0 flex-wrap w-full sm:w-auto sm:pl-0 sm:justify-end",
            readOnly ? "pl-5" : "pl-7",
          )}
        >
          {automationStep ? (
            <AutomationBadge step={automationStep} />
          ) : (
            <DecisionBadge decision={paper.decision} prefix={isHumanDecision(paper) ? "Human" : "AI"} />
          )}
          {override && <OverrideBadge decision={override.decision} />}
          <ConfidenceMeter confidence={paper.confidence} />
          {!readOnly && (
          <div className="flex items-center gap-1" role="group" aria-label="Your decision">
            <DecisionButton
              decision="include"
              pressed={finalDecision === "include"}
              source={decisionSource}
              tabIndex={innerTab}
              onClick={() => onDecide(key, "include")}
            />
            <DecisionButton
              decision="exclude"
              pressed={finalDecision === "exclude"}
              source={decisionSource}
              tabIndex={innerTab}
              onClick={() => onDecide(key, "exclude")}
            />
          </div>
          )}
        </div>
      </div>

      {expanded && (
        <div role="gridcell" id={detailsId} className={cn("px-4 pb-4 pt-3 border-t border-border space-y-3", readOnly ? "ml-5" : "ml-7")}>
          {reason && (
            <section>
              <h4 className="text-xs font-semibold text-muted mb-1">
                {automationStep ? "Automation reason" : "AI reason"}
              </h4>
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
          {override && !readOnly && (
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
