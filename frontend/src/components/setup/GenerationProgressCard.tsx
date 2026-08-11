import { useMemo } from "react"
import { ConfigGenerationStepper, type ConfigGenStepDisplay, type ConfigGenStepStatus } from "@/components/config/ConfigGenerationStepper"
import { GEN_STEPS, WEB_RESEARCH_DONE_INDEX, WEB_RESEARCH_FALLBACK_STEP } from "./constants"
import { buildGenerationStepDetail, buildTopicRoutingText, getFallbackStepLabel } from "./generationHelpers"

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

  const steps = useMemo<ConfigGenStepDisplay[]>(() => {
    return GEN_STEPS.map((step, i) => {
      const fallbackSkipped =
        step.key === WEB_RESEARCH_FALLBACK_STEP && !usedWebFallback && hasPassedWebSearch
      const fallbackDegraded =
        step.key === WEB_RESEARCH_FALLBACK_STEP && usedWebFallback && i <= activeStep
      const done = i < activeStep
      const active = i === activeStep

      let status: ConfigGenStepStatus = "pending"
      if (fallbackDegraded) {
        status = active ? "active" : done ? "degraded" : "pending"
      } else if (fallbackSkipped) {
        status = "skipped"
      } else if (done) {
        status = "done"
      } else if (active) {
        status = "active"
      }

      const label =
        step.key === WEB_RESEARCH_FALLBACK_STEP
          ? getFallbackStepLabel(fallbackSkipped, fallbackDegraded)
          : step.label

      const detail = buildGenerationStepDetail(
        step.key,
        status,
        active ? stepMetadata : {},
        active ? "In progress..." : step.detail,
        {
          fallbackReason,
          routeDetail: step.key === "topic_routing" ? routeDetail : null,
        },
      )

      return {
        key: step.key,
        label,
        shortLabel: step.shortLabel,
        detail,
        status,
      }
    })
  }, [activeStep, fallbackReason, hasPassedWebSearch, routeDetail, stepMetadata, usedWebFallback])

  return <ConfigGenerationStepper steps={steps} />
}
