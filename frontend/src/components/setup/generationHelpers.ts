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
