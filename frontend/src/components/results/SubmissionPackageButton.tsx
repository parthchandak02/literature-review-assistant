import { Download } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Spinner } from "@/components/ui/feedback"
import { submissionZipUrl } from "@/lib/api"
import { cn } from "@/lib/utils"
import { PackageBuildConfirm } from "./PackageBuildConfirm"
import { PACKAGE_ACTION_LABEL, startDownload, usePackageBuildGuard, useSubmissionPackage } from "./submissionPackage"

export function SubmissionPackageButton({
  runId,
  className,
  label = PACKAGE_ACTION_LABEL.download,
}: {
  runId: string
  className?: string
  label?: string
}) {
  const { state, ensure } = useSubmissionPackage(runId)
  const buildGuard = usePackageBuildGuard(runId)
  const building = state.status === "building"
  const busy = building || buildGuard.checking

  async function buildAndDownload() {
    const next = await ensure()
    if (next.status === "ready") {
      startDownload(submissionZipUrl(runId))
    } else {
      toast.error(next.error ?? "Failed to build submission package")
    }
  }

  function handleClick() {
    if (busy) return
    if (state.status === "ready") {
      startDownload(submissionZipUrl(runId))
      return
    }
    void buildGuard.guard(() => void buildAndDownload())
  }

  return (
    <>
      <Button
        type="button"
        size="xs"
        variant="outline"
        onClick={handleClick}
        disabled={busy}
        aria-busy={busy}
        title={
          state.status === "ready"
            ? "Download the submission package (.zip)"
            : "Build the submission package if needed, then download it (.zip)"
        }
        className={cn("gap-1", className)}
      >
        {building ? <Spinner size="sm" /> : <Download className="h-3 w-3" />}
        {building ? "Building…" : label}
      </Button>
      <PackageBuildConfirm prompt={buildGuard.prompt} onConfirm={buildGuard.confirm} onCancel={buildGuard.cancel} />
    </>
  )
}
