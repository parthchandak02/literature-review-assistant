import { Sparkles } from "lucide-react"
import { PageSection } from "@/components/ui/section"
import { GEN_STEPS, WEB_RESEARCH_FALLBACK_STEP, WEB_RESEARCH_DONE_INDEX } from "./constants"
import { buildTopicRoutingText, getFallbackStepLabel } from "./generationHelpers"

export function GenerationProgressCard({
  activeStepKey,
  stepMetadata,
  usedWebFallback,
  fallbackReason,
}: {
  activeStepKey: string
  stepMetadata: Record<string, unknown>
  usedWebFallback: boolean
  fallbackReason: string | null
}) {
  const activeIdx = GEN_STEPS.findIndex((s) => s.key === activeStepKey)
  const activeStep = activeIdx === -1 ? 0 : activeIdx
  const hasPassedWebSearch = activeStep > WEB_RESEARCH_DONE_INDEX
  const routeDetail = buildTopicRoutingText(stepMetadata)

  return (
    <PageSection icon={Sparkles} title="Config Generation Summary" description="Live generation progress">
      <div className="space-y-1.5">
        {GEN_STEPS.map((step, i) => {
          const fallbackSkipped =
            step.key === WEB_RESEARCH_FALLBACK_STEP && !usedWebFallback && hasPassedWebSearch
          const fallbackDegraded =
            step.key === WEB_RESEARCH_FALLBACK_STEP && usedWebFallback && (i <= activeStep)
          const done = i < activeStep
          const active = i === activeStep
          const showDetail = active || done || fallbackSkipped
          const rowCls = fallbackDegraded
            ? done
              ? "bg-intent-warning-subtle border-intent-warning-border"
              : active
              ? "bg-intent-warning-subtle border-intent-warning-border"
              : "bg-surface-2/40 border-border"
            : fallbackSkipped
            ? "bg-intent-info-subtle border-intent-info-border"
            : done
            ? "bg-intent-success-subtle border-intent-success-border"
            : active
            ? "bg-intent-primary-subtle border-intent-primary-border"
            : "bg-surface-2/40 border-border"
          const titleCls = fallbackDegraded
            ? done || active
              ? "text-foreground"
              : "text-muted"
            : fallbackSkipped
            ? "text-foreground"
            : done
            ? "text-foreground"
            : active
            ? "text-foreground"
            : "text-muted"
          const detailCls = fallbackDegraded
            ? "text-muted"
            : fallbackSkipped
            ? "text-muted"
            : done
            ? "text-muted"
            : "text-muted"
          const detailText = fallbackSkipped
            ? "Skipped because web research succeeded."
            : fallbackDegraded && fallbackReason
            ? `Falling back to model knowledge: ${fallbackReason}`
            : step.key === "topic_routing" && routeDetail
            ? routeDetail
            : step.detail
          const titleText =
            step.key === WEB_RESEARCH_FALLBACK_STEP
              ? getFallbackStepLabel(fallbackSkipped, fallbackDegraded)
              : step.label

          return (
            <div key={step.key} className={`rounded-lg border px-2.5 py-2 ${rowCls}`}>
              <p className={`text-xs font-medium leading-snug ${titleCls}`}>{titleText}</p>
              {showDetail && (
                <p className={`text-[11px] mt-1 leading-snug ${detailCls}`}>{detailText}</p>
              )}
            </div>
          )
        })}
      </div>
    </PageSection>
  )
}
