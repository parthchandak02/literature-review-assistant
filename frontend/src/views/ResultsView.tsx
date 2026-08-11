import { useEffect, useMemo, useState } from "react"
import {
  FileText,
  BookOpen,
  Lock,
  Image,
  ShieldCheck,
  FolderOpen,
} from "lucide-react"
import { EmptyState } from "@/components/ui/feedback"
import { CustomDiagramsCard } from "@/components/CustomDiagramsCard"
import { ArtifactFileList } from "@/components/results/ArtifactFileList"
import { ReferencesView } from "@/views/ReferencesView"
import { collectCustomDiagramItems, customDiagramPipelineTouched } from "@/lib/customDiagrams"
import { submissionZipUrl } from "@/lib/api"
import { ManuscriptViewer } from "@/components/results/ManuscriptViewer"
import { GradeSofCard } from "@/components/results/GradeSummarySection"
import { ProsperoDownloadsCard } from "@/components/results/ProsperoSection"
import { PrismaDiagramCard } from "@/components/results/PrismaSection"
import { EvidenceNetworkSection } from "@/components/results/EvidenceNetworkSection"
import {
  ResultsCategoryNav,
  type ResultsCategoryItem,
} from "@/components/results/ResultsCategoryNav"
import type { ResultsCategory } from "@/lib/resultsCategories"
import {
  buildResultsCategoryIds,
  defaultResultsCategory,
  resolveActiveResultsCategory,
  SUBMISSION_FOCUS_RESULTS_CATEGORY,
} from "@/lib/resultsCategories"
import {
  findAllFilesByExt,
  findFileByName,
} from "@/components/results/manuscriptUtils"

interface ResultsViewProps {
  outputs: Record<string, unknown>
  isDone: boolean
  runId: string
  workflowId: string | null
  historyOutputs?: Record<string, string>
  exportRunId?: string | null
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

  const hasCustomDiagrams = useMemo(
    () => collectCustomDiagramItems(effectiveOutputs).length > 0 || customDiagramPipelineTouched(effectiveOutputs),
    [effectiveOutputs],
  )

  // Paths excluded from Files list (shown in Manuscript or Figures categories)
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

  const categoryIds = useMemo(
    () =>
      buildResultsCategoryIds({
        hasManuscript: Boolean(manuscriptPath),
        hasFiguresSection: Boolean(prismaDiagramPath) || hasCustomDiagrams,
        hasExportRunId: Boolean(exportRunId),
      }),
    [manuscriptPath, prismaDiagramPath, hasCustomDiagrams, exportRunId],
  )

  const categoryItems = useMemo<ResultsCategoryItem[]>(() => {
    const byId: Record<ResultsCategory, ResultsCategoryItem> = {
      manuscript: { id: "manuscript", label: "Manuscript", icon: FileText },
      figures: { id: "figures", label: "Figures", icon: Image },
      quality: { id: "quality", label: "Quality", icon: ShieldCheck },
      files: { id: "files", label: "Files", icon: FolderOpen },
      references: { id: "references", label: "References", icon: BookOpen },
    }
    return categoryIds.map((id) => byId[id])
  }, [categoryIds])

  const [category, setCategory] = useState<ResultsCategory>(() =>
    defaultResultsCategory(Boolean(manuscriptPath)),
  )

  /* eslint-disable react-hooks/set-state-in-effect -- reset category when run/manuscript context changes */
  useEffect(() => {
    setCategory(defaultResultsCategory(Boolean(manuscriptPath)))
  }, [manuscriptPath, runId])

  useEffect(() => {
    if (submissionFocusTarget === "reference-papers") {
      setCategory(SUBMISSION_FOCUS_RESULTS_CATEGORY)
    }
  }, [submissionFocusTarget, submissionFocusToken])
  /* eslint-enable react-hooks/set-state-in-effect */

  const activeCategory = resolveActiveResultsCategory(category, categoryIds)

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
      <ResultsCategoryNav
        items={categoryItems}
        activeCategory={activeCategory}
        onCategoryChange={setCategory}
      />

      <div
        className="card-surface overflow-hidden min-h-[480px]"
        role="tabpanel"
        id={`tabpanel-${activeCategory}`}
        aria-labelledby={`tab-${activeCategory}`}
      >
        {activeCategory === "manuscript" && manuscriptPath && (
          <ManuscriptViewer
            filePath={manuscriptPath}
            docxPath={docxPath}
            canExport={canExport}
            exportRunId={exportRunId}
            allOutputs={effectiveOutputs}
          />
        )}

        {activeCategory === "figures" && (
          <div className="p-4 space-y-4">
            {prismaDiagramPath ? (
              <PrismaDiagramCard filePath={prismaDiagramPath} runId={exportRunId} />
            ) : null}
            <CustomDiagramsCard outputs={effectiveOutputs} />
            <ArtifactFileList
              outputs={effectiveOutputs}
              excludePaths={manuscriptExcludePaths}
              runId={exportRunId}
              figuresOnly
            />
          </div>
        )}

        {activeCategory === "quality" && exportRunId && (
          <div className="p-4 space-y-1">
            <GradeSofCard runId={exportRunId} />
            <EvidenceNetworkSection runId={exportRunId} />
          </div>
        )}

        {activeCategory === "files" && (
          <div className="p-4 space-y-1">
            {exportRunId ? <ProsperoDownloadsCard runId={exportRunId} /> : null}
            <ArtifactFileList
              outputs={effectiveOutputs}
              excludePaths={manuscriptExcludePaths}
              runId={exportRunId}
              hideFigures
              submissionFocusTarget={submissionFocusTarget}
              submissionFocusToken={submissionFocusToken}
            />
          </div>
        )}

        {activeCategory === "references" && (
          <div className="p-4">
            <ReferencesView
              runId={runId}
              workflowId={workflowId}
              isDone={isDone}
              embedded
            />
          </div>
        )}
      </div>
    </div>
  )
}
