import type { Dispatch, SetStateAction } from "react"
import type { NavigateFunction } from "react-router-dom"
import type { RunRequest, RunResponse } from "@/lib/api"
import { clearLiveRun, saveLiveRun } from "@/lib/api"
import type { StoredApiKeys } from "@/lib/api/storage"
import type { RunTab, SelectedRun } from "@/views/RunView"

export interface LiveRunRefs {
  liveRunNavigatedRef: { current: string | null }
  wasStreamingRef: { current: boolean }
}

export interface LiveRunSetters extends LiveRunRefs {
  reset: () => void
  setLiveRunId: (id: string) => void
  setLiveTopic: (topic: string) => void
  setLiveStartedAt: (date: Date) => void
  setLiveWorkflowId: (id: string | null) => void
  setSelectedRun: Dispatch<SetStateAction<SelectedRun | null>> | ((run: SelectedRun) => void)
  setActiveRunTab?: (tab: RunTab) => void
  navigate?: NavigateFunction
}

export interface ConnectLiveRunInput {
  runId: string
  topic: string
  workflowId: string | null
  startedAt?: Date
  createdAt?: string
  dbPath?: string | null
  tab?: RunTab
  navigatePath?: string
}

export interface ConnectLiveRunOptions {
  /** Skip reset when reconnecting to the same live run id. */
  skipResetIfSameRun?: boolean
  currentLiveRunId?: string | null
  /** Value for liveRunNavigatedRef; defaults to workflowId. */
  navigatedRef?: string | null
  resetStreamingRef?: boolean
}

/** Shared connect path: reset, persist live ids, select run, optional navigate. */
export function connectLiveRun(
  ctx: LiveRunSetters,
  input: ConnectLiveRunInput,
  options: ConnectLiveRunOptions = {},
): void {
  const {
    skipResetIfSameRun = false,
    currentLiveRunId = null,
    navigatedRef,
    resetStreamingRef = true,
  } = options

  const shouldReset = !skipResetIfSameRun || currentLiveRunId !== input.runId
  if (shouldReset) {
    ctx.reset()
  }
  if (resetStreamingRef) {
    ctx.wasStreamingRef.current = false
  }
  ctx.liveRunNavigatedRef.current = navigatedRef !== undefined ? navigatedRef : input.workflowId

  const now = input.startedAt ?? new Date()
  ctx.setLiveRunId(input.runId)
  ctx.setLiveTopic(input.topic)
  ctx.setLiveStartedAt(now)
  ctx.setLiveWorkflowId(input.workflowId)
  saveLiveRun({
    runId: input.runId,
    topic: input.topic,
    startedAt: now.toISOString(),
    workflowId: input.workflowId,
  })

  const setSelected = ctx.setSelectedRun as (run: SelectedRun) => void
  setSelected({
    runId: input.runId,
    workflowId: input.workflowId,
    topic: input.topic,
    dbPath: input.dbPath ?? null,
    isDone: false,
    startedAt: now,
    createdAt: input.createdAt ?? now.toISOString(),
  })

  if (input.tab && ctx.setActiveRunTab) {
    ctx.setActiveRunTab(input.tab)
  }
  if (input.navigatePath && ctx.navigate) {
    ctx.navigate(input.navigatePath, { replace: true })
  }
}

export interface ClearLiveRunUiArgs extends LiveRunRefs {
  reset: () => void
  setLiveRunId: (id: string | null) => void
  setLiveWorkflowId: (id: string | null) => void
  setLiveTopic: (topic: string | null) => void
  setLiveStartedAt: (date: Date | null) => void
}

/** Clear persisted live run and reset live-run UI state. */
export function clearLiveRunUi(ctx: ClearLiveRunUiArgs): void {
  clearLiveRun()
  ctx.reset()
  ctx.setLiveRunId(null)
  ctx.setLiveWorkflowId(null)
  ctx.setLiveTopic(null)
  ctx.setLiveStartedAt(null)
  ctx.wasStreamingRef.current = false
}

export interface BeginLiveRunArgs extends LiveRunSetters {
  res: RunResponse
  workflowId?: string | null
  tab?: RunTab
}

/** Shared reset + persist path for all run-start handlers. */
export function beginLiveRun({
  res,
  workflowId = null,
  tab = "activity",
  ...ctx
}: BeginLiveRunArgs): void {
  connectLiveRun(
    ctx,
    {
      runId: res.run_id,
      topic: res.topic,
      workflowId,
      tab,
    },
    { navigatedRef: null },
  )
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
