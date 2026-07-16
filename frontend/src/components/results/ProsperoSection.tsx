import { Download, FileCode, FileType } from "lucide-react"
import { Button } from "@/components/ui/button"
import { CollapsibleSection } from "@/components/ui/section"
import { prosperoFormDocxUrl, prosperoFormMarkdownUrl } from "@/lib/api"

export function ProsperoDownloadsCard({ runId }: { runId: string }) {
  return (
    <CollapsibleSection icon={Download} title="PROSPERO Draft" defaultOpen={false}>
      <div className="p-4 flex flex-wrap gap-2">
        <Button size="sm" variant="outline" asChild className="h-8 gap-1 text-xs border-border text-foreground">
          <a href={prosperoFormDocxUrl(runId)}>
            <FileType className="h-3 w-3 text-intent-info" />
            PROSPERO DOCX
          </a>
        </Button>
        <Button size="sm" variant="outline" asChild className="h-8 gap-1 text-xs border-border text-foreground">
          <a href={prosperoFormMarkdownUrl(runId)}>
            <FileCode className="h-3 w-3 text-intent-success" />
            PROSPERO Markdown
          </a>
        </Button>
        </div>
    </CollapsibleSection>
  )
}
