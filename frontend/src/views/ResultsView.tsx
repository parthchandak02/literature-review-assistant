import { useEffect, useMemo, useState } from "react"
import { FileText, BookOpen, Download, Lock } from "lucide-react"
import { Button } from "@/components/ui/button"
import { EmptyState } from "@/components/ui/feedback"
import { CollapsibleSection } from "@/components/ui/section"
import { CustomDiagramsCard } from "@/components/CustomDiagramsCard"
import { ResultsPanel } from "@/components/ResultsPanel"
import { ReferencesView } from "@/views/ReferencesView"
import { collectCustomDiagramItems } from "@/lib/customDiagrams"
import { submissionZipUrl } from "@/lib/api"
import { ManuscriptViewer } from "@/components/results/ManuscriptViewer"
import { ManuscriptActions } from "@/components/results/ManuscriptActions"
import { GradeSofCard } from "@/components/results/GradeSummarySection"
import { ProsperoDownloadsCard } from "@/components/results/ProsperoSection"
import { PrismaDiagramCard } from "@/components/results/PrismaSection"
import { EvidenceNetworkSection } from "@/components/results/EvidenceNetworkSection"
import {
  findAllFilesByExt,
  findFileByName,
  hasSubmissionArtifacts,
} from "@/components/results/manuscriptUtils"

interface ResultsViewProps {
  outputs: Record<string, unknown>
  isDone: boolean
  runId: string
  workflowId: string | null
  historyOutputs?: Record<string, string>
  exportRunId?: string | null
  onGoToSubmissionReferencePapers?: () => void
  submissionFocusTarget?: "reference-papers" | null
  submissionFocusToken?: number
}

export function ResultsView({
  outputs,
  isDone,
  runId,
  workflowId,
  historyOutputs = {},
  exportRunId,
  onGoToSubmissionReferencePapers,
  submissionFocusTarget = null,
  submissionFocusToken = 0,
}: ResultsViewProps) {
  const effectiveOutputs = useMemo<Record<string, unknown>>(() => {
    const base =
      Object.keys(outputs).length > 0
        ? outputs
        : Object.keys(historyOutputs).length > 0
          ? { artifacts: historyOutputs }
          : {}
    if (exportRunId && Object.keys(base).length > 0) {
      return {
        ...base,
        submission_zip: submissionZipUrl(exportRunId),
      }
    }
    return base
  }, [outputs, historyOutputs, exportRunId])

  const isHistorical = !isDone && Object.keys(historyOutputs).length > 0
  const hasResults = isDone || isHistorical
  const canExport = exportRunId != null && hasResults
  const [artifactsOpen, setArtifactsOpen] = useState(false)
  const [referencesOpen, setReferencesOpen] = useState(false)
  const [submissionReady, setSubmissionReady] = useState(false)

  const manuscriptPath = useMemo(
    () => findFileByName(effectiveOutputs, "doc_manuscript"),
    [effectiveOutputs],
  )

  const docxPath = useMemo(
    () => findFileByName(effectiveOutputs, ".docx"),
    [effectiveOutputs],
  )

  const prismaDiagramPath = useMemo(() => {
    const imagePaths = findAllFilesByExt(effectiveOutputs, [".png", ".svg", ".jpg", ".jpeg", ".webp"])
    const customPaths = new Set(collectCustomDiagramItems(effectiveOutputs).map((d) => d.path))
    return (
      imagePaths.find((path) => /prisma|flow/i.test(path) && !customPaths.has(path)) ?? null
    )
  }, [effectiveOutputs])

  const customDiagramPaths = useMemo(
    () => collectCustomDiagramItems(effectiveOutputs).map((d) => d.path),
    [effectiveOutputs],
  )

  // Paths to exclude from Artifacts panel (they live in the left panel header actions)
  const manuscriptExcludePaths = useMemo<Set<string>>(() => {
    const paths = new Set<string>()
    if (manuscriptPath) paths.add(manuscriptPath)
    if (docxPath) paths.add(docxPath)
    const texFiles = findAllFilesByExt(effectiveOutputs, [".tex"])
    texFiles.forEach((p) => paths.add(p))
    customDiagramPaths.forEach((p) => paths.add(p))
    if (prismaDiagramPath) paths.add(prismaDiagramPath)
    return paths
  }, [effectiveOutputs, manuscriptPath, docxPath, customDiagramPaths, prismaDiagramPath])

  useEffect(() => {
    setSubmissionReady(hasSubmissionArtifacts(effectiveOutputs))
  }, [effectiveOutputs])

  useEffect(() => {
    if (submissionFocusTarget && !artifactsOpen) {
      setArtifactsOpen(true)
    }
  }, [submissionFocusTarget, submissionFocusToken, artifactsOpen])

  if (!hasResults) {
    return (
      <EmptyState
        icon={Lock}
        heading="Results available once the review completes."
        sub="Switch to the Activity tab to monitor progress."
        className="h-64"
      />
    )
  }

  if (Object.keys(effectiveOutputs).length === 0) {
    return (
      <EmptyState
        icon={FileText}
        heading="No output files found."
        className="h-64"
      />
    )
  }

  return (
    <div className="flex flex-col gap-3 min-h-[520px]">
      {manuscriptPath && (
        <CollapsibleSection
          icon={FileText}
          title="Manuscript"
          defaultOpen={false}
          actions={
            <ManuscriptActions
              docxPath={docxPath}
              canExport={canExport}
              exportRunId={exportRunId}
              allOutputs={effectiveOutputs}
              onExportReadyChange={setSubmissionReady}
            />
          }
        >
          <ManuscriptViewer filePath={manuscriptPath} />
        </CollapsibleSection>
      )}

      <CollapsibleSection
        icon={FileText}
        title="Artifacts"
        description="Protocol, data files, figures, quality summaries"
        open={artifactsOpen}
        onToggle={() => setArtifactsOpen((v) => !v)}
        actions={
          exportRunId ? (
            submissionReady ? (
              <Button
                size="sm"
                asChild
                className="h-7 gap-1 text-xs bg-intent-success hover:bg-intent-success text-intent-success-fg border-0 shadow-none"
              >
                <a href={submissionZipUrl(exportRunId)} download>
                  <Download className="h-3 w-3" />
                  Submission Package
                </a>
              </Button>
            ) : (
              <Button
                size="sm"
                disabled
                className="h-7 gap-1 text-xs bg-surface-2 text-muted border-0 shadow-none cursor-not-allowed"
                title="Run manuscript export first"
              >
                <Download className="h-3 w-3" />
                Submission Package
              </Button>
            )
          ) : null
        }
      >
        <div className="p-4 space-y-3">
          {prismaDiagramPath ? <PrismaDiagramCard filePath={prismaDiagramPath} /> : null}

          <CustomDiagramsCard outputs={effectiveOutputs} />

          {exportRunId ? <GradeSofCard runId={exportRunId} /> : null}

          {exportRunId ? <ProsperoDownloadsCard runId={exportRunId} /> : null}

          {exportRunId ? <EvidenceNetworkSection runId={exportRunId} /> : null}

          <ResultsPanel
            outputs={effectiveOutputs}
            excludePaths={manuscriptExcludePaths}
            runId={exportRunId}
            submissionFocusTarget={submissionFocusTarget}
            submissionFocusToken={submissionFocusToken}
          />
        </div>
      </CollapsibleSection>

      <CollapsibleSection
        icon={BookOpen}
        title="References"
        description="Included studies and source files"
        open={referencesOpen}
        onToggle={() => setReferencesOpen((v) => !v)}
      >
        <div className="p-4">
          <ReferencesView
            runId={runId}
            workflowId={workflowId}
            isDone={isDone}
            onGoToSubmissionReferencePapers={onGoToSubmissionReferencePapers}
          />
        </div>
      </CollapsibleSection>
    </div>
  )
}
