import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-control text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:pointer-events-none disabled:opacity-50 glass-interactive [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default:
          "bg-intent-primary-solid text-intent-primary-solid-fg hover:bg-intent-primary-solid/90",
        destructive:
          "bg-intent-danger-solid text-intent-danger-solid-fg hover:bg-intent-danger-solid/90",
        success:
          "bg-intent-success-solid text-intent-success-solid-fg hover:bg-intent-success-solid/90",
        warning:
          "bg-intent-warning-solid text-intent-warning-solid-fg hover:bg-intent-warning-solid/90",
        outline:
          "glass-panel border-border text-foreground hover:text-foreground",
        secondary:
          "glass-panel text-foreground hover:text-foreground",
        ghost: "text-muted hover:text-foreground hover:bg-surface-2/45",
        link: "text-intent-primary-text underline-offset-4 hover:underline",
      },
      size: {
        xs: "h-7 gap-1.5 px-2 text-xs [&_svg]:size-3.5",
        sm: "h-8 px-3",
        default: "h-9 px-4 py-2",
        lg: "h-10 px-6",
        icon: "h-9 w-9",
        "icon-sm": "h-8 w-8 [&_svg]:size-3.5",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button"
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    )
  }
)
Button.displayName = "Button"

// eslint-disable-next-line react-refresh/only-export-components
export { Button, buttonVariants }
