export interface ScreeningStatsBarProps {
  total: number
  includedCount: number
  uncertainCount: number
}

export function ScreeningStatsBar({ total, includedCount, uncertainCount }: ScreeningStatsBarProps) {
  return (
    <div className="flex items-center gap-4 p-3 rounded-lg bg-card border border-border text-sm">
      <span className="text-muted">
        <span className="text-foreground font-semibold">{total}</span> papers reviewed
      </span>
      <span className="text-border">|</span>
      <span className="text-muted">
        <span className="text-intent-success font-semibold">{includedCount}</span> include
      </span>
      <span className="text-border">|</span>
      <span className="text-muted">
        <span className="text-intent-warning font-semibold">{uncertainCount}</span> uncertain
      </span>
    </div>
  )
}
