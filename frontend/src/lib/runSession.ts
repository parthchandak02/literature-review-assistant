import type { RunRequest, RunResponse } from "@/lib/api"
import type { StoredApiKeys } from "@/lib/api/storage"
import { saveLiveRun } from "@/lib/api/storage"
import type { SelectedRun, RunTab } from "@/views/RunView"

export interface BeginLiveRunArgs {
  res: RunResponse
  reset: () => void
  setLiveRunId: (id: string) => void
  setLiveTopic: (topic: string) => void
  setLiveStartedAt: (date: Date) => void
  setLiveWorkflowId: (id: string | null) => void
  setSelectedRun: (run: SelectedRun) => void
  setActiveRunTab: (tab: RunTab) => void
  liveRunNavigatedRef: { current: string | null }
  wasStreamingRef: { current: boolean }
  workflowId?: string | null
  tab?: RunTab
}

/** Shared reset + persist path for all run-start handlers. */
export function beginLiveRun({
  res,
  reset,
  setLiveRunId,
  setLiveTopic,
  setLiveStartedAt,
  setLiveWorkflowId,
  setSelectedRun,
  setActiveRunTab,
  liveRunNavigatedRef,
  wasStreamingRef,
  workflowId = null,
  tab = "activity",
}: BeginLiveRunArgs): void {
  reset()
  wasStreamingRef.current = false
  liveRunNavigatedRef.current = null
  const now = new Date()
  setLiveRunId(res.run_id)
  setLiveTopic(res.topic)
  setLiveStartedAt(now)
  setLiveWorkflowId(workflowId)
  saveLiveRun({
    runId: res.run_id,
    topic: res.topic,
    startedAt: now.toISOString(),
    workflowId,
  })
  setSelectedRun({
    runId: res.run_id,
    workflowId,
    topic: res.topic,
    dbPath: null,
    isDone: false,
    startedAt: now,
    createdAt: now.toISOString(),
  })
  setActiveRunTab(tab)
}

export function runRequestToStoredKeys(req: RunRequest): StoredApiKeys {
  return {
    gemini: req.gemini_api_key ?? "",
    deepseek: req.deepseek_api_key,
    openrouter: req.openrouter_api_key ?? "",
    openai: req.openai_api_key ?? "",
    anthropic: req.anthropic_api_key ?? "",
    groq: req.groq_api_key ?? "",
    mistral: req.mistral_api_key ?? "",
    cohere: req.cohere_api_key ?? "",
    openalex: req.openalex_api_key ?? "",
    ieee: req.ieee_api_key ?? "",
    pubmedEmail: req.pubmed_email ?? "",
    pubmedApiKey: req.pubmed_api_key ?? "",
    perplexity: req.perplexity_api_key ?? "",
    semanticScholar: req.semantic_scholar_api_key ?? "",
    crossrefEmail: req.crossref_email ?? "",
    wos: req.wos_api_key ?? "",
    scopus: req.scopus_api_key ?? "",
  }
}

export function resumeErrorMessage(err: unknown): string {
  if (err instanceof Error) return err.message
  return "Resume failed"
}
