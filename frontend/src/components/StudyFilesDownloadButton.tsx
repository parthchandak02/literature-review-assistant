import { Download } from "lucide-react"
import { Button } from "@/components/ui/button"
import { studyFilesZipUrl } from "@/lib/api"
import { cn } from "@/lib/utils"

interface StudyFilesDownloadButtonProps {
  runId: string
  label?: string
  className?: string
  title?: string
}

export function StudyFilesDownloadButton({
  runId,
  label = "Download Studies ZIP",
  className,
  title = "Download all included-study full-text files as ZIP",
}: StudyFilesDownloadButtonProps) {
  const downloadName = `${runId}-studies-files.zip`
  return (
    <Button size="sm" variant="outline" asChild className={cn("shrink-0", className)}>
      <a href={studyFilesZipUrl(runId)} download={downloadName} title={title}>
        <Download className="h-3.5 w-3.5" />
        {label}
      </a>
    </Button>
  )
}
