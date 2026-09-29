import { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { EmptyState } from "@/components/ui/feedback"
import { Download, FileText } from "lucide-react"
import { studyFilesZipUrl } from "@/lib/api"
import { cn } from "@/lib/utils"
import { FilePreview } from "./FilePreview"
import { FigureCard } from "./FigureCard"
import {
  type OutputFile,
  type DocGroup,
  REFERENCE_PAPERS_ZIP_KEY,
  FLAT_DOC_GROUPS,
  collectFiles,
  fileGroupKey,
  fileIcon,
  isFigurePath,
  isPreviewableFile,
  resolveFileUrl,
} from "./artifactFileUtils"
import { RESULTS_DOWNLOAD_BTN_CLS } from "./resultsShared"

export interface ArtifactFileListProps {
  outputs: Record<string, unknown>
  /** File paths already rendered elsewhere that should not appear in this panel. */
  excludePaths?: Set<string>
  /** run_id used for Reference papers only ZIP synthetic row. */
  runId?: string | null
  /** Optional highlight target for deep-linking into Submission Files. */
  submissionFocusTarget?: "reference-papers" | null
  submissionFocusToken?: number
  /** When true, only render figure rows (no document groups). */
  figuresOnly?: boolean
  /** When true, skip the Figures section (document groups only). */
  hideFigures?: boolean
  /** When true, drop PROSPERO registration docs (a dedicated downloads card already lists them). */
  hideProsperoRegistration?: boolean
}

const PROSPERO_REGISTRATION_RE = /(^|\/)doc_prospero_registration\.[a-z]+$/i

function FileLabel({ file }: { file: OutputFile }) {
  const showFileName = file.fileName && file.fileName !== file.label
  return (
    <span className="flex min-w-0 flex-col" title={file.fileName ?? file.label}>
      <span className="text-sm text-foreground [overflow-wrap:anywhere]">{file.label}</span>
      {showFileName && <span className="truncate font-mono text-2xs text-muted">{file.fileName}</span>}
    </span>
  )
}

function FileRow({ file }: { file: OutputFile }) {
  const { icon: Icon, className: iconClass } = fileIcon(file)
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="flex items-center gap-2 min-w-0">
        <Icon className={`h-4 w-4 shrink-0 ${iconClass}`} />
        <FileLabel file={file} />
      </span>
      <Button size="sm" variant="outline" asChild className={`shrink-0 ${RESULTS_DOWNLOAD_BTN_CLS}`}>
        <a href={resolveFileUrl(file.path)} download={file.fileName ?? file.label} className="gap-1.5">
          <Download className="h-3.5 w-3.5" />
          Download
        </a>
      </Button>
    </div>
  )
}

function SelectableDocRow({
  file,
  selected,
  onSelect,
}: {
  file: OutputFile
  selected: boolean
  onSelect: (file: OutputFile) => void
}) {
  const { icon: Icon, className: iconClass } = fileIcon(file)
  return (
    <div
      className={cn(
        "flex items-center justify-between gap-2 rounded-md -mx-2 pr-2 transition-colors",
        selected
          ? "bg-intent-primary-subtle ring-1 ring-intent-primary-border"
          : "hover:bg-surface-2/60",
      )}
    >
      <button
        type="button"
        aria-pressed={selected}
        onClick={() => onSelect(file)}
        title={selected ? `Hide preview of ${file.label}` : `Preview ${file.label}`}
        className="flex flex-1 items-center gap-2 min-w-0 rounded-md px-2 py-1.5 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <Icon className={`h-4 w-4 shrink-0 ${iconClass}`} />
        <FileLabel file={file} />
      </button>
      <Button size="sm" variant="outline" asChild className={`shrink-0 ${RESULTS_DOWNLOAD_BTN_CLS}`}>
        <a
          href={resolveFileUrl(file.path)}
          download={file.fileName ?? file.label}
          className="gap-1.5"
          aria-label={`Download ${file.label}`}
        >
          <Download className="h-3.5 w-3.5" />
          Download
        </a>
      </Button>
    </div>
  )
}

function FigureFileCard({ file }: { file: OutputFile }) {
  const { icon: Icon, className: iconClass } = fileIcon(file)
  const url = resolveFileUrl(file.path)
  return (
    <FigureCard
      src={url}
      downloadHref={url}
      downloadName={file.fileName ?? file.label}
      title={file.label}
      icon={<Icon className={`h-4 w-4 shrink-0 ${iconClass}`} />}
      showImage={file.isRasterImage}
    />
  )
}

function buildGroupedDocs(
  docs: OutputFile[],
  runId: string | null,
): Record<DocGroup, OutputFile[]> {
  const groupedDocs = docs.reduce<Record<DocGroup, OutputFile[]>>(
    (acc, f) => {
      const g = fileGroupKey(f)
      acc[g].push(f)
      return acc
    },
    { manuscript: [], protocol: [], submission: [], data: [] },
  )
  if (runId) {
    const refZipPath = studyFilesZipUrl(runId)
    const hasRow = groupedDocs.submission.some((f) => f.path === refZipPath)
    if (!hasRow) {
      groupedDocs.submission.unshift({
        key: REFERENCE_PAPERS_ZIP_KEY,
        path: refZipPath,
        label: "Reference papers only (ZIP)",
        fileName: "studies-files.zip",
        isRasterImage: false,
        isLatex: false,
        isMarkdown: false,
        isJson: false,
        isCsv: false,
      })
    }
  }
  return groupedDocs
}

function DocGroupsList({
  groupedDocs,
  selectedKey,
  onSelect,
  figsCount,
}: {
  groupedDocs: Record<DocGroup, OutputFile[]>
  selectedKey: string | null
  onSelect: (file: OutputFile) => void
  figsCount: number
}) {
  const hasAnyDocs = FLAT_DOC_GROUPS.some((g) => groupedDocs[g.key].length > 0)
  if (!hasAnyDocs) return null

  return (
    <>
      {FLAT_DOC_GROUPS.map(({ key, label }, idx) => {
        let groupFiles = [...groupedDocs[key]]
        if (key === "submission") {
          groupFiles = groupFiles.filter((f) => !/(^|\/)submission\.zip$/i.test(f.path))
        }
        if (key === "submission") {
          groupFiles.sort((a, b) => {
            if (a.key === REFERENCE_PAPERS_ZIP_KEY) return -1
            if (b.key === REFERENCE_PAPERS_ZIP_KEY) return 1
            return a.label.localeCompare(b.label)
          })
        }
        if (groupFiles.length === 0) return null
        const isLast = idx === FLAT_DOC_GROUPS.filter((g) => groupedDocs[g.key].length > 0).length - 1
        return (
          <div key={key} className={isLast && figsCount === 0 ? "" : "pb-4 mb-4 border-b border-border/60"}>
            <p className="label-caps pb-2">{label}</p>
            <div className="flex flex-col gap-1">
              {groupFiles.map((f) => (
                <div key={f.key} data-download-key={f.key}>
                  {isPreviewableFile(f) ? (
                    <SelectableDocRow
                      file={f}
                      selected={selectedKey === f.key}
                      onSelect={onSelect}
                    />
                  ) : (
                    <FileRow file={f} />
                  )}
                </div>
              ))}
            </div>
          </div>
        )
      })}
    </>
  )
}

export function ArtifactFileList({
  outputs,
  excludePaths,
  runId = null,
  submissionFocusTarget = null,
  submissionFocusToken = 0,
  figuresOnly = false,
  hideFigures = false,
  hideProsperoRegistration = false,
}: ArtifactFileListProps) {
  const [selectedFile, setSelectedFile] = useState<OutputFile | null>(null)

  const allFiles = collectFiles(outputs)
  const files = allFiles.filter(
    (f) =>
      !excludePaths?.has(f.path)
      && !(hideProsperoRegistration && PROSPERO_REGISTRATION_RE.test(f.path)),
  )
  const docs = files.filter((f) => !f.isRasterImage && !isFigurePath(f.path))
  const figs = files.filter((f) => isFigurePath(f.path))
  const previewableDocs = docs.filter(isPreviewableFile)
  const hasPreviewPane = previewableDocs.length > 0

  useEffect(() => {
    if (submissionFocusTarget !== "reference-papers") return
    const targetKey = REFERENCE_PAPERS_ZIP_KEY
    const highlightClasses = ["ring-1", "ring-intent-primary-border", "bg-intent-primary-subtle", "p-1", "rounded-md"]
    const raf = window.requestAnimationFrame(() => {
      const el = document.querySelector(`[data-download-key="${targetKey}"]`)
      if (el instanceof HTMLElement) {
        el.scrollIntoView({ behavior: "smooth", block: "center" })
        el.classList.add(...highlightClasses)
      }
    })
    const timeout = window.setTimeout(() => {
      const el = document.querySelector(`[data-download-key="${targetKey}"]`)
      if (el instanceof HTMLElement) {
        el.classList.remove(...highlightClasses)
      }
    }, 2500)
    return () => {
      window.clearTimeout(timeout)
      window.cancelAnimationFrame(raf)
    }
  }, [submissionFocusTarget, submissionFocusToken])

  const handleSelect = (file: OutputFile) => {
    setSelectedFile((prev) => (prev?.key === file.key ? null : file))
  }

  if (files.length === 0) {
    return <EmptyState icon={FileText} heading="No output files to display." className="py-16" />
  }

  if (figuresOnly) {
    if (figs.length === 0) {
      return <EmptyState icon={FileText} heading="No figures in this run." className="py-10" />
    }
    return (
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {figs.map((f) => (
          <FigureFileCard key={f.key} file={f} />
        ))}
      </div>
    )
  }

  const groupedDocs = buildGroupedDocs(docs, runId)

  const listContent = (
    <div className="flex flex-col gap-0">
      <DocGroupsList
        groupedDocs={groupedDocs}
        selectedKey={selectedFile?.key ?? null}
        onSelect={handleSelect}
        figsCount={hideFigures ? 0 : figs.length}
      />

      {!hideFigures && figs.length > 0 && (
        <div>
          <p className="label-caps pb-2">Figures</p>
          <div className="grid gap-3 sm:grid-cols-2">
            {figs.map((f) => (
              <FigureFileCard key={f.key} file={f} />
            ))}
          </div>
        </div>
      )}
    </div>
  )

  if (!hasPreviewPane) {
    return listContent
  }

  return (
    <div className="grid grid-cols-1 gap-4 min-h-[400px] lg:grid-cols-[minmax(18rem,26rem)_minmax(0,1fr)]">
      <div className="flex flex-col min-w-0 lg:max-h-[70vh] lg:overflow-y-auto lg:pr-1">
        {listContent}
      </div>
      <div className="min-w-0 lg:border-l lg:border-border lg:pl-4">
        <FilePreview file={selectedFile} />
      </div>
    </div>
  )
}
