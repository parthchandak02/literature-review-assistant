import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium transition-colors [&_svg]:pointer-events-none [&_svg]:size-3 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        neutral:
          "bg-intent-neutral-subtle text-intent-neutral border-intent-neutral-border",
        primary:
          "bg-intent-primary-subtle text-intent-primary border-intent-primary-border",
        success:
          "bg-intent-success-subtle text-intent-success border-intent-success-border",
        warning:
          "bg-intent-warning-subtle text-intent-warning border-intent-warning-border",
        danger:
          "bg-intent-danger-subtle text-intent-danger border-intent-danger-border",
        info:
          "bg-intent-info-subtle text-intent-info border-intent-info-border",
        active:
          "bg-intent-active-subtle text-intent-active border-intent-active-border",
      },
      size: {
        sm: "text-[10px] px-1.5 py-px",
        md: "text-xs px-2 py-0.5",
      },
    },
    defaultVariants: {
      variant: "neutral",
      size: "md",
    },
  }
)

type BadgeVariant = NonNullable<VariantProps<typeof badgeVariants>["variant"]>

interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

const Badge = React.forwardRef<HTMLSpanElement, BadgeProps>(
  ({ className, variant, size, ...props }, ref) => {
    return (
      <span
        className={cn(badgeVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    )
  }
)
Badge.displayName = "Badge"

// eslint-disable-next-line react-refresh/only-export-components
export { Badge, badgeVariants, type BadgeVariant }
