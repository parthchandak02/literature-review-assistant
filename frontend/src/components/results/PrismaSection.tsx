import { Download, FileText } from "lucide-react"
import { Button } from "@/components/ui/button"
import { ResultsBlock } from "@/components/ui/section"
import { downloadUrl, prismaDiagramUrl, prismaFlowZipUrl } from "@/lib/api"
import { RESULTS_DOWNLOAD_BTN_CLS } from "./resultsShared"

interface PrismaDiagramCardProps {
  filePath: string
  runId?: string | null
}

export function PrismaDiagramCard({ filePath, runId }: PrismaDiagramCardProps) {
  return (
    <ResultsBlock
      icon={FileText}
      title="PRISMA Diagram"
      actions={
        runId ? (
          <Button
            size="sm"
            variant="outline"
            asChild
            className={RESULTS_DOWNLOAD_BTN_CLS}
          >
            <a href={prismaFlowZipUrl(runId)} download title="Download PRISMA flow data (summary + per-paper records)">
              <Download className="h-3 w-3" />
              PRISMA Data
            </a>
          </Button>
        ) : null
      }
    >
      <div className="rounded-lg border border-border bg-card p-2">
        <img
          src={runId ? prismaDiagramUrl(runId) : downloadUrl(filePath)}
          alt="PRISMA flow diagram"
          className="w-full h-auto rounded-lg"
        />
      </div>
    </ResultsBlock>
  )
}
