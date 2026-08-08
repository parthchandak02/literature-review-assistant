import { Download, FileText } from "lucide-react"
import { Button } from "@/components/ui/button"
import { CollapsibleSection } from "@/components/ui/section"
import { downloadUrl, prismaFlowZipUrl } from "@/lib/api"

interface PrismaDiagramCardProps {
  filePath: string
  runId?: string | null
}

export function PrismaDiagramCard({ filePath, runId }: PrismaDiagramCardProps) {
  return (
    <CollapsibleSection
      icon={FileText}
      title="PRISMA Diagram"
      defaultOpen={false}
      actions={
        runId ? (
          <Button
            size="sm"
            variant="outline"
            asChild
            className="h-7 gap-1 text-xs border-border text-foreground"
            onClick={(e) => e.stopPropagation()}
          >
            <a href={prismaFlowZipUrl(runId)} download title="Download PRISMA flow data (summary + per-paper records)">
              <Download className="h-3 w-3" />
              PRISMA Data
            </a>
          </Button>
        ) : null
      }
    >
      <div className="p-4">
        <div className="rounded-xl border border-border bg-card p-2">
          <img src={downloadUrl(filePath)} alt="PRISMA flow diagram" className="w-full h-auto rounded-lg" />
        </div>
      </div>
    </CollapsibleSection>
  )
}
