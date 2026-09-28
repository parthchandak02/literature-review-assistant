import { useMemo } from "react"
import { AlertTriangle, Download, FileCode, FileType, Package, RefreshCw } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Spinner } from "@/components/ui/feedback"
import { downloadUrl, submissionZipUrl } from "@/lib/api"
import { findFileByName, hasCompleteSubmission, hasPartialSubmission } from "./manuscriptUtils"
import { PackageBuildConfirm } from "./PackageBuildConfirm"
import { RESULTS_DOWNLOAD_BTN_CLS } from "./resultsShared"
import {
  PACKAGE_ACTION_LABEL,
  primaryPackageAction,
  rebuildNeedsConfirm,
  usePackageBuildGuard,
  useSubmissionPackage,
  type PackageAction,
} from "./submissionPackage"

interface ManuscriptActionsProps {
  docxPath: string | null
  canExport: boolean
  exportRunId: string | null | undefined
  allOutputs: Record<string, unknown>
}

export function ManuscriptActions({
  docxPath,
  canExport,
  exportRunId,
  allOutputs,
}: ManuscriptActionsProps) {
  const complete = useMemo(() => hasCompleteSubmission(allOutputs), [allOutputs])
  const partial = useMemo(() => hasPartialSubmission(allOutputs), [allOutputs])
  const { state, run } = useSubmissionPackage(exportRunId, { complete, partial })
  const buildGuard = usePackageBuildGuard(exportRunId)
  const prefix = exportRunId ?? "manuscript"
  const action = primaryPackageAction(state.status)

  const mergedOutputs = useMemo<Record<string, unknown>>(() => {
    if (state.files.length === 0) return allOutputs
    const submission: Record<string, string> = {}
    for (const filePath of state.files) {
      const name = filePath.split("/").pop() ?? filePath
      submission[name] = filePath
    }
    return { ...allOutputs, submission }
  }, [allOutputs, state.files])

  const texPath = useMemo(() => {
    const submissionTex = state.files.find((f) => /\/manuscript\.tex$/.test(f))
    return submissionTex ?? findFileByName(mergedOutputs, "manuscript.tex")
  }, [mergedOutputs, state.files])
  const mergedDocxPath = useMemo(
    () => findFileByName(mergedOutputs, ".docx") ?? docxPath,
    [mergedOutputs, docxPath],
  )

  const ready = state.status === "ready"
  const sharedCls = RESULTS_DOWNLOAD_BTN_CLS

  const checking = buildGuard.checking

  function requestBuild(buildAction: Exclude<PackageAction, "download">) {
    if (checking || state.status === "building") return
    const overwrite = buildAction === "rebuild" && rebuildNeedsConfirm(state.status)
    void buildGuard.guard(() => void run(buildAction), { overwrite })
  }

  return (
    <div className="flex items-center gap-1.5">
      {state.status === "building" && (
        <Button size="sm" variant="outline" disabled aria-busy className={sharedCls}>
          <Spinner size="sm" />
          Building…
        </Button>
      )}

      {canExport && action === "build" && (
        <Button
          size="sm"
          variant="outline"
          onClick={() => requestBuild("build")}
          disabled={checking}
          aria-busy={checking || undefined}
          className={sharedCls}
          title="Build the submission package (.tex, .docx, references, study PDFs)"
        >
          <Package className="h-3 w-3" />
          {PACKAGE_ACTION_LABEL.build}
        </Button>
      )}

      {canExport && action === "rebuild" && (
        <Button
          size="sm"
          variant="outline"
          onClick={() => requestBuild("rebuild")}
          disabled={checking}
          aria-busy={checking || undefined}
          className={sharedCls}
          title="The submission package is incomplete. Rebuild it from the current manuscript."
        >
          <RefreshCw className="h-3 w-3" />
          {PACKAGE_ACTION_LABEL.rebuild}
        </Button>
      )}

      {canExport && action === "retry" && (
        <Button
          size="sm"
          variant="outline"
          onClick={() => requestBuild("retry")}
          disabled={checking}
          aria-busy={checking || undefined}
          className={sharedCls}
          title={state.error ?? "Retry building the submission package"}
        >
          <AlertTriangle className="h-3 w-3 text-intent-danger" />
          {PACKAGE_ACTION_LABEL.retry}
        </Button>
      )}

      {(ready || mergedDocxPath) && (
        <>
          {texPath && (
            <Button size="sm" variant="outline" asChild className={sharedCls}>
              <a href={downloadUrl(texPath)} download={`${prefix}-manuscript.tex`}>
                <FileCode className="h-3 w-3" />
                .tex
              </a>
            </Button>
          )}
          {exportRunId && (
            <Button size="sm" variant="outline" asChild className={sharedCls}>
              <a href={`/api/run/${exportRunId}/manuscript.docx`}>
                <FileType className="h-3 w-3 text-intent-info" />
                DOCX
              </a>
            </Button>
          )}
        </>
      )}

      {exportRunId && ready && (
        <>
          <Button size="xs" variant="success" asChild className="gap-1 border-0 shadow-none">
            <a href={submissionZipUrl(exportRunId)} download title="Download the submission package (.zip)">
              <Download className="h-3 w-3" />
              Submission package
            </a>
          </Button>
          {canExport && (
            <Button
              type="button"
              size="icon-sm"
              variant="ghost"
              onClick={() => requestBuild("rebuild")}
              disabled={checking}
              aria-label={PACKAGE_ACTION_LABEL.rebuild}
              title={PACKAGE_ACTION_LABEL.rebuild}
            >
              <RefreshCw />
            </Button>
          )}
        </>
      )}

      <PackageBuildConfirm prompt={buildGuard.prompt} onConfirm={buildGuard.confirm} onCancel={buildGuard.cancel} />
    </div>
  )
}
