import { CheckCircle, XCircle, HelpCircle } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { confidenceToVariant, screeningDecisionToVariant } from "@/lib/constants"

export function DecisionBadge({ decision }: { decision: string }) {
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

export function ConfidencePill({ confidence }: { confidence: number | null }) {
  if (confidence == null) return null
  const pct = Math.round(confidence * 100)
  return (
    <Badge variant={confidenceToVariant(confidence)} size="sm" className="font-mono">
      {pct}% conf.
    </Badge>
  )
}
