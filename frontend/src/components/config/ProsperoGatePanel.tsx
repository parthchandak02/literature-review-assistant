import { useId, useState } from "react"
import { Download, ExternalLink, FileCode, FileType, RefreshCw, ShieldCheck } from "lucide-react"
import { Button } from "@/components/ui/button"
import { DateInput } from "@/components/ui/date-input"
import { Input } from "@/components/ui/input"
import { PageSection } from "@/components/ui/section"
import { Badge } from "@/components/ui/badge"
import { Spinner } from "@/components/ui/feedback"
import { prosperoFormDocxUrl, prosperoFormMarkdownUrl } from "@/lib/api"
import type { ProsperoRegistration } from "@/lib/api"
import { isProsperoRegistrationNumberValid } from "@/lib/constants"
import { PROSPERO_ID_HELPER, PROSPERO_SKIP_SUPPORTED, prosperoIdError } from "@/lib/prosperoConfig"
import type { ReviewTypeChoice } from "@/components/setup/types"
import { cn } from "@/lib/utils"

export interface ProsperoGatePanelProps {
  runId: string | null
  workflowId?: string | null
  mode?: "gate" | "manage"
  initialRegistration?: ProsperoRegistration | null
  isComplete?: boolean
  attention?: boolean
  disabled?: boolean
  isSubmitting?: boolean
  isRegenerating?: boolean
  onStartResearch?: (registration: ProsperoRegistration) => void | Promise<void>
  onSaveRegistration?: (registration: ProsperoRegistration) => void | Promise<void>
  onRegenerateDrafts?: () => void | Promise<void>
  reviewType?: ReviewTypeChoice | null
  /** Rendered only when the backend supports unregistered runs (PROSPERO_SKIP_SUPPORTED). */
  onStartWithoutRegistration?: () => void | Promise<void>
}

export function ProsperoGatePanel({
  runId,
  workflowId = null,
  mode = "gate",
  initialRegistration = null,
  isComplete = false,
  attention = false,
  disabled = false,
  isSubmitting = false,
  isRegenerating = false,
  onStartResearch,
  onSaveRegistration,
  onRegenerateDrafts,
  reviewType = null,
  onStartWithoutRegistration,
}: ProsperoGatePanelProps) {
  const registrationSeed = `${initialRegistration?.registration_number ?? ""}|${initialRegistration?.registration_date ?? ""}`

  return (
    <ProsperoGatePanelBody
      key={registrationSeed}
      runId={runId}
      workflowId={workflowId}
      mode={mode}
      initialRegistration={initialRegistration}
      isComplete={isComplete}
      attention={attention}
      disabled={disabled}
      isSubmitting={isSubmitting}
      isRegenerating={isRegenerating}
      onStartResearch={onStartResearch}
      onSaveRegistration={onSaveRegistration}
      onRegenerateDrafts={onRegenerateDrafts}
      reviewType={reviewType}
      onStartWithoutRegistration={onStartWithoutRegistration}
    />
  )
}

function ProsperoGatePanelBody({
  runId,
  workflowId = null,
  mode = "gate",
  initialRegistration = null,
  isComplete = false,
  attention = false,
  disabled = false,
  isSubmitting = false,
  isRegenerating = false,
  onStartResearch,
  onSaveRegistration,
  onRegenerateDrafts,
  reviewType = null,
  onStartWithoutRegistration,
}: ProsperoGatePanelProps) {
  const numberHelpId = useId()
  const [numberTouched, setNumberTouched] = useState(false)
  const [registrationNumber, setRegistrationNumber] = useState(initialRegistration?.registration_number ?? "")
  const [registrationDate, setRegistrationDate] = useState(initialRegistration?.registration_date ?? "")

  const trimmedNumber = registrationNumber.trim()
  const numberValid = isProsperoRegistrationNumberValid(trimmedNumber)
  const dateValid = registrationDate.length > 0
  const formValid = numberValid && dateValid && !disabled && !isSubmitting && !isRegenerating
  const artifactId = workflowId ?? runId
  const isGateMode = mode === "gate"
  const controlsDisabled = disabled || isSubmitting || isRegenerating
  const numberError = numberTouched ? prosperoIdError(registrationNumber) : null
  const isScoping = reviewType === "scoping"
  const canSkip = isGateMode && PROSPERO_SKIP_SUPPORTED && Boolean(onStartWithoutRegistration)
  const missingHint = !numberValid
    ? "Add a valid PROSPERO ID to continue."
    : !dateValid
      ? "Add the registration date to continue."
      : null

  function buildRegistration(): ProsperoRegistration {
    return {
      registration_number: trimmedNumber.toUpperCase(),
      registration_date: registrationDate,
    }
  }

  return (
    <div className={cn(attention && "prospero-attention-border")}>
      <PageSection
        icon={ShieldCheck}
        title="PROSPERO registration"
        action={
          isComplete ? (
            <Badge variant="success" size="sm">
              Done
            </Badge>
          ) : attention ? (
            <Badge variant="warning" size="sm">
              {isScoping && canSkip ? "Optional" : "Needed to continue"}
            </Badge>
          ) : null
        }
        contentClassName="space-y-4"
      >
        {isScoping && (
          <p className="text-xs text-muted leading-relaxed">
            Registration is required before search starts, including for scoping reviews.
            {canSkip
              ? " You can start without registering."
              : " Enter a PROSPERO-format ID (CRD42 followed by digits)."}
          </p>
        )}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <div className="flex h-5 items-center justify-between gap-2">
              <label htmlFor="prospero-id" className="text-xs font-medium text-foreground">
                PROSPERO ID
              </label>
              <a
                href="https://www.crd.york.ac.uk/prospero/"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-xs text-muted hover:text-intent-active"
              >
                Register
                <ExternalLink className="h-3.5 w-3.5" />
              </a>
            </div>
            <Input
              id="prospero-id"
              value={registrationNumber}
              onChange={(e) => setRegistrationNumber(e.target.value)}
              onBlur={() => setNumberTouched(registrationNumber.trim().length > 0)}
              placeholder="CRD42…"
              autoComplete="off"
              disabled={controlsDisabled}
              aria-invalid={numberError ? true : undefined}
              aria-describedby={numberHelpId}
            />
            <p
              id={numberHelpId}
              className={cn("text-2xs", numberError ? "text-intent-danger-text" : "text-muted")}
              role={numberError ? "alert" : undefined}
            >
              {numberError ?? PROSPERO_ID_HELPER}
            </p>
          </div>
          <div className="space-y-1.5">
            <div className="flex h-5 items-center">
              <label htmlFor="prospero-date" className="text-xs font-medium text-foreground">
                Registration date
              </label>
            </div>
            <DateInput
              id="prospero-date"
              value={registrationDate}
              onChange={(e) => setRegistrationDate(e.target.value)}
              disabled={controlsDisabled}
            />
          </div>
        </div>

        <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center sm:gap-2">
          <div className="flex min-w-0 flex-wrap items-center gap-2 sm:flex-1">
            {artifactId ? (
              <>
                <Button size="sm" variant="outline" asChild>
                  <a href={prosperoFormDocxUrl(artifactId)}>
                    <FileType className="text-intent-info" />
                    DOCX
                  </a>
                </Button>
                <Button size="sm" variant="outline" asChild>
                  <a href={prosperoFormMarkdownUrl(artifactId)}>
                    <FileCode className="text-intent-success" />
                    Markdown
                  </a>
                </Button>
                {onRegenerateDrafts ? (
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={controlsDisabled}
                    onClick={() => void onRegenerateDrafts()}
                  >
                    {isRegenerating ? <Spinner size="sm" /> : <RefreshCw />}
                    Regenerate
                  </Button>
                ) : null}
              </>
            ) : (
              <span className="inline-flex items-center gap-1.5 text-xs text-muted">
                <Download className="h-3.5 w-3.5 shrink-0" />
                Drafts appear once generated
              </span>
            )}
          </div>
          <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center sm:justify-end">
          {isGateMode && missingHint && !controlsDisabled && (
            <span className="text-2xs text-muted">{missingHint}</span>
          )}
          {canSkip && (
            <Button
              size="sm"
              variant="outline"
              className="w-full shrink-0 sm:w-auto"
              onClick={() => onStartWithoutRegistration && void onStartWithoutRegistration()}
              disabled={controlsDisabled}
            >
              Start without registration
            </Button>
          )}
          {isGateMode ? (
            <Button
              size="sm"
              className="w-full shrink-0 sm:w-auto"
              onClick={() => onStartResearch && void onStartResearch(buildRegistration())}
              disabled={!formValid || !onStartResearch}
            >
              {isSubmitting ? (
                <>
                  <Spinner size="sm" />
                  Starting...
                </>
              ) : (
                "Start research"
              )}
            </Button>
          ) : (
            <Button
              size="sm"
              className="w-full shrink-0 sm:w-auto"
              onClick={() => onSaveRegistration && void onSaveRegistration(buildRegistration())}
              disabled={!formValid || !onSaveRegistration}
            >
              {isSubmitting ? (
                <>
                  <Spinner size="sm" />
                  Saving...
                </>
              ) : (
                "Save"
              )}
            </Button>
          )}
          </div>
        </div>
      </PageSection>
    </div>
  )
}
