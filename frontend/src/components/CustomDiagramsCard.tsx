import { useEffect, useMemo, useState } from "react"
import { AlertTriangle, ImageIcon, Sparkles } from "lucide-react"
import { CollapsibleSection } from "@/components/ui/section"
import { Spinner } from "@/components/ui/feedback"
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
  const [metaLoading, setMetaLoading] = useState(false)

  useEffect(() => {
    if (!pipelineTouched) return
    const controller = new AbortController()
    setMetaLoading(true)

    void (async () => {
      let nextBriefs: DiagramBriefEntry[] | null = null
      let nextWarnings: string[] = []

      try {
        if (briefPackPath) {
          const raw = await fetchArtifactText(briefPackPath, controller.signal)
          nextBriefs = parseDiagramBriefPack(raw)
        }
        if (reportPath) {
          const raw = await fetchArtifactText(reportPath, controller.signal)
          const report = parseDiagramGenerationReport(raw)
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
          setMetaLoading(false)
        }
      }
    })()

    return () => controller.abort()
  }, [briefPackPath, pipelineTouched, reportPath])

  if (!pipelineTouched) return null

  const expectedCount = briefs?.length ?? (reportWarnings.length > 0 ? 3 : diagrams.length)
  const hasDiagrams = diagrams.length > 0

  return (
    <CollapsibleSection
      icon={Sparkles}
      title="Custom diagrams"
      description="AI-generated figures grounded in included-study evidence"
      defaultOpen={hasDiagrams}
    >
      <div className="p-4 flex flex-col gap-4">
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
            expectedCount={expectedCount}
            warnings={reportWarnings}
          />
        )}

        {!hasDiagrams && reportPath ? (
          <p className="text-xs text-muted">
            See{" "}
            <a
              href={downloadUrl(reportPath)}
              className="text-intent-primary hover:underline"
              download
            >
              diagram generation report
            </a>{" "}
            in Artifacts for full details.
          </p>
        ) : null}
      </div>
    </CollapsibleSection>
  )
}

function DiagramFigure({ item, title }: { item: CustomDiagramItem; title: string }) {
  return (
    <figure className="rounded-xl border border-border bg-card overflow-hidden">
      <div className="px-3 py-2 border-b border-border bg-surface-1/60">
        <figcaption className="text-sm font-medium text-foreground line-clamp-2" title={title}>
          Figure {item.index}. {title}
        </figcaption>
      </div>
      <div className="p-2">
        <img
          src={downloadUrl(item.path)}
          alt={title}
          className="w-full h-auto rounded-lg"
          loading="lazy"
        />
      </div>
    </figure>
  )
}

function EmptyCustomDiagrams({
  expectedCount,
  warnings,
}: {
  expectedCount: number
  warnings: string[]
}) {
  return (
    <div className="rounded-xl border border-dashed border-border bg-surface-1/40 p-4 flex flex-col gap-3">
      <div className="flex items-start gap-2 text-sm text-muted">
        <ImageIcon className="h-4 w-4 shrink-0 mt-0.5" />
        <p>
          {expectedCount > 0
            ? `${expectedCount} custom diagram${expectedCount === 1 ? "" : "s"} were planned for this run, but no PNG outputs were saved.`
            : "No custom diagram PNGs were generated for this run."}
        </p>
      </div>
      {warnings.length > 0 ? (
        <div className="rounded-lg border border-intent-warning/30 bg-intent-warning/5 p-3">
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
        <code className="text-[11px]">GEMINI_API_KEY</code> is set and{" "}
        <code className="text-[11px]">research_diagram_drawing</code> uses a Google image model.
      </p>
    </div>
  )
}
