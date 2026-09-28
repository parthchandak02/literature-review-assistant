import { ArrowRight, Hand } from "lucide-react"
import { Button } from "@/components/ui/button"
import type { RunTab } from "@/context/runSessionTypes"
import { GATE_ACTION_TAB, shouldShowGateBanner, type RunGate } from "./runRouting"

const GATE_COPY: Record<RunGate, { message: string; cta: string }> = {
  config_generating: {
    message: "Generating the review config. This usually takes a minute or two",
    cta: "View progress",
  },
  config_ready: {
    message: "Waiting on you: the review config is ready to check and launch",
    cta: "Open config",
  },
  awaiting_prospero: {
    message: "Paused: register the protocol on PROSPERO to continue",
    cta: "Go to PROSPERO step",
  },
  awaiting_review: {
    message: "Paused: screening decisions need your approval",
    cta: "Review now",
  },
}

export interface RunGateBannerProps {
  gate: RunGate | null
  activeTab: RunTab
  onTabChange: (tab: RunTab) => void
  /** Optional count shown with the message (e.g. decisions awaiting approval). */
  count?: number | null
}

export function RunGateBanner({ gate, activeTab, onTabChange, count }: RunGateBannerProps) {
  if (!shouldShowGateBanner(gate, activeTab)) return null
  const { message, cta } = GATE_COPY[gate]

  return (
    <div
      role="status"
      className="flex flex-wrap items-center gap-x-3 gap-y-1.5 shrink-0 border-b border-intent-primary-border bg-intent-primary-subtle px-6 py-2 text-sm text-foreground"
    >
      <span className="inline-flex items-center gap-2 min-w-0">
        <Hand className="h-3.5 w-3.5 shrink-0 text-intent-primary-text" aria-hidden />
        <span className="font-medium">
          {message}
          {count != null && count > 0 && (
            <span className="text-muted-foreground"> ({count.toLocaleString()})</span>
          )}
        </span>
      </span>
      <Button type="button" size="xs" onClick={() => onTabChange(GATE_ACTION_TAB[gate])}>
        {cta}
        <ArrowRight aria-hidden />
      </Button>
    </div>
  )
}
