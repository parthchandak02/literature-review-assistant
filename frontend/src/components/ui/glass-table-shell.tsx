import type { ReactNode } from "react"
import { cn } from "@/lib/utils"

export interface GlassTableShellProps {
  children: ReactNode
  className?: string
}

/** Opaque glass-framed table container (DatabaseView pattern). */
export function GlassTableShell({ children, className }: GlassTableShellProps) {
  return <div className={cn("glass-table-shell", className)}>{children}</div>
}
