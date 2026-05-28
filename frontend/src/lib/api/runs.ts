import type { RunRequest, RunResponse } from "./types"
import type { StoredApiKeys } from "./storage"
import { API_BASE } from "./internal"
import { apiError } from "./internal"

function appendKeysToForm(form: FormData, keys: StoredApiKeys): void {
  form.append("deepseek_api_key", keys.deepseek)
  if (keys.gemini) form.append("gemini_api_key", keys.gemini)
  if (keys.openrouter) form.append("openrouter_api_key", keys.openrouter)
  if (keys.openai) form.append("openai_api_key", keys.openai)
  if (keys.anthropic) form.append("anthropic_api_key", keys.anthropic)
  if (keys.groq) form.append("groq_api_key", keys.groq)
  if (keys.mistral) form.append("mistral_api_key", keys.mistral)
  if (keys.cohere) form.append("cohere_api_key", keys.cohere)
  if (keys.openalex) form.append("openalex_api_key", keys.openalex)
  if (keys.ieee) form.append("ieee_api_key", keys.ieee)
  if (keys.pubmedEmail) form.append("pubmed_email", keys.pubmedEmail)
  if (keys.pubmedApiKey) form.append("pubmed_api_key", keys.pubmedApiKey)
  if (keys.perplexity) form.append("perplexity_api_key", keys.perplexity)
  if (keys.semanticScholar) form.append("semantic_scholar_api_key", keys.semanticScholar)
  if (keys.crossrefEmail) form.append("crossref_email", keys.crossrefEmail)
  if (keys.wos) form.append("wos_api_key", keys.wos)
  if (keys.scopus) form.append("scopus_api_key", keys.scopus)
}

export async function startRun(req: RunRequest): Promise<RunResponse> {
  const res = await fetch(`${API_BASE}/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`Failed to start run: ${text}`)
  }
  return res.json() as Promise<RunResponse>
}

export async function startRunWithMasterlist(
  csvFile: File,
  reviewYaml: string,
  keys: StoredApiKeys,
  runRoot = "runs",
): Promise<RunResponse> {
  const form = new FormData()
  form.append("csv_file", csvFile)
  form.append("review_yaml", reviewYaml)
  appendKeysToForm(form, keys)
  if (runRoot) form.append("run_root", runRoot)
  const res = await fetch(`${API_BASE}/run-with-masterlist`, {
    method: "POST",
    body: form,
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`Failed to start master list run: ${text}`)
  }
  return res.json() as Promise<RunResponse>
}

export async function startRunWithSupplementaryCsv(
  csvFile: File,
  reviewYaml: string,
  keys: StoredApiKeys,
  runRoot = "runs",
): Promise<RunResponse> {
  const form = new FormData()
  form.append("csv_file", csvFile)
  form.append("review_yaml", reviewYaml)
  appendKeysToForm(form, keys)
  if (runRoot) form.append("run_root", runRoot)
  const res = await fetch(`${API_BASE}/run-with-supplementary-csv`, {
    method: "POST",
    body: form,
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`Failed to start supplementary CSV run: ${text}`)
  }
  return res.json() as Promise<RunResponse>
}

export async function cancelRun(runId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/cancel/${runId}`, { method: "POST" })
  if (!res.ok) throw await apiError(res, "Cancel failed")
}
