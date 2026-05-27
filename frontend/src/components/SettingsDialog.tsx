import { useState } from "react"
import { Key, BarChart3, X } from "lucide-react"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { ApiKeysPanel } from "@/components/ApiKeysSection"
import { CostsPanel } from "@/components/GlobalCostOpsDialog"

type SettingsTab = "keys" | "costs"

interface SettingsDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  initialTab?: SettingsTab
}

const TABS: { id: SettingsTab; label: string; icon: typeof Key }[] = [
  { id: "keys", label: "API Keys", icon: Key },
  { id: "costs", label: "Costs", icon: BarChart3 },
]

export function SettingsDialog({ open, onOpenChange, initialTab = "keys" }: SettingsDialogProps) {
  const [tab, setTab] = useState<SettingsTab>(initialTab)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-5xl border-border bg-card p-0 text-foreground">
        <DialogHeader className="border-b border-border px-6 py-4">
          <div className="flex items-start justify-between gap-4">
            <div>
              <DialogTitle className="text-foreground">Settings</DialogTitle>
              <DialogDescription className="mt-0.5 text-muted">
                Manage API credentials and view cost analytics.
              </DialogDescription>
            </div>
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

          {/* Tab bar */}
          <div className="flex gap-1 mt-3">
            {TABS.map((t) => {
              const Icon = t.icon
              const active = tab === t.id
              return (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => setTab(t.id)}
                  className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                    active
                      ? "bg-intent-primary-subtle text-foreground ring-1 ring-intent-primary-border"
                      : "text-muted hover:text-foreground hover:bg-surface-2/60"
                  }`}
                >
                  <Icon className="h-3.5 w-3.5" />
                  {t.label}
                </button>
              )
            })}
          </div>
        </DialogHeader>

        <div className="px-6 py-5 max-h-[70dvh] overflow-y-auto">
          {tab === "keys" && <ApiKeysPanel />}
          {tab === "costs" && <CostsPanel />}
        </div>
      </DialogContent>
    </Dialog>
  )
}
