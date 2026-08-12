import * as React from "react"
import { Calendar } from "lucide-react"

import { cn } from "@/lib/utils"
import { Input } from "@/components/ui/input"

const DateInput = React.forwardRef<HTMLInputElement, Omit<React.ComponentProps<"input">, "type">>(
  ({ className, disabled, ...props }, ref) => {
    return (
      <div className={cn("date-input-shell", disabled && "pointer-events-none")}>
        <Input
          ref={ref}
          type="date"
          disabled={disabled}
          className={cn("date-input-control", className)}
          {...props}
        />
        <Calendar className="date-input-icon" aria-hidden />
      </div>
    )
  },
)
DateInput.displayName = "DateInput"

export { DateInput }
