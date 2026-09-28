import { ViewToolbar } from "@/components/ui/view-toolbar"
import type { ScreeningThresholds } from "@/lib/api"
import { summaryLine, thresholdsText, UNCERTAIN_OUTCOME, type DecisionCounts } from "./screeningModel"

export interface ScreeningSummaryHeaderProps {
  counts: DecisionCounts
  reviewedCount: number
  thresholds?: ScreeningThresholds | null
}

export function ScreeningSummaryHeader({ counts, reviewedCount, thresholds }: ScreeningSummaryHeaderProps) {
  const thresholdNote = thresholdsText(thresholds)
  const pct = counts.total === 0 ? 0 : Math.round((reviewedCount / counts.total) * 100)
  return (
    <ViewToolbar
      bordered={false}
      height="auto"
      className="px-0"
      title={
        <div className="space-y-1.5 font-normal">
          <h2 className="text-base font-semibold text-foreground">Review screening decisions</h2>
          <p className="text-sm text-muted">
            Check the AI&apos;s include and exclude calls before extraction starts. Uncertain papers are{" "}
            {UNCERTAIN_OUTCOME} unless you decide otherwise.
          </p>
          {thresholdNote && <p className="text-xs text-muted">{thresholdNote}</p>}
          <p className="text-sm text-foreground tabular-nums" aria-live="polite">
            {summaryLine(counts)}
          </p>
          <div className="flex items-center gap-2">
            <div
              role="progressbar"
              aria-label="Papers reviewed"
              aria-valuemin={0}
              aria-valuemax={counts.total}
              aria-valuenow={reviewedCount}
              className="h-1.5 w-40 rounded-full bg-surface-3 overflow-hidden"
            >
              <div className="h-full rounded-full bg-intent-primary" style={{ width: `${pct}%` }} />
            </div>
            <span className="text-xs text-muted tabular-nums">
              Reviewed {reviewedCount} of {counts.total}
            </span>
          </div>
        </div>
      }
    />
  )
}
