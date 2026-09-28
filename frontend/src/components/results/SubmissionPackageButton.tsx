import { useState } from "react"
import { Download } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Spinner } from "@/components/ui/feedback"
import { APIResponseError, submissionZipUrl, triggerExport } from "@/lib/api"
import { cn } from "@/lib/utils"
import { formatExportError } from "./manuscriptUtils"

async function ensureSubmissionPackage(runId: string): Promise<void> {
  try {
    await triggerExport(runId, false)
  } catch (error) {
    if (error instanceof APIResponseError && error.status === 409) {
      await triggerExport(runId, true)
      return
    }
    throw error
  }
}

function startDownload(url: string) {
  const anchor = document.createElement("a")
  anchor.href = url
  anchor.download = ""
  anchor.rel = "noopener"
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
}

export function SubmissionPackageButton({
  runId,
  className,
  label = "Download submission package",
}: {
  runId: string
  className?: string
  label?: string
}) {
  const [packaging, setPackaging] = useState(false)

  async function handleClick() {
    if (packaging) return
    setPackaging(true)
    try {
      await ensureSubmissionPackage(runId)
      startDownload(submissionZipUrl(runId))
    } catch (error) {
      toast.error(formatExportError(error) || "Failed to build submission package")
    } finally {
      setPackaging(false)
    }
  }

  return (
    <Button
      type="button"
      size="xs"
      variant="outline"
      onClick={() => void handleClick()}
      disabled={packaging}
      aria-busy={packaging}
      title="Build (if needed) and download the full submission package (.zip)"
      className={cn("gap-1", className)}
    >
      {packaging ? <Spinner size="sm" /> : <Download className="h-3 w-3" />}
      {packaging ? "Packaging..." : label}
    </Button>
  )
}
