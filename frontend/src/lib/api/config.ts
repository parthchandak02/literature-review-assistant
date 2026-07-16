import { APIResponseError, apiFetch } from "./client"
import { API_BASE } from "./internal"
import type { RunRequest } from "./types"
import type { StoredApiKeys } from "./storage"
import { emptyStoredApiKeys } from "./storage"

export interface EnvKeyProviderStatus {
  configured: boolean
  masked: string
  source: string | null
  required: boolean
}

export interface EnvKeysStatus {
  required_ui_keys: string[]
  providers: Record<string, EnvKeyProviderStatus>
  server_ready: boolean
}

const LLM_UI_LABELS: Record<string, string> = {
  deepseek: "DeepSeek",
  gemini: "Gemini",
  openrouter: "OpenRouter",
  openai: "OpenAI",
  anthropic: "Anthropic",
  groq: "Groq",
  mistral: "Mistral",
  cohere: "Cohere",
}

export function llmProviderLabel(uiKey: string): string {
  return LLM_UI_LABELS[uiKey] ?? uiKey
}

export async function getDefaultReviewConfig(): Promise<string> {
  const data = await apiFetch<{ content: string }>("/config/review")
  return data.content
}

/**
 * Streaming version of generateConfig. Calls the SSE endpoint, invoking
 * onProgress with each step key and metadata as the backend progresses through stages.
 * Resolves with the final YAML string when done.
 */
export async function generateConfigStream(
  researchQuestion: string,
  deepseekApiKey: string,
  generationProfile: "standard" | "health_sdg",
  onProgress: (step: string, metadata?: Record<string, unknown>) => void,
): Promise<string> {
  const res = await fetch(`${API_BASE}/config/generate/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      research_question: researchQuestion,
      deepseek_api_key: deepseekApiKey,
      generation_profile: generationProfile,
    }),
  })
  if (!res.ok) {
    let detail: unknown = `HTTP ${res.status}`
    try {
      detail = await res.json()
    } catch {
      // keep status detail
    }
    throw new APIResponseError("Config generation stream failed", res.status, detail)
  }
  const reader = res.body?.getReader()
  if (!reader) throw new Error("No response body from config generation stream")
  const decoder = new TextDecoder()
  let buffer = ""
  let yaml = ""
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split("\n")
    buffer = lines.pop() ?? ""
    for (const line of lines) {
      if (!line.startsWith("data: ")) continue
      try {
        const msg = JSON.parse(line.slice(6)) as {
          type: string
          step?: string
          yaml?: string
          quality?: Record<string, unknown>
          detail?: string
          [key: string]: unknown
        }
        if (msg.type === "progress" && msg.step) {
          const metadata: Record<string, unknown> = {}
          for (const [key, value] of Object.entries(msg)) {
            if (key !== "type" && key !== "step") {
              metadata[key] = value
            }
          }
          onProgress(msg.step, metadata)
        } else if (msg.type === "done" && msg.yaml) {
          yaml = msg.yaml
        } else if (msg.type === "error") {
          throw new Error(msg.detail ?? "Config generation failed")
        }
      } catch (parseErr) {
        if (parseErr instanceof Error && parseErr.message !== "Config generation failed") continue
        throw parseErr
      }
    }
  }
  if (!yaml) throw new Error("Config generation completed without producing a config")
  return yaml
}

/** Fetch the review.yaml that was used for a specific past run. Returns null if not available. */
export async function fetchRunConfig(workflowId: string, runRoot = "runs"): Promise<string | null> {
  const params = new URLSearchParams({ run_root: runRoot })
  try {
    const data = await apiFetch<{ content: string }>(
      `/history/${encodeURIComponent(workflowId)}/config?${params}`,
    )
    return data.content ?? null
  } catch (err) {
    if (err instanceof APIResponseError && err.status === 404) return null
    throw err
  }
}

export function buildRunRequest(
  reviewYaml: string,
  keys: StoredApiKeys,
  runRoot?: string,
): RunRequest {
  return {
    review_yaml: reviewYaml,
    deepseek_api_key: keys.deepseek,
    gemini_api_key: keys.gemini || undefined,
    openrouter_api_key: keys.openrouter || undefined,
    openai_api_key: keys.openai || undefined,
    anthropic_api_key: keys.anthropic || undefined,
    groq_api_key: keys.groq || undefined,
    mistral_api_key: keys.mistral || undefined,
    cohere_api_key: keys.cohere || undefined,
    openalex_api_key: keys.openalex || undefined,
    ieee_api_key: keys.ieee || undefined,
    pubmed_email: keys.pubmedEmail || undefined,
    pubmed_api_key: keys.pubmedApiKey || undefined,
    perplexity_api_key: keys.perplexity || undefined,
    semantic_scholar_api_key: keys.semanticScholar || undefined,
    crossref_email: keys.crossrefEmail || undefined,
    wos_api_key: keys.wos || undefined,
    scopus_api_key: keys.scopus || undefined,
    run_root: runRoot,
  }
}

/**
 * Fetch API keys that are already configured in the server's environment.
 * Never throws; returns all-empty on error.
 */
export async function fetchEnvKeys(): Promise<StoredApiKeys> {
  const empty = emptyStoredApiKeys()
  try {
    const data = await apiFetch<Partial<StoredApiKeys>>("/config/env-keys")
    return { ...empty, ...data }
  } catch {
    return empty
  }
}

export async function fetchRequiredLlmUiKeys(): Promise<string[]> {
  try {
    const payload = await apiFetch<{ ui_keys?: string[] }>("/config/env-keys/required")
    return payload.ui_keys?.length ? payload.ui_keys : ["deepseek"]
  } catch {
    return ["deepseek"]
  }
}

/** Masked credential status from server .env (no raw secrets). */
export async function fetchEnvKeysStatus(): Promise<EnvKeysStatus | null> {
  try {
    return await apiFetch<EnvKeysStatus>("/config/env-keys/status")
  } catch {
    return null
  }
}
