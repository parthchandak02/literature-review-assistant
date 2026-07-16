import { FileText } from "lucide-react"
import { CollapsibleSection } from "@/components/ui/section"
import { downloadUrl } from "@/lib/api"

export function PrismaDiagramCard({ filePath }: { filePath: string }) {
  return (
    <CollapsibleSection icon={FileText} title="PRISMA Diagram" defaultOpen={false}>
      <div className="p-4">
        <div className="rounded-xl border border-border bg-card p-2">
          <img src={downloadUrl(filePath)} alt="PRISMA flow diagram" className="w-full h-auto rounded-lg" />
        </div>
      </div>
    </CollapsibleSection>
  )
}
