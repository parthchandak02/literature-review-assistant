import { Suspense, lazy, useRef, useState } from "react"
import { Key, BarChart3, X } from "lucide-react"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { GlassTabs } from "@/components/ui/glass-tabs"
import { ApiKeysPanel } from "@/components/ApiKeysSection"
import { LoadingPane } from "@/components/ui/feedback"
import type { SettingsTab } from "@/context/SettingsContext"
import { useEdgeFade } from "@/hooks/useEdgeFade"

export type { SettingsTab }

const CostsPanel = lazy(() => import("@/components/CostsPanel").then((m) => ({ default: m.CostsPanel })))

interface SettingsDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  initialTab?: SettingsTab
}

const TABS: { id: SettingsTab; label: string; icon: typeof Key }[] = [
  { id: "keys", label: "API keys", icon: Key },
  { id: "costs", label: "Global costs", icon: BarChart3 },
]

export function SettingsDialog({ open, onOpenChange, initialTab = "keys" }: SettingsDialogProps) {
  const [tab, setTab] = useState<SettingsTab>(initialTab)
  const [prevOpen, setPrevOpen] = useState(open)
  if (open !== prevOpen) {
    setPrevOpen(open)
    if (open) setTab(initialTab)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        aria-describedby={undefined}
        className="flex h-[min(52rem,90dvh)] w-[min(56rem,96vw)] max-w-4xl flex-col gap-0 overflow-hidden border-border bg-card p-0 text-foreground"
      >
        <DialogHeader className="shrink-0 border-b border-border px-5 py-3">
          <div className="flex items-center justify-between gap-4">
            <DialogTitle className="text-foreground">Settings</DialogTitle>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              onClick={() => onOpenChange(false)}
              className="rounded-xl border border-transparent text-muted hover:border-border hover:bg-surface-2/70 hover:text-foreground"
              aria-label="Close settings"
            >
              <X className="h-4 w-4" />
            </Button>
          </div>

          <GlassTabs items={TABS} activeTab={tab} onTabChange={setTab} className="mt-2" />
        </DialogHeader>

        <SettingsTabPanel tab={tab} />
      </DialogContent>
    </Dialog>
  )
}

function SettingsTabPanel({ tab }: { tab: SettingsTab }) {
  const bodyRef = useRef<HTMLDivElement | null>(null)
  const bottomFade = useEdgeFade(bodyRef, "y")
  return (
    <div
      ref={bodyRef}
      role="tabpanel"
      id={`tabpanel-${tab}`}
      aria-labelledby={`tab-${tab}`}
      style={bottomFade}
      className="min-h-0 min-w-0 flex-1 overflow-y-auto px-5 pt-3 pb-6"
    >
      <div>
        {tab === "keys" && (
          <div className="mx-auto max-w-xl">
            <ApiKeysPanel />
          </div>
        )}
        {tab === "costs" && (
          <Suspense fallback={<LoadingPane />}>
            <CostsPanel />
          </Suspense>
        )}
      </div>
    </div>
  )
}
