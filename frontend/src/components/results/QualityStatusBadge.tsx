import { AlertTriangle, CheckCircle2, CircleDashed, XCircle } from "lucide-react"
import { Badge, type BadgeVariant } from "@/components/ui/badge"

function VariantIcon({ variant }: { variant: BadgeVariant }) {
  if (variant === "danger") return <XCircle aria-hidden />
  if (variant === "warning") return <AlertTriangle aria-hidden />
  if (variant === "success") return <CheckCircle2 aria-hidden />
  return <CircleDashed aria-hidden />
}

export function QualityStatusBadge({ variant, label }: { variant: BadgeVariant; label: string }) {
  return (
    <Badge variant={variant} size="sm">
      <VariantIcon variant={variant} />
      {label}
    </Badge>
  )
}
