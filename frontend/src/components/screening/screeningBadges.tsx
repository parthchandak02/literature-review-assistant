import { Bot, CheckCircle, XCircle, HelpCircle } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { automationStepLabel } from "@/lib/automationSteps"
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

/** Removed by an automated step before any reviewer decision; not an AI reviewer call. */
export function AutomationBadge({ step }: { step: string }) {
  const label = automationStepLabel(step)
  return (
    <Badge variant="neutral" size="sm" title={`Removed by automation: ${label}`}>
      <Bot aria-hidden />
      Auto-removed · {label}
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
      <span className="num text-2xs text-muted w-7 text-right">{pct}%</span>
    </span>
  )
}

export type DecisionSource = "ai" | "human"

const AI_PRESSED_CLASS: Record<HumanDecision, string> = {
  include: "border-intent-success-border bg-intent-success-subtle text-intent-success-text hover:text-intent-success-text",
  exclude: "border-intent-danger-border bg-intent-danger-subtle text-intent-danger-text hover:text-intent-danger-text",
}

const SHORTCUT: Record<HumanDecision, string> = { include: "i", exclude: "e" }

/**
 * Include/Exclude toggle. `pressed` marks the final decision; a human choice is a solid
 * fill and the AI default stays a tinted outline, so untouched rows don't read as manual.
 */
export function DecisionButton({
  decision,
  pressed,
  source,
  tabIndex,
  onClick,
}: {
  decision: HumanDecision
  pressed: boolean
  source: DecisionSource
  tabIndex?: number
  onClick: () => void
}) {
  const human = pressed && source === "human"
  const aiDefault = pressed && source === "ai"
  const label = decision === "include" ? "Include" : "Exclude"
  return (
    <Button
      type="button"
      size="xs"
      tabIndex={tabIndex}
      variant={human ? (decision === "include" ? "success" : "destructive") : "outline"}
      aria-pressed={pressed}
      data-decision-source={pressed ? source : undefined}
      title={`${label} (${SHORTCUT[decision]})${aiDefault ? " · AI decision" : ""}`}
      onClick={onClick}
      className={cn(aiDefault && AI_PRESSED_CLASS[decision])}
    >
      {label}
    </Button>
  )
}
