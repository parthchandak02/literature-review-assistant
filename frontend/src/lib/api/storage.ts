export interface StoredLiveRun {
  runId: string
  topic: string
  startedAt: string
  workflowId?: string | null
}

export interface StoredApiKeys {
  gemini: string
  deepseek: string
  openrouter: string
  openai: string
  anthropic: string
  groq: string
  mistral: string
  cohere: string
  openalex: string
  ieee: string
  pubmedEmail: string
  pubmedApiKey: string
  perplexity: string
  semanticScholar: string
  crossrefEmail: string
  wos: string
  scopus: string
}

const LIVE_RUN_KEY = "litreview_live_run"
const API_KEYS_KEY = "litreview_api_keys"

export function saveLiveRun(run: StoredLiveRun): void {
  try {
    localStorage.setItem(LIVE_RUN_KEY, JSON.stringify(run))
  } catch {
    // ignore quota / security errors
  }
}

export function loadLiveRun(): StoredLiveRun | null {
  try {
    const raw = localStorage.getItem(LIVE_RUN_KEY)
    return raw ? (JSON.parse(raw) as StoredLiveRun) : null
  } catch {
    return null
  }
}

export function clearLiveRun(): void {
  try {
    localStorage.removeItem(LIVE_RUN_KEY)
  } catch {
    // ignore
  }
}

export function emptyStoredApiKeys(): StoredApiKeys {
  return {
    gemini: "",
    deepseek: "",
    openrouter: "",
    openai: "",
    anthropic: "",
    groq: "",
    mistral: "",
    cohere: "",
    openalex: "",
    ieee: "",
    pubmedEmail: "",
    pubmedApiKey: "",
    perplexity: "",
    semanticScholar: "",
    crossrefEmail: "",
    wos: "",
    scopus: "",
  }
}

export function saveApiKeys(keys: StoredApiKeys): void {
  try {
    localStorage.setItem(API_KEYS_KEY, JSON.stringify(keys))
  } catch {
    // ignore quota / security errors
  }
}

export function loadApiKeys(): StoredApiKeys | null {
  try {
    const raw = localStorage.getItem(API_KEYS_KEY)
    return raw ? (JSON.parse(raw) as StoredApiKeys) : null
  } catch {
    return null
  }
}

export function clearApiKeys(): void {
  try {
    localStorage.removeItem(API_KEYS_KEY)
  } catch {
    // ignore
  }
}

export function resolveStoredApiKeys(overrides?: Partial<StoredApiKeys>): StoredApiKeys {
  const saved = loadApiKeys()
  return { ...emptyStoredApiKeys(), ...(saved ?? {}), ...(overrides ?? {}) }
}
