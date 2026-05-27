import { useEffect, useState } from "react"
import { CheckCircle2, ChevronDown, Eye, EyeOff, Server, Shield } from "lucide-react"
import { Input } from "@/components/ui/input"
import {
  emptyStoredApiKeys,
  fetchEnvKeys,
  fetchEnvKeysStatus,
  fetchRequiredLlmUiKeys,
  llmProviderLabel,
  loadApiKeys,
  saveApiKeys,
} from "@/lib/api"
import type { StoredApiKeys, EnvKeysStatus } from "@/lib/api"

interface ApiKeyField {
  id: keyof StoredApiKeys
  label: string
  placeholder: string
  group: "llm" | "search"
}

const LLM_FIELDS: ApiKeyField[] = [
  { id: "deepseek", label: "DeepSeek", placeholder: "sk-...", group: "llm" },
  { id: "gemini", label: "Gemini", placeholder: "AIza...", group: "llm" },
  { id: "openrouter", label: "OpenRouter", placeholder: "sk-or-v1-...", group: "llm" },
  { id: "openai", label: "OpenAI", placeholder: "sk-...", group: "llm" },
  { id: "anthropic", label: "Anthropic", placeholder: "sk-ant-...", group: "llm" },
  { id: "groq", label: "Groq", placeholder: "gsk_...", group: "llm" },
  { id: "mistral", label: "Mistral", placeholder: "...", group: "llm" },
  { id: "cohere", label: "Cohere", placeholder: "...", group: "llm" },
  { id: "perplexity", label: "Perplexity", placeholder: "pplx-...", group: "llm" },
]

const SEARCH_FIELDS: ApiKeyField[] = [
  { id: "scopus", label: "Scopus", placeholder: "Elsevier Scopus search key", group: "search" },
  { id: "wos", label: "Web of Science", placeholder: "Clarivate WoS Starter API key", group: "search" },
  { id: "openalex", label: "OpenAlex", placeholder: "register free at openalex.org/sign-up", group: "search" },
  { id: "pubmedEmail", label: "PubMed Email", placeholder: "user@example.com", group: "search" },
  { id: "pubmedApiKey", label: "PubMed API Key", placeholder: "increases rate limits", group: "search" },
  { id: "ieee", label: "IEEE Xplore", placeholder: "IEEE Xplore API key", group: "search" },
  { id: "semanticScholar", label: "Semantic Scholar", placeholder: "Semantic Scholar key", group: "search" },
  { id: "crossrefEmail", label: "Crossref Email", placeholder: "user@example.com", group: "search" },
]

function KeyField({
  field,
  value,
  envConfigured,
  envMasked,
  required,
  onChange,
}: {
  field: ApiKeyField
  value: string
  envConfigured: boolean
  envMasked: string
  required: boolean
  onChange: (v: string) => void
}) {
  const [show, setShow] = useState(false)
  const hasValue = !!value.trim()
  const usingEnv = envConfigured && !hasValue

  return (
    <div className="group">
      <div className="flex items-center gap-2 mb-1.5">
        <label className="text-xs font-medium text-zinc-400 flex-1">
          {field.label}
          {required && <span className="text-intent-danger ml-0.5">*</span>}
        </label>
        {usingEnv && (
          <span className="inline-flex items-center gap-1 text-[10px] text-intent-success font-medium">
            <Server className="h-2.5 w-2.5" />
            .env
          </span>
        )}
        {hasValue && (
          <span className="inline-flex items-center gap-1 text-[10px] text-intent-primary font-medium">
            <Shield className="h-2.5 w-2.5" />
            browser
          </span>
        )}
      </div>
      <div className="relative">
        <Input
          type={show ? "text" : "password"}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={usingEnv ? `Using .env (${envMasked})` : field.placeholder}
          autoComplete="off"
          className="pr-9 h-9 text-xs bg-zinc-950 border-zinc-700/80 text-zinc-200 placeholder:text-zinc-600 focus-visible:ring-intent-primary"
        />
        <button
          type="button"
          onClick={() => setShow((v) => !v)}
          className="absolute right-2.5 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-zinc-300 transition-colors"
        >
          {show ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
        </button>
      </div>
    </div>
  )
}

export function ApiKeysPanel({ onValidityChange }: { onValidityChange?: (valid: boolean) => void }) {
  const [keys, setKeys] = useState<StoredApiKeys>(() => {
    const saved = loadApiKeys()
    return saved ? { ...emptyStoredApiKeys(), ...saved } : emptyStoredApiKeys()
  })
  const [envStatus, setEnvStatus] = useState<EnvKeysStatus | null>(null)
  const [requiredKeys, setRequiredKeys] = useState<string[]>(["deepseek"])
  const [showSearch, setShowSearch] = useState(false)

  useEffect(() => {
    fetchEnvKeysStatus().then(setEnvStatus)
    fetchRequiredLlmUiKeys().then((k) => { if (k.length) setRequiredKeys(k) })
  }, [])

  useEffect(() => {
    fetchEnvKeys().then((envKeys) => {
      setKeys((prev) => {
        const merged = { ...prev }
        for (const k of Object.keys(envKeys) as (keyof typeof envKeys)[]) {
          const current = String(merged[k] ?? "").trim()
          if ((!current || current === "undefined") && envKeys[k]) {
            merged[k] = envKeys[k]
          }
        }
        return merged
      })
    })
  }, [])

  function handleChange(id: keyof StoredApiKeys, value: string) {
    const next = { ...keys, [id]: value }
    setKeys(next)
    saveApiKeys(next)
  }

  const keysByName = keys as unknown as Record<string, string>
  const missingRequired = requiredKeys.filter((key) => {
    const browserVal = String(keysByName[key] ?? "").trim()
    const envConfigured = envStatus?.providers[key]?.configured ?? false
    return !browserVal && !envConfigured
  })
  const allValid = missingRequired.length === 0

  useEffect(() => {
    onValidityChange?.(allValid)
  }, [allValid, onValidityChange])

  const configuredLlmCount = LLM_FIELDS.filter((f) => {
    const browserVal = String(keys[f.id] ?? "").trim()
    const envConfigured = envStatus?.providers[f.id]?.configured ?? false
    return !!browserVal || envConfigured
  }).length

  const configuredSearchCount = SEARCH_FIELDS.filter((f) => {
    const browserVal = String(keys[f.id] ?? "").trim()
    const envConfigured = envStatus?.providers[f.id]?.configured ?? false
    return !!browserVal || envConfigured
  }).length

  return (
    <div className="space-y-5">
      {/* Status summary */}
      {allValid ? (
        <div className="flex items-center gap-2.5 px-3 py-2.5 rounded-xl bg-intent-success-subtle border border-intent-success-border text-xs text-intent-success">
          <CheckCircle2 className="h-3.5 w-3.5 shrink-0" />
          <span>
            All required keys configured.
            {envStatus?.server_ready && " Server .env is active."}
          </span>
        </div>
      ) : (
        <div className="flex items-center gap-2.5 px-3 py-2.5 rounded-xl bg-intent-warning-subtle border border-intent-warning-border text-xs text-intent-warning">
          <span>
            Missing required key{missingRequired.length > 1 ? "s" : ""}:{" "}
            {missingRequired.map((k) => llmProviderLabel(k)).join(", ")}
          </span>
        </div>
      )}

      {/* LLM Providers */}
      <div>
        <div className="flex items-center gap-2 mb-3">
          <h4 className="text-xs font-semibold text-zinc-300 uppercase tracking-wide">
            LLM Providers
          </h4>
          <span className="text-[10px] text-zinc-600">
            {configuredLlmCount}/{LLM_FIELDS.length} configured
          </span>
        </div>
        <div className="space-y-3">
          {LLM_FIELDS.map((field) => {
            const provider = envStatus?.providers[field.id]
            return (
              <KeyField
                key={field.id}
                field={field}
                value={keys[field.id]}
                envConfigured={provider?.configured ?? false}
                envMasked={provider?.masked ?? ""}
                required={requiredKeys.includes(field.id)}
                onChange={(v) => handleChange(field.id, v)}
              />
            )
          })}
        </div>
      </div>

      {/* Search / Data Sources */}
      <div>
        <button
          type="button"
          onClick={() => setShowSearch((v) => !v)}
          className="flex items-center gap-2 mb-3 group cursor-pointer"
        >
          <h4 className="text-xs font-semibold text-zinc-300 uppercase tracking-wide group-hover:text-zinc-100 transition-colors">
            Search &amp; Data Sources
          </h4>
          <span className="text-[10px] text-zinc-600">
            {configuredSearchCount}/{SEARCH_FIELDS.length} configured
          </span>
          <ChevronDown className={`h-3 w-3 text-zinc-500 transition-transform ${showSearch ? "rotate-180" : ""}`} />
        </button>

        {showSearch && (
          <div className="space-y-3">
            {SEARCH_FIELDS.map((field) => {
              const provider = envStatus?.providers[field.id]
              return (
                <KeyField
                  key={field.id}
                  field={field}
                  value={keys[field.id]}
                  envConfigured={provider?.configured ?? false}
                  envMasked={provider?.masked ?? ""}
                  required={false}
                  onChange={(v) => handleChange(field.id, v)}
                />
              )
            })}
          </div>
        )}
      </div>

      <p className="text-[11px] text-zinc-600 leading-relaxed">
        Keys in <code className="text-zinc-500">.env</code> are the source of truth.
        Browser overrides apply only to this session and are not written to disk.
      </p>
    </div>
  )
}
