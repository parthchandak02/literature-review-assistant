import * as Popover from "@radix-ui/react-popover"
import { ChevronDown } from "lucide-react"
import { Button } from "@/components/ui/button"
import type { FunnelStage } from "@/lib/funnelStages"

const STAGE_LABEL: Record<string, string> = {
  raw: "Records retrieved",
  deduped: "After deduplication",
  after_metadata: "After metadata filter",
  to_llm: "Ranked for screening",
  to_dual_review: "Sent to dual review",
  fulltext: "Full-text assessed",
  included: "Included",
  chased: "Added via citation chasing",
}

export function RunFunnelPopover({ stages }: { stages: FunnelStage[] }) {
  if (stages.length === 0) return null
  return (
    <Popover.Root>
      <Popover.Trigger asChild>
        <Button type="button" size="xs" variant="ghost" className="gap-1 px-1.5">
          Funnel
          <ChevronDown aria-hidden />
        </Button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          align="start"
          sideOffset={6}
          className="glass-panel-strong z-50 min-w-56 rounded-panel border border-border p-3 text-sm shadow-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <p className="mb-2 text-xs font-medium text-muted-foreground">Screening funnel</p>
          <ol className="flex flex-col gap-1">
            {stages.map((stage) => (
              <li key={stage.key} className="flex items-baseline justify-between gap-6">
                <span className="text-muted-foreground">{STAGE_LABEL[stage.key] ?? stage.label}</span>
                <span className="font-semibold tabular-nums text-foreground">
                  {stage.count.toLocaleString()}
                </span>
              </li>
            ))}
          </ol>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  )
}
