import { useEffect, useMemo, useState } from "react"
import { AlertTriangle, ImageIcon, Sparkles } from "lucide-react"
import { ResultsBlock } from "@/components/ui/section"
import { Spinner } from "@/components/ui/feedback"
import { FigureCard } from "@/components/results/FigureCard"
import { fetchArtifactText, downloadUrl } from "@/lib/api"
import {
  collectCustomDiagramItems,
  customDiagramPipelineTouched,
  findArtifactPath,
  parseDiagramBriefPack,
  parseDiagramGenerationReport,
  titleForCustomDiagram,
  type CustomDiagramItem,
  type DiagramBriefEntry,
} from "@/lib/customDiagrams"

interface CustomDiagramsCardProps {
  outputs: Record<string, unknown>
}

export function CustomDiagramsCard({ outputs }: CustomDiagramsCardProps) {
  const diagrams = useMemo(() => collectCustomDiagramItems(outputs), [outputs])
  const briefPackPath = useMemo(
    () => findArtifactPath(outputs, "diagram_brief_pack"),
    [outputs],
  )
  const reportPath = useMemo(
    () => findArtifactPath(outputs, "diagram_generation_report"),
    [outputs],
  )
  const pipelineTouched = useMemo(() => customDiagramPipelineTouched(outputs), [outputs])

  const [briefs, setBriefs] = useState<DiagramBriefEntry[] | null>(null)
  const [reportWarnings, setReportWarnings] = useState<string[]>([])
  const [reportResultCount, setReportResultCount] = useState<number | null>(null)
  const [metaLoading, setMetaLoading] = useState(false)

  useEffect(() => {
    if (!pipelineTouched) return
    const controller = new AbortController()
    setMetaLoading(true)

    void (async () => {
      let nextBriefs: DiagramBriefEntry[] | null = null
      let nextWarnings: string[] = []
      let nextResultCount: number | null = null

      try {
        if (briefPackPath) {
          const raw = await fetchArtifactText(briefPackPath, controller.signal)
          nextBriefs = parseDiagramBriefPack(raw)
        }
        if (reportPath) {
          const raw = await fetchArtifactText(reportPath, controller.signal)
          const report = parseDiagramGenerationReport(raw)
          if (Array.isArray(report?.results)) nextResultCount = report.results.length
          if (Array.isArray(report?.warnings)) {
            nextWarnings = report.warnings.filter((w): w is string => typeof w === "string")
          }
        }
      } catch {
        // Best-effort metadata for labels and failure hints.
      } finally {
        if (!controller.signal.aborted) {
          setBriefs(nextBriefs)
          setReportWarnings(nextWarnings)
          setReportResultCount(nextResultCount)
          setMetaLoading(false)
        }
      }
    })()

    return () => controller.abort()
  }, [briefPackPath, pipelineTouched, reportPath])

  if (!pipelineTouched) return null

  const plannedCount = briefs?.length ?? reportResultCount
  const hasDiagrams = diagrams.length > 0
  const missingCount = plannedCount != null ? Math.max(0, plannedCount - diagrams.length) : 0

  return (
    <ResultsBlock
      icon={Sparkles}
      title="Custom diagrams"
      actions={
        plannedCount != null && plannedCount > 0 ? (
          <span className="text-2xs text-muted tabular-nums">
            {diagrams.length} of {plannedCount} saved
          </span>
        ) : null
      }
    >
      <div className="flex flex-col gap-4">
        {metaLoading && !hasDiagrams ? (
          <div className="flex items-center gap-2 text-sm text-muted">
            <Spinner size="sm" />
            Loading diagram metadata…
          </div>
        ) : null}

        {hasDiagrams ? (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {diagrams.map((item) => (
              <DiagramFigure
                key={item.artifactKey}
                item={item}
                title={titleForCustomDiagram(item.index, briefs)}
              />
            ))}
          </div>
        ) : (
          <EmptyCustomDiagrams
            plannedCount={plannedCount}
            warnings={reportWarnings}
          />
        )}

        {hasDiagrams && missingCount > 0 ? (
          <p className="text-xs text-intent-warning-text">
            {missingCount} planned diagram{missingCount === 1 ? " was" : "s were"} not saved.
          </p>
        ) : null}

        {(!hasDiagrams || missingCount > 0) && reportPath ? (
          <p className="text-xs text-muted">
            See{" "}
            <a
              href={downloadUrl(reportPath)}
              className="text-intent-primary hover:underline"
              download
            >
              diagram generation report
            </a>{" "}
            in Files for full details.
          </p>
        ) : null}
      </div>
    </ResultsBlock>
  )
}

function DiagramFigure({ item, title }: { item: CustomDiagramItem; title: string }) {
  const url = downloadUrl(item.path)
  return (
    <FigureCard
      src={url}
      downloadHref={url}
      downloadName={item.path.split("/").pop() ?? `figure-${item.index}.png`}
      title={title}
      caption={`Figure ${item.index}. ${title}`}
    />
  )
}

function EmptyCustomDiagrams({
  plannedCount,
  warnings,
}: {
  plannedCount: number | null
  warnings: string[]
}) {
  return (
    <div className="rounded-panel border border-dashed border-border bg-surface-1/40 p-4 flex flex-col gap-3">
      <div className="flex items-start gap-2 text-sm text-muted">
        <ImageIcon className="h-4 w-4 shrink-0 mt-0.5" />
        <p>
          {plannedCount != null && plannedCount > 0
            ? `${plannedCount} custom diagram${plannedCount === 1 ? " was" : "s were"} planned for this run, but no PNG outputs were saved.`
            : "No custom diagram PNGs were generated for this run."}
        </p>
      </div>
      {warnings.length > 0 ? (
        <div className="rounded-lg border border-intent-warning-border bg-intent-warning-subtle p-3">
          <div className="flex items-center gap-2 text-xs font-medium text-intent-warning mb-2">
            <AlertTriangle className="h-3.5 w-3.5" />
            Generation issues
          </div>
          <ul className="text-xs text-muted space-y-1 list-disc pl-4">
            {warnings.slice(0, 6).map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </div>
      ) : null}
      <p className="text-xs text-muted">
        Resume the workflow from the writing phase after confirming{" "}
        <code className="text-2xs">GEMINI_API_KEY</code> is set and{" "}
        <code className="text-2xs">research_diagram_drawing</code> uses a Google image model.
      </p>
    </div>
  )
}
