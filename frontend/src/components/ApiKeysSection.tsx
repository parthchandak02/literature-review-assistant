import { useEffect, useRef, useState } from "react"
import {
  AlertTriangle,
  Check,
  CheckCircle2,
  ChevronDown,
  Eye,
  EyeOff,
  Server,
  Shield,
  X,
} from "lucide-react"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"
import {
  emptyStoredApiKeys,
  fetchEnvKeysStatus,
  fetchRequiredLlmUiKeys,
  llmProviderLabel,
  loadApiKeys,
  saveApiKeys,
} from "@/lib/api"
import type { StoredApiKeys, EnvKeysStatus } from "@/lib/api"
import {
  KEY_USAGE,
  LLM_FIELDS,
  SEARCH_FIELDS,
  validateApiKeyValue,
  type ApiKeyField,
  type KeyId,
} from "@/lib/apiKeyFields"

const SAVED_INDICATOR_DELAY_MS = 600
const SAVED_INDICATOR_VISIBLE_MS = 2000

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
  const isEmail = !!field.email
  const inputId = `api-key-${field.id}`
  const hintId = `${inputId}-hint`
  const serverHintId = `${inputId}-server`
  const serverLead = isEmail ? "Using server value" : "Using server key"
  const error = validateApiKeyValue(field.id, value)
  const maskedShowsPrefix = Boolean(
    usingEnv && field.prefix && envMasked.toLowerCase().startsWith(field.prefix.toLowerCase()),
  )
  const showFormatHint = Boolean(field.prefix) && !maskedShowsPrefix

  return (
    <div className="group">
      <div className="flex items-center gap-2 mb-1.5">
        <label htmlFor={inputId} className="text-xs font-medium text-muted flex-1">
          {field.label}
          {required && (
            <>
              <span className="text-intent-danger ml-0.5" aria-hidden>*</span>
              <span className="sr-only"> (required)</span>
            </>
          )}
        </label>
        {envConfigured && (
          <span
            className={cn(
              "inline-flex items-center gap-1 text-2xs font-medium",
              usingEnv ? "text-intent-success" : "text-muted",
            )}
            title={usingEnv ? "Runs use the key configured on the server" : "Browser value overrides the server key"}
          >
            <Server className="h-2.5 w-2.5" aria-hidden />
            Configured on server
          </span>
        )}
        {hasValue && (
          <span className="inline-flex items-center gap-1 text-2xs text-intent-primary font-medium">
            <Shield className="h-2.5 w-2.5" aria-hidden />
            Browser override
          </span>
        )}
      </div>
      <div className="relative">
        <Input
          id={inputId}
          type={isEmail ? "email" : show ? "text" : "password"}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={usingEnv ? "" : field.placeholder}
          autoComplete="off"
          spellCheck={false}
          aria-invalid={error ? true : undefined}
          aria-describedby={
            [usingEnv ? serverHintId : null, error || showFormatHint ? hintId : null].filter(Boolean).join(" ") || undefined
          }
          className={cn(
            "h-9 font-mono text-xs bg-background border-border/80 text-foreground placeholder:text-muted focus-visible:ring-intent-primary",
            hasValue && (isEmail ? "pr-9" : "pr-16"),
            error && "border-intent-warning-border",
          )}
        />
        {usingEnv && (
          <span
            id={serverHintId}
            className="pointer-events-none absolute inset-y-0 left-3 right-3 flex items-center text-xs text-muted"
          >
            <span className="truncate">
              {serverLead}
              {envMasked && (
                <>
                  {" "}(<code className="font-mono">{envMasked}</code>)
                </>
              )}
            </span>
          </span>
        )}
        <div className="absolute right-1.5 top-1/2 -translate-y-1/2 flex items-center gap-0.5">
          {hasValue && (
            <button
              type="button"
              onClick={() => onChange("")}
              aria-label={`Clear ${field.label}`}
              title="Clear"
              className="rounded p-1 text-muted hover:text-foreground transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <X className="h-3.5 w-3.5" aria-hidden />
            </button>
          )}
          {!isEmail && hasValue && (
            <button
              type="button"
              onClick={() => setShow((v) => !v)}
              aria-label={show ? `Hide ${field.label}` : `Show ${field.label}`}
              aria-pressed={show}
              className="rounded p-1 text-muted hover:text-foreground transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              {show ? <EyeOff className="h-3.5 w-3.5" aria-hidden /> : <Eye className="h-3.5 w-3.5" aria-hidden />}
            </button>
          )}
        </div>
      </div>
      {error ? (
        <p id={hintId} className="mt-1 text-2xs text-intent-warning-text">
          {error}
        </p>
      ) : showFormatHint ? (
        <p id={hintId} className="mt-1 text-2xs text-muted">
          Starts with <code className="font-mono">{field.prefix}</code>
        </p>
      ) : null}
    </div>
  )
}

function useSavedIndicator(): [boolean, () => void] {
  const [visible, setVisible] = useState(false)
  const showTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const hideTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(
    () => () => {
      if (showTimer.current) clearTimeout(showTimer.current)
      if (hideTimer.current) clearTimeout(hideTimer.current)
    },
    [],
  )

  function trigger() {
    setVisible(false)
    if (showTimer.current) clearTimeout(showTimer.current)
    if (hideTimer.current) clearTimeout(hideTimer.current)
    showTimer.current = setTimeout(() => {
      setVisible(true)
      hideTimer.current = setTimeout(() => setVisible(false), SAVED_INDICATOR_VISIBLE_MS)
    }, SAVED_INDICATOR_DELAY_MS)
  }

  return [visible, trigger]
}

export function ApiKeysPanel({ onValidityChange }: { onValidityChange?: (valid: boolean) => void }) {
  const [keys, setKeys] = useState<StoredApiKeys>(() => {
    const saved = loadApiKeys()
    return saved ? { ...emptyStoredApiKeys(), ...saved } : emptyStoredApiKeys()
  })
  const [envStatus, setEnvStatus] = useState<EnvKeysStatus | null>(null)
  const [requiredKeys, setRequiredKeys] = useState<string[]>(["fireworks"])
  const [showOptional, setShowOptional] = useState(false)
  const [savedVisible, markSaved] = useSavedIndicator()

  useEffect(() => {
    fetchEnvKeysStatus().then(setEnvStatus)
    fetchRequiredLlmUiKeys().then((k) => { if (k.length) setRequiredKeys(k) })
  }, [])

  function handleChange(id: KeyId, value: string) {
    const next = { ...keys, [id]: value }
    setKeys(next)
    saveApiKeys(next)
    markSaved()
  }

  const keysByName = keys as unknown as Record<string, string>
  const isConfigured = (id: string) =>
    !!String(keysByName[id] ?? "").trim() || (envStatus?.providers[id]?.configured ?? false)
  const missingRequired = requiredKeys.filter((key) => !isConfigured(key))
  const allValid = missingRequired.length === 0

  useEffect(() => {
    onValidityChange?.(allValid)
  }, [allValid, onValidityChange])

  const requiredFields = LLM_FIELDS.filter((f) => requiredKeys.includes(f.id))
  const optionalLlm = LLM_FIELDS.filter((f) => !requiredKeys.includes(f.id))
  const optionalCount = optionalLlm.length + SEARCH_FIELDS.length
  const optionalConfigured = [...optionalLlm, ...SEARCH_FIELDS].filter((f) => isConfigured(f.id)).length

  function renderField(field: ApiKeyField) {
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
  }

  return (
    <div className="space-y-5">
      {allValid ? (
        <div className="flex items-center gap-2.5 px-3 py-2.5 rounded-panel bg-intent-success-subtle border border-intent-success-border text-xs text-intent-success">
          <CheckCircle2 className="h-3.5 w-3.5 shrink-0" aria-hidden />
          <span>All required keys configured.</span>
        </div>
      ) : (
        <div
          role="alert"
          className="flex items-start gap-2.5 px-3 py-2.5 rounded-panel bg-intent-warning-subtle border border-intent-warning-border text-xs text-intent-warning-text"
        >
          <AlertTriangle className="h-3.5 w-3.5 mt-0.5 shrink-0" aria-hidden />
          <div className="space-y-0.5">
            <p className="font-medium">
              Missing required key{missingRequired.length > 1 ? "s" : ""}:{" "}
              {missingRequired.map((k) => llmProviderLabel(k)).join(", ")}
            </p>
            {missingRequired.map((k) => (
              <p key={k}>
                New reviews can't start without {llmProviderLabel(k)}. It's used for{" "}
                {KEY_USAGE[k] ?? "the model steps configured on the server"}.
              </p>
            ))}
          </div>
        </div>
      )}

      <section aria-labelledby="api-keys-required-heading">
        <div className="flex items-center gap-2 mb-3">
          <h4 id="api-keys-required-heading" className="text-xs font-semibold text-foreground uppercase tracking-wide">
            Required
          </h4>
          <span
            role="status"
            className={cn(
              "ml-auto inline-flex items-center gap-1 text-2xs font-medium text-intent-success transition-opacity motion-reduce:transition-none",
              savedVisible ? "opacity-100" : "opacity-0",
            )}
          >
            {savedVisible && (
              <>
                <Check className="h-3 w-3" aria-hidden />
                Saved
              </>
            )}
          </span>
        </div>
        <div className="space-y-3">{requiredFields.map(renderField)}</div>
      </section>

      <section>
        <button
          type="button"
          onClick={() => setShowOptional((v) => !v)}
          aria-expanded={showOptional}
          aria-controls="api-keys-optional"
          className="flex items-center gap-2 mb-3 cursor-pointer rounded pointer-coarse:min-h-11 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <h4 className="text-xs font-semibold text-foreground uppercase tracking-wide">
            Optional providers
          </h4>
          <span className="text-2xs text-muted">
            {optionalConfigured}/{optionalCount} configured
          </span>
          <ChevronDown
            className={cn(
              "h-3 w-3 text-muted transition-transform motion-reduce:transition-none",
              showOptional && "rotate-180",
            )}
            aria-hidden
          />
        </button>

        {showOptional && (
          <div id="api-keys-optional" className="space-y-5">
            {optionalLlm.length > 0 && (
              <div>
                <h5 className="mb-2 text-2xs font-semibold uppercase tracking-wide text-muted">
                  Other LLM providers
                </h5>
                <div className="space-y-3">{optionalLlm.map(renderField)}</div>
              </div>
            )}
            <div>
              <h5 className="mb-2 text-2xs font-semibold uppercase tracking-wide text-muted">
                Search &amp; data sources
              </h5>
              <div className="space-y-3">{SEARCH_FIELDS.map(renderField)}</div>
            </div>
          </div>
        )}
      </section>

      <p className="text-2xs text-muted leading-relaxed">
        Keys configured on the server are used automatically and are never sent to the browser.
        Browser overrides are stored in this browser only and take precedence for runs you start here.
      </p>
    </div>
  )
}
