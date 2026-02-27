import { cn } from "@/lib/utils"

/**
 * Skeleton -- pulse placeholder used for loading states across all views.
 * Replaces the mix of Spinner / LoadingPane / Loader2+animate-spin patterns.
 */
interface SkeletonProps {
  className?: string
}

export function Skeleton({ className }: SkeletonProps) {
  return (
    <div
      className={cn("animate-pulse rounded bg-zinc-800/70", className)}
    />
  )
}

/** A standard card-shaped skeleton block. */
export function SkeletonCard({ className }: SkeletonProps) {
  return (
    <div className={cn("rounded-xl border border-zinc-800 bg-zinc-900/50 p-5 space-y-3", className)}>
      <Skeleton className="h-4 w-1/3" />
      <Skeleton className="h-3 w-full" />
      <Skeleton className="h-3 w-2/3" />
    </div>
  )
}

/** A standard table-row skeleton (3 rows). */
export function SkeletonTable({ rows = 3 }: { rows?: number }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex gap-3 items-center py-2 border-b border-zinc-800/50">
          <Skeleton className="h-3 w-1/2" />
          <Skeleton className="h-3 w-1/4 ml-auto" />
          <Skeleton className="h-3 w-1/6" />
        </div>
      ))}
    </div>
  )
}
