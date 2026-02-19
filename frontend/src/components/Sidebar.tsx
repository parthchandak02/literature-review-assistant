import { cn } from "@/lib/utils"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import {
  BookMarked,
  BarChart3,
  ChevronLeft,
  ChevronRight,
  Clock,
  Database,
  FileText,
  LayoutDashboard,
  ListFilter,
  Plus,
} from "lucide-react"

export type NavTab =
  | "setup"
  | "overview"
  | "cost"
  | "database"
  | "log"
  | "results"
  | "history"

type RunStatus = "idle" | "connecting" | "streaming" | "done" | "error" | "cancelled"

interface NavItem {
  id: NavTab
  label: string
  icon: React.ElementType
  requiresRun?: boolean
}

const NAV_ITEMS: NavItem[] = [
  { id: "overview", label: "Overview", icon: LayoutDashboard, requiresRun: true },
  { id: "cost", label: "Cost & Usage", icon: BarChart3, requiresRun: true },
  { id: "log", label: "Event Log", icon: ListFilter, requiresRun: true },
  { id: "database", label: "Database", icon: Database, requiresRun: true },
  { id: "results", label: "Results", icon: FileText, requiresRun: true },
  { id: "history", label: "History", icon: Clock, requiresRun: false },
]

const STATUS_LABEL: Record<RunStatus, string> = {
  idle: "Ready",
  connecting: "Connecting",
  streaming: "Running",
  done: "Completed",
  error: "Failed",
  cancelled: "Cancelled",
}

const STATUS_COLOR: Record<RunStatus, string> = {
  idle: "text-zinc-500",
  connecting: "text-violet-400",
  streaming: "text-violet-400",
  done: "text-emerald-400",
  error: "text-red-400",
  cancelled: "text-amber-400",
}

interface SidebarProps {
  activeTab: NavTab
  onTabChange: (tab: NavTab) => void
  hasRun: boolean
  isRunning: boolean
  runStatus: RunStatus
  totalCost: number
  topic: string | null
  onNewReview: () => void
  collapsed: boolean
  onToggle: () => void
}

export function Sidebar({
  activeTab,
  onTabChange,
  hasRun,
  isRunning,
  runStatus,
  totalCost,
  topic,
  onNewReview,
  collapsed,
  onToggle,
}: SidebarProps) {
  const statusLabel = STATUS_LABEL[runStatus] ?? runStatus
  const statusColor = STATUS_COLOR[runStatus] ?? "text-zinc-400"

  return (
    <TooltipProvider delayDuration={0}>
      <aside
        className={cn(
          "fixed left-0 top-0 h-full bg-zinc-900 border-r border-zinc-800 flex flex-col z-20 select-none overflow-hidden",
          "transition-[width] duration-200 ease-in-out",
          collapsed ? "w-[56px]" : "w-[220px]",
        )}
      >
        {/* Logo row */}
        <div className="flex items-center h-14 border-b border-zinc-800 shrink-0 px-3.5">
          <div className="flex items-center justify-center w-7 h-7 rounded-lg bg-violet-600 shrink-0">
            <BookMarked className="h-3.5 w-3.5 text-white" />
          </div>
          <div
            className={cn(
              "flex items-center gap-2 ml-2 overflow-hidden transition-all duration-200",
              collapsed ? "w-0 opacity-0" : "w-auto opacity-100",
            )}
          >
            <span className="font-semibold text-sm text-white tracking-tight whitespace-nowrap">LitReview</span>
            <span className="text-[10px] font-medium text-zinc-500 bg-zinc-800 px-1.5 py-0.5 rounded whitespace-nowrap">
              BETA
            </span>
          </div>
        </div>

        {/* New review button */}
        <div className="px-2.5 pt-3 pb-2 shrink-0">
          <NavTooltip label="New Review" collapsed={collapsed} side="right">
            <button
              onClick={onNewReview}
              className={cn(
                "w-full flex items-center rounded-md transition-colors text-zinc-300 hover:text-white hover:bg-zinc-800",
                collapsed ? "justify-center h-9 w-9 mx-auto" : "gap-2 px-3 py-1.5 text-sm",
              )}
            >
              <Plus className="h-3.5 w-3.5 shrink-0" />
              {!collapsed && "New Review"}
            </button>
          </NavTooltip>
        </div>

        {/* Active run status pill (expanded only) */}
        {hasRun && topic && !collapsed && (
          <div className="mx-2.5 mb-2 px-3 py-2 bg-zinc-800/60 rounded-lg shrink-0">
            <div className="flex items-center gap-1.5 mb-1">
              {isRunning && (
                <span className="relative flex h-2 w-2 shrink-0">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-violet-400 opacity-75" />
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-violet-500" />
                </span>
              )}
              <span className={cn("text-[11px] font-medium uppercase tracking-wide", statusColor)}>
                {statusLabel}
              </span>
            </div>
            <p className="text-xs text-zinc-200 line-clamp-2 leading-snug">{topic}</p>
          </div>
        )}

        {/* Collapsed running dot */}
        {hasRun && isRunning && collapsed && (
          <div className="flex justify-center pb-1 shrink-0">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-violet-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-violet-500" />
            </span>
          </div>
        )}

        {/* Nav items */}
        <nav className="flex-1 px-2.5 pb-2 overflow-y-auto overflow-x-hidden">
          {NAV_ITEMS.map((item) => {
            const disabled = (item.requiresRun ?? false) && !hasRun
            const active = activeTab === item.id
            return (
              <NavTooltip key={item.id} label={item.label} collapsed={collapsed} side="right">
                <button
                  onClick={() => !disabled && onTabChange(item.id)}
                  disabled={disabled}
                  className={cn(
                    "w-full flex items-center rounded-md transition-colors mb-0.5",
                    collapsed
                      ? "justify-center h-9 w-9 mx-auto"
                      : "gap-2.5 px-3 py-1.5 text-sm",
                    active
                      ? collapsed
                        ? "bg-zinc-800 text-white ring-1 ring-violet-500/50"
                        : "bg-zinc-800 text-white border-l-2 border-violet-500 pl-[10px]"
                      : disabled
                      ? "text-zinc-600 cursor-not-allowed"
                      : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/60",
                  )}
                >
                  <item.icon className="h-4 w-4 shrink-0" />
                  {!collapsed && item.label}
                </button>
              </NavTooltip>
            )
          })}
        </nav>

        {/* Cost footer (expanded only) */}
        {hasRun && totalCost > 0 && !collapsed && (
          <div className="px-4 py-3 border-t border-zinc-800 shrink-0">
            <div className="text-[11px] text-zinc-500 mb-0.5 uppercase tracking-wide">Total Cost</div>
            <div className="text-lg font-mono font-semibold text-emerald-400">
              ${totalCost.toFixed(4)}
            </div>
          </div>
        )}

        {/* Toggle button */}
        <button
          onClick={onToggle}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          className={cn(
            "flex items-center justify-center h-9 shrink-0 border-t border-zinc-800",
            "text-zinc-600 hover:text-zinc-300 hover:bg-zinc-800/50 transition-colors",
          )}
        >
          {collapsed ? (
            <ChevronRight className="h-4 w-4" />
          ) : (
            <ChevronLeft className="h-4 w-4" />
          )}
        </button>
      </aside>
    </TooltipProvider>
  )
}

// Internal helper: only shows tooltip when sidebar is collapsed
function NavTooltip({
  label,
  collapsed,
  side,
  children,
}: {
  label: string
  collapsed: boolean
  side?: "right" | "left" | "top" | "bottom"
  children: React.ReactNode
}) {
  if (!collapsed) return <>{children}</>
  return (
    <Tooltip>
      <TooltipTrigger asChild>{children}</TooltipTrigger>
      <TooltipContent side={side ?? "right"} className="bg-zinc-800 border-zinc-700 text-zinc-200 text-xs">
        {label}
      </TooltipContent>
    </Tooltip>
  )
}
