import { CheckCircle, XCircle, HelpCircle } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { screeningDecisionToVariant } from "@/lib/constants"
import type { HumanDecision } from "./screeningModel"

export function DecisionBadge({ decision, prefix }: { decision: string; prefix?: string }) {
  const variant = screeningDecisionToVariant(decision)
  const Icon = decision === "include" ? CheckCircle : decision === "exclude" ? XCircle : HelpCircle
  const label = decision === "include" ? "Include" : decision === "exclude" ? "Exclude" : "Uncertain"
  return (
    <Badge variant={variant} size="sm">
      <Icon aria-hidden />
      {prefix ? `${prefix}: ${label}` : label}
    </Badge>
  )
}

export function OverrideBadge({ decision }: { decision: HumanDecision }) {
  return (
    <Badge variant="primary" size="sm">
      Override: {decision === "include" ? "Include" : "Exclude"}
    </Badge>
  )
}

/** Neutral meter: low confidence is not an error, so it never borrows the Exclude red. */
export function ConfidenceMeter({ confidence }: { confidence: number | null }) {
  if (confidence == null) {
    return <span className="text-2xs text-muted tabular-nums w-16 text-right">No score</span>
  }
  const pct = Math.max(0, Math.min(100, Math.round(confidence * 100)))
  return (
    <span
      role="meter"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={pct}
      aria-label={`AI confidence ${pct}%`}
      title={`AI confidence ${pct}%`}
      className="inline-flex items-center gap-1.5 w-16"
    >
      <span className="relative h-1.5 flex-1 rounded-full bg-surface-3 overflow-hidden">
        <span className="absolute inset-y-0 left-0 rounded-full bg-intent-neutral" style={{ width: `${pct}%` }} />
      </span>
      <span className="text-2xs text-muted tabular-nums w-7 text-right">{pct}%</span>
    </span>
  )
}
