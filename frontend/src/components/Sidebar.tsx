import { cn } from "@/lib/utils"
import {
  BookMarked,
  BarChart3,
  Database,
  FileText,
  LayoutDashboard,
  ListFilter,
  Plus,
  Layers,
} from "lucide-react"

export type NavTab =
  | "setup"
  | "overview"
  | "phases"
  | "cost"
  | "database"
  | "log"
  | "results"

interface NavItem {
  id: NavTab
  label: string
  icon: React.ElementType
  requiresRun?: boolean
}

const NAV_ITEMS: NavItem[] = [
  { id: "overview", label: "Overview", icon: LayoutDashboard, requiresRun: true },
  { id: "phases", label: "Phases", icon: Layers, requiresRun: true },
  { id: "cost", label: "Cost & Usage", icon: BarChart3, requiresRun: true },
  { id: "log", label: "Event Log", icon: ListFilter, requiresRun: true },
  { id: "database", label: "Database", icon: Database, requiresRun: true },
  { id: "results", label: "Results", icon: FileText, requiresRun: true },
]

interface SidebarProps {
  activeTab: NavTab
  onTabChange: (tab: NavTab) => void
  hasRun: boolean
  isRunning: boolean
  totalCost: number
  topic: string | null
  onNewReview: () => void
}

export function Sidebar({
  activeTab,
  onTabChange,
  hasRun,
  isRunning,
  totalCost,
  topic,
  onNewReview,
}: SidebarProps) {
  return (
    <aside className="fixed left-0 top-0 h-full w-[220px] bg-zinc-900 border-r border-zinc-800 flex flex-col z-20 select-none">
      {/* Logo */}
      <div className="flex items-center gap-2.5 px-4 h-14 border-b border-zinc-800 shrink-0">
        <div className="flex items-center justify-center w-7 h-7 rounded-lg bg-violet-600">
          <BookMarked className="h-3.5 w-3.5 text-white" />
        </div>
        <span className="font-semibold text-sm text-white tracking-tight">LitReview</span>
        <span className="ml-auto text-[10px] font-medium text-zinc-500 bg-zinc-800 px-1.5 py-0.5 rounded">
          BETA
        </span>
      </div>

      {/* New review button */}
      <div className="px-3 pt-3 pb-2 shrink-0">
        <button
          onClick={onNewReview}
          className="w-full flex items-center gap-2 px-3 py-1.5 text-sm text-zinc-300 hover:text-white hover:bg-zinc-800 rounded-md transition-colors"
        >
          <Plus className="h-3.5 w-3.5" />
          New Review
        </button>
      </div>

      {/* Active run info */}
      {hasRun && topic && (
        <div className="mx-3 mb-2 px-3 py-2 bg-zinc-800/60 rounded-lg shrink-0">
          <div className="flex items-center gap-1.5 mb-1">
            {isRunning && (
              <span className="relative flex h-2 w-2 shrink-0">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-violet-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-2 w-2 bg-violet-500" />
              </span>
            )}
            <span className="text-[11px] font-medium text-zinc-400 uppercase tracking-wide">
              {isRunning ? "Running" : "Completed"}
            </span>
          </div>
          <p className="text-xs text-zinc-200 line-clamp-2 leading-snug">{topic}</p>
        </div>
      )}

      {/* Nav items */}
      <nav className="flex-1 px-3 pb-3 overflow-y-auto">
        {NAV_ITEMS.map((item) => {
          const disabled = item.requiresRun && !hasRun
          const active = activeTab === item.id
          return (
            <button
              key={item.id}
              onClick={() => !disabled && onTabChange(item.id)}
              disabled={disabled}
              className={cn(
                "w-full flex items-center gap-2.5 px-3 py-1.5 rounded-md text-sm transition-colors mb-0.5",
                active
                  ? "bg-zinc-800 text-white border-l-2 border-violet-500 pl-[10px]"
                  : disabled
                  ? "text-zinc-600 cursor-not-allowed"
                  : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/60",
              )}
            >
              <item.icon className="h-4 w-4 shrink-0" />
              {item.label}
            </button>
          )
        })}
      </nav>

      {/* Bottom: cost summary */}
      {hasRun && totalCost > 0 && (
        <div className="px-4 py-3 border-t border-zinc-800 shrink-0">
          <div className="text-[11px] text-zinc-500 mb-0.5 uppercase tracking-wide">Total Cost</div>
          <div className="text-lg font-mono font-semibold text-emerald-400">
            ${totalCost.toFixed(4)}
          </div>
        </div>
      )}
    </aside>
  )
}
