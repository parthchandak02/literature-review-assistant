import type { ConfigGenStepStatus } from "@/components/config/ConfigGenerationStepper"

export function buildTopicRoutingText(stepMetadata: Record<string, unknown>): string | null {
  const domain = typeof stepMetadata.domain === "string" ? stepMetadata.domain : null
  const confidence = typeof stepMetadata.confidence === "number" ? stepMetadata.confidence : null
  const policy = typeof stepMetadata.policy === "string" ? stepMetadata.policy : null
  if (!domain && !policy && confidence === null) return null
  const confidenceTxt = confidence === null ? "n/a" : confidence.toFixed(2)
  return `Domain=${domain ?? "unknown"}, confidence=${confidenceTxt}, policy=${policy ?? "unknown"}`
}

export function getFallbackStepLabel(fallbackSkipped: boolean, fallbackDegraded: boolean): string {
  if (fallbackSkipped) return "Web research backup skipped"
  if (fallbackDegraded) return "Web search unavailable"
  return "Web research backup (standby)"
}

function metadataDetail(stepMetadata: Record<string, unknown>): string | null {
  return typeof stepMetadata.detail === "string" && stepMetadata.detail.trim()
    ? stepMetadata.detail.trim()
    : null
}

export function buildGenerationStepDetail(
  stepKey: string,
  status: ConfigGenStepStatus,
  stepMetadata: Record<string, unknown>,
  defaultDetail: string,
  options?: {
    fallbackReason?: string | null
    routeDetail?: string | null
  },
): string | null {
  const liveDetail = metadataDetail(stepMetadata)

  if (status === "active") {
    return liveDetail ?? defaultDetail
  }

  if (stepKey === "web_research_fallback") {
    if (status === "degraded" && options?.fallbackReason) {
      return `Falling back to model knowledge: ${options.fallbackReason}`
    }
    if (status === "skipped") {
      return "Skipped because web research succeeded."
    }
    return liveDetail ?? defaultDetail
  }

  if (stepKey === "topic_routing" && options?.routeDetail) {
    return options.routeDetail
  }

  if (status === "skipped") {
    return "Skipped because web research succeeded."
  }

  if (status === "pending") {
    return null
  }

  return liveDetail ?? defaultDetail
}
