import { formatUsd } from "./costOpsFormatters"

export function CostChartTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean
  payload?: Array<{ value?: number }>
  label?: string
}) {
  if (!active || !payload?.length) return null
  const value = Number(payload[0].value ?? 0)
  return (
    <div className="rounded-lg border border-border bg-popover px-3 py-2 text-xs text-popover-foreground shadow-xl">
      <div className="text-muted mb-1">{label}</div>
      <div className="text-foreground font-mono font-semibold">{formatUsd(value)}</div>
    </div>
  )
}
