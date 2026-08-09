import { Network } from "lucide-react"
import { ResultsBlock } from "@/components/ui/section"
import { EvidenceNetworkViz } from "@/components/EvidenceNetworkViz"

export function EvidenceNetworkSection({ runId }: { runId: string }) {
  return (
    <ResultsBlock icon={Network} title="Evidence Network">
      <EvidenceNetworkViz runId={runId} />
    </ResultsBlock>
  )
}
