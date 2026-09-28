import type { StoredApiKeys } from "@/lib/api"

export type KeyId = keyof StoredApiKeys

export interface ApiKeyField {
  id: KeyId
  label: string
  placeholder: string
  group: "llm" | "search"
  prefix?: string
  email?: boolean
}

export const LLM_FIELDS: ApiKeyField[] = [
  { id: "fireworks", label: "Fireworks AI", placeholder: "fw_...", group: "llm", prefix: "fw_" },
  { id: "gemini", label: "Gemini", placeholder: "AIza...", group: "llm", prefix: "AIza" },
  { id: "openrouter", label: "OpenRouter", placeholder: "sk-or-v1-...", group: "llm", prefix: "sk-or-" },
  { id: "openai", label: "OpenAI", placeholder: "sk-...", group: "llm", prefix: "sk-" },
  { id: "anthropic", label: "Anthropic", placeholder: "sk-ant-...", group: "llm", prefix: "sk-ant-" },
  { id: "groq", label: "Groq", placeholder: "gsk_...", group: "llm", prefix: "gsk_" },
  { id: "mistral", label: "Mistral", placeholder: "Mistral API key", group: "llm" },
  { id: "cohere", label: "Cohere", placeholder: "Cohere API key", group: "llm" },
  { id: "perplexity", label: "Perplexity", placeholder: "pplx-...", group: "llm", prefix: "pplx-" },
]

export const SEARCH_FIELDS: ApiKeyField[] = [
  { id: "scopus", label: "Scopus", placeholder: "Elsevier Scopus search key", group: "search" },
  { id: "wos", label: "Web of Science", placeholder: "Clarivate WoS Starter API key", group: "search" },
  { id: "openalex", label: "OpenAlex", placeholder: "register free at openalex.org/sign-up", group: "search" },
  { id: "pubmedEmail", label: "PubMed email", placeholder: "user@example.com", group: "search", email: true },
  { id: "pubmedApiKey", label: "PubMed API key", placeholder: "increases rate limits", group: "search" },
  { id: "ieee", label: "IEEE Xplore", placeholder: "IEEE Xplore API key", group: "search" },
  { id: "semanticScholar", label: "Semantic Scholar", placeholder: "Semantic Scholar key", group: "search" },
  { id: "crossrefEmail", label: "Crossref email", placeholder: "user@example.com", group: "search", email: true },
]

const ALL_FIELDS = [...LLM_FIELDS, ...SEARCH_FIELDS]

export const KEY_USAGE: Record<string, string> = {
  fireworks: "screening, extraction, quality assessment and writing",
  gemini: "research diagram drawing",
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

export function validateApiKeyValue(id: KeyId, value: string): string | null {
  const trimmed = value.trim()
  if (!trimmed) return null
  const field = ALL_FIELDS.find((f) => f.id === id)
  if (!field) return null
  if (field.email) {
    return EMAIL_RE.test(trimmed) ? null : "Enter a valid email address."
  }
  if (/\s/.test(trimmed)) return "Keys can't contain spaces."
  if (field.prefix && !trimmed.startsWith(field.prefix)) {
    return `${field.label} keys usually start with "${field.prefix}".`
  }
  if (field.prefix === "sk-" && trimmed.startsWith("sk-ant-")) {
    return "This looks like an Anthropic key."
  }
  return null
}
