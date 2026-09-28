import type { ReactNode } from "react"
import { ExternalLink } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { FetchError, LoadingPane } from "@/components/ui/feedback"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import { useDbPaperDetail } from "@/hooks/useDbPapers"
import type { PaperDetail, PaperScreeningStage } from "@/lib/api/db"
import { confidenceToVariant, screeningDecisionToVariant } from "@/lib/constants"
import { decodeHtmlEntities, humanizeSnake, humanizeSource, humanizeStage } from "@/lib/humanize"
import { PRIMARY_STATUS_VARIANT, paperLink } from "./paperColumns"

export interface PaperInspectorProps {
  runId: string
  paperId: string | null
  onOpenChange: (open: boolean) => void
}

export function PaperInspector({ runId, paperId, onOpenChange }: PaperInspectorProps) {
  const query = useDbPaperDetail(runId, paperId)
  const detail = query.data
  return (
    <Sheet open={Boolean(paperId)} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full max-w-xl gap-5 sm:max-w-xl">
        <SheetHeader>
          <SheetTitle className="leading-snug">
            {detail ? decodeHtmlEntities(detail.title) : "Paper details"}
          </SheetTitle>
          <SheetDescription className="text-xs">
            {detail ? paperByline(detail) : "Full record for the selected paper."}
          </SheetDescription>
        </SheetHeader>
        {query.isLoading ? (
          <LoadingPane message="Loading paper…" className="h-40" />
        ) : query.isError ? (
          <FetchError
            message={query.error instanceof Error ? query.error.message : String(query.error)}
            onRetry={() => void query.refetch()}
          />
        ) : detail ? (
          <PaperDetailBody detail={detail} />
        ) : null}
      </SheetContent>
    </Sheet>
  )
}

function paperByline(detail: PaperDetail): string {
  const authors = detail.authors.map((a) => decodeHtmlEntities(a))
  const shown = authors.length > 3 ? `${authors.slice(0, 3).join(", ")} et al.` : authors.join(", ")
  return [shown, detail.year, detail.journal].filter(Boolean).join(" · ")
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="grid gap-1.5">
      <h3 className="label-caps">{title}</h3>
      {children}
    </section>
  )
}

function Field({ label, value }: { label: string; value: ReactNode }) {
  if (value == null || value === "") return null
  return (
    <div className="grid grid-cols-[8rem_1fr] gap-2 text-xs">
      <dt className="text-muted">{label}</dt>
      <dd className="min-w-0 break-words text-foreground">{value}</dd>
    </div>
  )
}

function PaperDetailBody({ detail }: { detail: PaperDetail }) {
  const href = paperLink(detail)
  return (
    <div className="grid gap-5">
      <Section title="Record">
        <dl className="grid gap-1">
          <Field label="Authors" value={detail.authors.map((a) => decodeHtmlEntities(a)).join(", ")} />
          <Field label="Year" value={detail.year != null && <span className="font-mono tabular-nums">{detail.year}</span>} />
          <Field label="Journal" value={detail.journal} />
          <Field label="Source" value={humanizeSource(detail.source_database)} />
          <Field label="Country" value={detail.country} />
          <Field
            label={detail.doi ? "DOI" : "Link"}
            value={
              href && (
                <a
                  href={href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 break-all text-intent-primary-text underline-offset-2 hover:underline"
                >
                  {detail.doi ?? href}
                  <ExternalLink className="h-3 w-3 shrink-0" />
                </a>
              )
            }
          />
          <Field label="Keywords" value={detail.keywords.length ? detail.keywords.join(", ") : null} />
        </dl>
      </Section>

      <Section title="Abstract">
        {detail.abstract ? (
          <p className="max-w-prose whitespace-pre-line text-sm leading-relaxed text-foreground">
            {detail.abstract}
          </p>
        ) : (
          <p className="text-xs text-muted">No abstract on record.</p>
        )}
      </Section>

      <Section title="Screening">
        {detail.screening.length === 0 ? (
          <p className="text-xs text-muted">Not screened yet.</p>
        ) : (
          <div className="grid gap-3">
            {detail.screening.map((stage) => (
              <ScreeningStage key={stage.stage} stage={stage} />
            ))}
          </div>
        )}
      </Section>

      {detail.extraction && (
        <Section title="Extraction">
          <dl className="grid gap-1">
            <Field label="Study design" value={humanizeSnake(detail.extraction.study_design)} />
            <Field
              label="Primary status"
              value={
                detail.extraction.primary_study_status && (
                  <Badge
                    size="sm"
                    variant={PRIMARY_STATUS_VARIANT[detail.extraction.primary_study_status] ?? "neutral"}
                  >
                    {humanizeSnake(detail.extraction.primary_study_status)}
                  </Badge>
                )
              }
            />
            <Field
              label="Confidence"
              value={
                detail.extraction.extraction_confidence != null && (
                  <Badge
                    size="sm"
                    variant={confidenceToVariant(detail.extraction.extraction_confidence)}
                    className="font-mono tabular-nums"
                  >
                    {Math.round(detail.extraction.extraction_confidence * 100)}%
                  </Badge>
                )
              }
            />
            <Field label="Text source" value={humanizeSnake(detail.extraction.extraction_source)} />
            <Field
              label="Participants"
              value={
                detail.extraction.participant_count != null && (
                  <span className="font-mono tabular-nums">
                    {detail.extraction.participant_count.toLocaleString()}
                  </span>
                )
              }
            />
            <Field label="Setting" value={detail.extraction.setting} />
            <Field label="Duration" value={detail.extraction.study_duration} />
            <Field label="Intervention" value={detail.extraction.intervention_description} />
            <Field label="Comparator" value={detail.extraction.comparator_description} />
            <Field
              label="Outcomes"
              value={<span className="font-mono tabular-nums">{detail.extraction.outcome_count}</span>}
            />
            <Field label="Funding" value={detail.extraction.funding_source} />
          </dl>
          {detail.extraction.results_summary &&
            Object.keys(detail.extraction.results_summary).length > 0 && (
              <dl className="mt-1 grid gap-1">
                {Object.entries(detail.extraction.results_summary).map(([k, v]) => (
                  <Field key={k} label={humanizeSnake(k)} value={v} />
                ))}
              </dl>
            )}
        </Section>
      )}

      {detail.quality && (
        <Section title="Quality">
          <dl className="grid gap-1">
            <Field label="Tool" value={detail.quality.tool_used} />
            <Field label="Overall" value={humanizeSnake(detail.quality.overall_judgment)} />
            <Field
              label="Assessed by"
              value={
                detail.quality.assessment_source && (
                  <Badge size="sm" variant={detail.quality.assessment_source === "heuristic" ? "warning" : "neutral"}>
                    {humanizeSnake(detail.quality.assessment_source)}
                  </Badge>
                )
              }
            />
          </dl>
        </Section>
      )}
    </div>
  )
}

function ScreeningStage({ stage }: { stage: PaperScreeningStage }) {
  return (
    <div className="grid gap-1.5 rounded-control border border-border p-2.5">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-medium text-foreground">{humanizeStage(stage.stage)}</span>
        {stage.final_decision ? (
          <Badge size="sm" variant={screeningDecisionToVariant(stage.final_decision)}>
            {humanizeSnake(stage.final_decision)}
          </Badge>
        ) : (
          <span className="text-2xs text-muted">No final decision</span>
        )}
      </div>
      {stage.adjudication_needed && (
        <span className="text-2xs text-intent-warning-text">Reviewers disagreed; adjudicated.</span>
      )}
      {stage.decisions.length > 0 && (
        <ul className="grid gap-1.5">
          {stage.decisions.map((d, i) => (
            <li key={`${d.reviewer_type}-${i}`} className="grid gap-0.5 text-xs">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-muted">{humanizeSnake(d.reviewer_type)}</span>
                <Badge size="sm" variant={screeningDecisionToVariant(d.decision)}>
                  {humanizeSnake(d.decision)}
                </Badge>
                {d.confidence != null && (
                  <span className="font-mono text-2xs tabular-nums text-muted">
                    {Math.round(d.confidence * 100)}%
                  </span>
                )}
                {d.exclusion_reason && (
                  <span className="text-2xs text-muted">{humanizeSnake(d.exclusion_reason)}</span>
                )}
              </div>
              {d.reason && <p className="leading-relaxed text-foreground">{d.reason}</p>}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
