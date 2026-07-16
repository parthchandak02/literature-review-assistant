import { useState } from "react"
import { CollapsibleSection } from "@/components/ui/section"
import { EvidenceNetworkViz } from "@/components/EvidenceNetworkViz"

export function EvidenceNetworkSection({ runId }: { runId: string }) {
  const [open, setOpen] = useState(false)
  return (
    <CollapsibleSection
      title="Evidence Network"
      open={open}
      onToggle={() => setOpen((v) => !v)}
    >
      <div className="p-4">
        {open && <EvidenceNetworkViz runId={runId} />}
      </div>
    </CollapsibleSection>
  )
}
