import * as Popover from "@radix-ui/react-popover"
import { ChevronDown } from "lucide-react"
import { cn } from "@/lib/utils"
import type { FunnelStage } from "@/lib/funnelStages"

const STAGE_LABEL: Record<string, string> = {
  identified: "Records identified",
  duplicates: "Duplicates removed",
  deduped: "Records after duplicates removed",
  automation: "Removed by automation tools",
  screened: "Records screened by reviewers",
  excluded_ta: "Excluded at title/abstract",
  sought: "Reports sought for retrieval",
  not_retrieved: "Reports not retrieved",
  assessed: "Reports assessed (full text)",
  excluded_ft: "Excluded at full text",
  included: "Studies included",
  chased: "Added via citation chasing",
}

const CHAIN_LABEL: Record<string, string> = {
  screened: "screened",
  assessed: "assessed",
}

function funnelChainStages(stages: FunnelStage[]): FunnelStage[] {
  const byKey = new Map(stages.map((s) => [s.key, s]))
  const first = byKey.get("identified") ?? byKey.get("deduped")
  return [first, byKey.get("screened"), byKey.get("assessed"), byKey.get("included")].filter(
    (s): s is FunnelStage => s != null,
  )
}

function FunnelChain({ stages }: { stages: FunnelStage[] }) {
  return (
    <span className="inline-flex items-baseline gap-1 whitespace-nowrap" data-testid="run-funnel-chain">
      {stages.map((stage, i) => (
        <span key={stage.key} className="inline-flex items-baseline gap-1">
          {i > 0 && (
            <span aria-hidden className="select-none text-text-dim">
              →
            </span>
          )}
          <span className={cn("num font-semibold", stage.colorClass)}>{stage.count.toLocaleString()}</span>
          {CHAIN_LABEL[stage.key] && (
            <span className="hidden text-muted @4xl:inline">{CHAIN_LABEL[stage.key]}</span>
          )}
        </span>
      ))}
    </span>
  )
}

export function RunFunnelPopover({ stages }: { stages: FunnelStage[] }) {
  if (stages.length === 0) return null
  const chain = funnelChainStages(stages)
  return (
    <Popover.Root>
      <Popover.Trigger asChild>
        <button
          type="button"
          aria-label="Show full funnel"
          title="Show full funnel"
          className="touch-hit group inline-flex shrink-0 items-center gap-1 rounded-sm px-1 -mx-1 py-0.5 pointer-coarse:min-h-6 transition-colors hover:bg-surface-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring data-[state=open]:bg-surface-2"
        >
          <FunnelChain stages={chain.length > 0 ? chain : stages.slice(0, 1)} />
          <ChevronDown
            aria-hidden
            className="h-3 w-3 shrink-0 text-text-dim transition-transform group-hover:text-muted-foreground group-data-[state=open]:rotate-180 motion-reduce:transition-none"
          />
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          align="start"
          sideOffset={6}
          className="glass-popover z-50 min-w-64 rounded-panel p-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <p className="mb-2 text-xs font-medium text-muted-foreground">PRISMA flow (live counts)</p>
          <ol className="flex flex-col gap-1">
            {stages.map((stage) =>
              stage.kind === "removed" ? (
                <li key={stage.key} className="flex items-baseline justify-between gap-6 pl-3 text-xs text-muted">
                  <span>{STAGE_LABEL[stage.key] ?? stage.label}</span>
                  <span className="num text-right">−{stage.count.toLocaleString()}</span>
                </li>
              ) : (
                <li key={stage.key} className="flex items-baseline justify-between gap-6">
                  <span className="text-muted-foreground">{STAGE_LABEL[stage.key] ?? stage.label}</span>
                  <span className={cn("num text-right font-semibold", stage.colorClass)}>
                    {stage.count.toLocaleString()}
                  </span>
                </li>
              ),
            )}
          </ol>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  )
}
