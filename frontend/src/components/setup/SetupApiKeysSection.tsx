import { useState } from "react"
import { ChevronDown, Eye, EyeOff, Key } from "lucide-react"
import { Input } from "@/components/ui/input"
import type { StoredApiKeys } from "@/lib/api"

interface ApiKeysProps {
  keys: StoredApiKeys
  onChange: (k: StoredApiKeys) => void
  embedded?: boolean
}

export function SetupApiKeysSection({ keys, onChange, embedded }: ApiKeysProps) {
  const [expanded, setExpanded] = useState(false)
  const [showDeepseek, setShowDeepseek] = useState(false)

  const fields: { id: keyof StoredApiKeys; label: string; placeholder: string; required?: boolean }[] = [
    { id: "deepseek", label: "DeepSeek API Key", placeholder: "sk-...", required: true },
    { id: "gemini", label: "Gemini API Key", placeholder: "optional -- AIza..." },
    { id: "openrouter", label: "OpenRouter API Key", placeholder: "optional -- sk-or-v1-..." },
    { id: "openai", label: "OpenAI API Key", placeholder: "optional -- sk-..." },
    { id: "anthropic", label: "Anthropic API Key", placeholder: "optional -- sk-ant-..." },
    { id: "groq", label: "Groq API Key", placeholder: "optional -- gsk_..." },
    { id: "mistral", label: "Mistral API Key", placeholder: "optional -- ..." },
    { id: "cohere", label: "Cohere API Key", placeholder: "optional -- ..." },
    { id: "scopus", label: "Scopus API Key", placeholder: "optional -- Elsevier Scopus search" },
    { id: "wos", label: "Web of Science API Key", placeholder: "optional -- Clarivate WoS Starter API" },
    { id: "openalex", label: "OpenAlex API Key", placeholder: "optional -- register free at openalex.org/sign-up" },
    { id: "pubmedEmail", label: "PubMed Email", placeholder: "user@example.com" },
    { id: "pubmedApiKey", label: "PubMed API Key", placeholder: "optional -- increases rate limits" },
    { id: "ieee", label: "IEEE Xplore API Key", placeholder: "optional" },
    { id: "perplexity", label: "Perplexity API Key", placeholder: "pplx-..." },
    { id: "semanticScholar", label: "Semantic Scholar API Key", placeholder: "optional" },
    { id: "crossrefEmail", label: "Crossref Email", placeholder: "user@example.com" },
  ]

  const primaryField = fields[0]
  const extraFields = fields.slice(1)

  const formContent = (
    <div className={embedded ? "space-y-3" : "px-4 py-4 space-y-3"}>
      {/* DeepSeek key -- always shown */}
      <div>
        <label className="block text-xs font-medium text-muted mb-1.5">
          {primaryField.label} <span className="text-intent-danger">*</span>
        </label>
        <div className="relative">
          <Input
            type={showDeepseek ? "text" : "password"}
            value={keys.deepseek}
            onChange={(e) => onChange({ ...keys, deepseek: e.target.value })}
            placeholder={primaryField.placeholder}
            autoComplete="off"
            className="pr-9 h-9 text-xs bg-background border-border text-foreground placeholder:text-muted focus-visible:ring-intent-primary-border"
          />
          <button
            type="button"
            onClick={() => setShowDeepseek((v) => !v)}
            className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted hover:text-foreground transition-colors"
          >
            {showDeepseek ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
          </button>
        </div>
      </div>

      {/* Optional keys toggle */}
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex items-center gap-1.5 text-xs text-muted hover:text-foreground transition-colors"
      >
        <ChevronDown className={`h-3.5 w-3.5 transition-transform ${expanded ? "rotate-180" : ""}`} />
        {expanded ? "Hide optional API keys" : "Add optional API keys (OpenAlex, PubMed, IEEE...)"}
      </button>

      {expanded && extraFields.map((f) => (
        <div key={f.id}>
          <label className="block text-xs font-medium text-muted mb-1">
            {f.label}
          </label>
          <Input
            type="text"
            value={keys[f.id] ?? ""}
            onChange={(e) => onChange({ ...keys, [f.id]: e.target.value })}
            placeholder={f.placeholder}
            autoComplete="off"
            className="h-9 text-xs bg-background border-border text-foreground placeholder:text-muted focus-visible:ring-intent-primary-border"
          />
        </div>
      ))}
    </div>
  )

  if (embedded) {
    return formContent
  }

  return (
    <div className="card-surface overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-border">
        <Key className="h-3.5 w-3.5 text-muted shrink-0" />
        <span className="text-xs font-semibold text-foreground flex-1">API Keys</span>
        {!keys.deepseek && (
          <span className="text-xs text-intent-danger font-medium">At least one LLM key required</span>
        )}
      </div>
      {formContent}
    </div>
  )
}
