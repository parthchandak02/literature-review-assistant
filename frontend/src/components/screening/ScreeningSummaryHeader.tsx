import { Lock } from "lucide-react"
import { formatCount } from "@/lib/format"
import { InfoHint } from "@/components/ui/info-hint"
import { ViewToolbar } from "@/components/ui/view-toolbar"
import type { ScreeningThresholds } from "@/lib/api"
import type { AutomationBreakdownEntry } from "@/lib/automationSteps"
import { thresholdsText, UNCERTAIN_OUTCOME, type DecisionCounts } from "./screeningModel"

function reviewerDecisionLine(counts: DecisionCounts): string {
  return [
    `${formatCount(counts.include)} include`,
    counts.excludeFulltext + counts.notRetrieved > 0
      ? `${formatCount(counts.exclude)} exclude (${[
          `${formatCount(counts.exclude - counts.excludeFulltext - counts.notRetrieved)} title/abstract`,
          counts.notRetrieved > 0 ? `${formatCount(counts.notRetrieved)} full text not retrieved` : null,
          counts.excludeFulltext > 0 ? `${formatCount(counts.excludeFulltext)} full text` : null,
        ]
          .filter(Boolean)
          .join(", ")})`
      : `${formatCount(counts.exclude)} exclude`,
    `${formatCount(counts.uncertain)} uncertain`,
    `${formatCount(counts.overridden)} overridden`,
  ].join(" · ")
}

export interface ScreeningSummaryHeaderProps {
  counts: DecisionCounts
  reviewedCount: number
  automation?: readonly AutomationBreakdownEntry[]
  thresholds?: ScreeningThresholds | null
  readOnly?: boolean
}

export const SCREENING_READ_ONLY_MESSAGE = "Screening was approved; this is a read-only view of the final decisions"

export function ScreeningSummaryHeader({
  counts,
  reviewedCount,
  automation = [],
  thresholds,
  readOnly = false,
}: ScreeningSummaryHeaderProps) {
  const thresholdNote = thresholdsText(thresholds)
  const pct = counts.total === 0 ? 0 : Math.round((reviewedCount / counts.total) * 100)
  return (
    <ViewToolbar
      bordered={false}
      height="auto"
      className="px-0"
      title={
        <div className="space-y-1.5 font-normal">
          <h2 className="text-base font-semibold text-foreground">
            {readOnly ? "Screening decisions" : "Review screening decisions"}
          </h2>
          {readOnly ? (
            <p
              role="status"
              data-testid="screening-read-only-banner"
              className="flex items-center gap-2 rounded-panel border border-border bg-surface-2 px-3 py-2 text-sm text-foreground"
            >
              <Lock aria-hidden className="size-3.5 shrink-0 text-muted" />
              {SCREENING_READ_ONLY_MESSAGE}
            </p>
          ) : (
            <p className="text-sm text-muted">
              Check the AI&apos;s include and exclude calls before extraction starts. Uncertain papers are{" "}
              {UNCERTAIN_OUTCOME} unless you decide otherwise.
            </p>
          )}
          {thresholdNote && <p className="text-xs text-muted">{thresholdNote}</p>}
          <p className="text-sm text-foreground tabular-nums" aria-live="polite" data-testid="screening-reviewer-line">
            <span className="font-medium">{formatCount(counts.total)} screened by reviewers</span>
            {" · "}
            {reviewerDecisionLine(counts)}
          </p>
          {counts.automated > 0 && (
            <div
              className="flex items-center gap-1 text-sm text-muted tabular-nums"
              data-testid="screening-automation-line"
            >
              <span>
                Removed by automation{" "}
                <span className="font-medium text-foreground">{formatCount(counts.automated)}</span>
                {counts.rescued > 0 && ` (${formatCount(counts.rescued)} rescued)`}
              </span>
              <InfoHint label="Removed by automation, by step">
                <p className="mb-1">
                  Excluded by automated steps before any reviewer saw them. Review them under Removed by
                  automation to rescue false negatives.
                </p>
                <ul className="space-y-0.5 tabular-nums">
                  {automation.map((entry) => (
                    <li key={entry.step} className="flex justify-between gap-4">
                      <span className="first-letter:uppercase">{entry.label}</span>
                      <span>{formatCount(entry.count)}</span>
                    </li>
                  ))}
                </ul>
              </InfoHint>
            </div>
          )}
          {!readOnly && (
          <div className="flex items-center gap-2">
            <div
              role="progressbar"
              aria-label="Reviewer-screened papers reviewed"
              aria-valuemin={0}
              aria-valuemax={counts.total}
              aria-valuenow={reviewedCount}
              className="h-1.5 w-40 rounded-full bg-surface-3 overflow-hidden"
            >
              <div className="h-full rounded-full bg-intent-primary" style={{ width: `${pct}%` }} />
            </div>
            <span className="text-xs text-muted tabular-nums">
              Reviewed {formatCount(reviewedCount)} of {formatCount(counts.total)}
            </span>
          </div>
          )}
        </div>
      }
    />
  )
}
