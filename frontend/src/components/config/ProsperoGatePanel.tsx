import { useMemo, useState } from "react"
import { Download, ExternalLink, FileCode, FileType, ShieldCheck } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { PageSection } from "@/components/ui/section"
import { Spinner } from "@/components/ui/feedback"
import { prosperoFormDocxUrl, prosperoFormMarkdownUrl } from "@/lib/api"
import type { ProsperoRegistration } from "@/lib/api"
import { isProsperoRegistrationNumberValid } from "@/lib/constants"
import { RESULTS_DOWNLOAD_BTN_CLS } from "@/components/results/resultsShared"

export interface ProsperoGatePanelProps {
  runId: string | null
  workflowId?: string | null
  disabled?: boolean
  isSubmitting?: boolean
  onStartResearch: (registration: ProsperoRegistration) => void | Promise<void>
}

export function ProsperoGatePanel({
  runId,
  workflowId = null,
  disabled = false,
  isSubmitting = false,
  onStartResearch,
}: ProsperoGatePanelProps) {
  const [registrationNumber, setRegistrationNumber] = useState("")
  const [registrationDate, setRegistrationDate] = useState("")

  const trimmedNumber = registrationNumber.trim()
  const numberValid = isProsperoRegistrationNumberValid(trimmedNumber)
  const dateValid = registrationDate.length > 0
  const canStart = numberValid && dateValid && !disabled && !isSubmitting
  const artifactId = workflowId ?? runId

  const numberHint = useMemo(() => {
    if (!trimmedNumber) return "Enter your PROSPERO ID (for example, CRD42025678901)."
    if (!numberValid) return "Use CRD followed by at least 9 digits."
    return null
  }, [trimmedNumber, numberValid])

  return (
    <PageSection
      icon={ShieldCheck}
      title="PROSPERO Registration Required"
      description="Complete before research starts"
      contentClassName="space-y-4"
    >
      <div className="space-y-2 text-sm text-foreground leading-relaxed">
        <p>
          Download the generated PROSPERO draft, register your review on{" "}
          <a
            href="https://www.crd.york.ac.uk/prospero/"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-intent-active hover:underline"
          >
            PROSPERO
            <ExternalLink className="h-3.5 w-3.5" />
          </a>
          , then enter your registration ID and date below.
        </p>
        <p className="text-muted text-xs">
          Research phases (search, screening, extraction) start only after registration is confirmed.
        </p>
      </div>

      {artifactId ? (
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="outline" asChild className={RESULTS_DOWNLOAD_BTN_CLS}>
            <a href={prosperoFormDocxUrl(artifactId)}>
              <FileType className="h-3 w-3 text-intent-info" />
              PROSPERO DOCX
            </a>
          </Button>
          <Button size="sm" variant="outline" asChild className={RESULTS_DOWNLOAD_BTN_CLS}>
            <a href={prosperoFormMarkdownUrl(artifactId)}>
              <FileCode className="h-3 w-3 text-intent-success" />
              PROSPERO Markdown
            </a>
          </Button>
        </div>
      ) : (
        <div className="rounded-md border border-border/70 bg-card/60 px-3 py-2 text-xs text-muted inline-flex items-center gap-2">
          <Download className="h-3.5 w-3.5 shrink-0" />
          PROSPERO draft downloads appear once the draft is generated.
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <label className="space-y-1.5">
          <span className="text-xs font-medium text-foreground">PROSPERO ID</span>
          <Input
            value={registrationNumber}
            onChange={(e) => setRegistrationNumber(e.target.value)}
            placeholder="CRD42025678901"
            autoComplete="off"
            disabled={disabled || isSubmitting}
          />
          {numberHint && <span className="text-[11px] text-muted">{numberHint}</span>}
        </label>
        <label className="space-y-1.5">
          <span className="text-xs font-medium text-foreground">Registration date</span>
          <Input
            type="date"
            value={registrationDate}
            onChange={(e) => setRegistrationDate(e.target.value)}
            disabled={disabled || isSubmitting}
          />
        </label>
      </div>

      <div className="flex items-center justify-end gap-2 pt-1">
        <Button
          onClick={() =>
            void onStartResearch({
              registration_number: trimmedNumber.toUpperCase(),
              registration_date: registrationDate,
            })
          }
          disabled={!canStart}
        >
          {isSubmitting ? (
            <>
              <Spinner size="sm" className="mr-2" />
              Starting research...
            </>
          ) : (
            "Start Research"
          )}
        </Button>
      </div>
    </PageSection>
  )
}
