import { Download, FileCode, FileType } from "lucide-react"
import { Button } from "@/components/ui/button"
import { ResultsBlock } from "@/components/ui/section"
import { prosperoFormDocxUrl, prosperoFormMarkdownUrl } from "@/lib/api"
import { RESULTS_DOWNLOAD_BTN_CLS } from "./resultsShared"

export function ProsperoDownloadsCard({ runId }: { runId: string }) {
  return (
    <ResultsBlock icon={Download} title="PROSPERO Draft">
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="outline" asChild className={RESULTS_DOWNLOAD_BTN_CLS}>
          <a href={prosperoFormDocxUrl(runId)}>
            <FileType className="h-3 w-3 text-intent-info" />
            PROSPERO DOCX
          </a>
        </Button>
        <Button size="sm" variant="outline" asChild className={RESULTS_DOWNLOAD_BTN_CLS}>
          <a href={prosperoFormMarkdownUrl(runId)}>
            <FileCode className="h-3 w-3 text-intent-success" />
            PROSPERO Markdown
          </a>
        </Button>
      </div>
    </ResultsBlock>
  )
}
