import { Component, type ErrorInfo, type ReactNode } from "react"
import { AlertTriangle, Copy, RotateCw } from "lucide-react"
import { Button } from "@/components/ui/button"

interface ViewBoundaryProps {
  children: ReactNode
  /** Shown in the fallback message (e.g. tab name). */
  label?: string
  /** When this changes, a prior error state is cleared (e.g. tab switch). */
  resetKey?: string | number
}

interface ViewBoundaryState {
  hasError: boolean
  message: string
  stack: string
  copied: boolean
}

const CLEARED: ViewBoundaryState = { hasError: false, message: "", stack: "", copied: false }

export class ViewBoundary extends Component<ViewBoundaryProps, ViewBoundaryState> {
  constructor(props: ViewBoundaryProps) {
    super(props)
    this.state = CLEARED
  }

  static getDerivedStateFromError(error: Error): Partial<ViewBoundaryState> {
    return { hasError: true, message: error.message || "Unknown error", stack: error.stack ?? "", copied: false }
  }

  componentDidUpdate(prevProps: ViewBoundaryProps) {
    if (prevProps.resetKey !== this.props.resetKey && this.state.hasError) {
      this.setState(CLEARED)
    }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("[ViewBoundary]", error, info.componentStack)
    if (info.componentStack) {
      this.setState((s) => ({ stack: `${s.stack}\n\nComponent stack:${info.componentStack}` }))
    }
  }

  private async copyDetails() {
    const details = [
      `View: ${this.props.label ?? "unknown"}`,
      `URL: ${window.location.href}`,
      `Error: ${this.state.message}`,
      this.state.stack,
    ]
      .filter(Boolean)
      .join("\n")
    try {
      await navigator.clipboard.writeText(details)
      this.setState({ copied: true })
    } catch {
      this.setState({ copied: false })
    }
  }

  render() {
    if (this.state.hasError) {
      return (
        <div role="alert" className="flex flex-col items-center justify-center gap-3 py-16 text-center">
          <AlertTriangle className="h-8 w-8 text-intent-danger" aria-hidden />
          <p className="text-sm font-medium text-foreground">
            {this.props.label ? `Could not load ${this.props.label}` : "Could not load this view"}
          </p>
          <p className="text-meta text-muted max-w-sm [overflow-wrap:anywhere]">{this.state.message}</p>
          <div className="mt-1 flex flex-wrap items-center justify-center gap-2">
            <Button type="button" size="sm" variant="outline" onClick={() => this.setState(CLEARED)}>
              Try again
            </Button>
            <Button type="button" size="sm" variant="outline" onClick={() => window.location.reload()}>
              <RotateCw className="h-3.5 w-3.5" aria-hidden />
              Reload page
            </Button>
            <Button type="button" size="sm" variant="ghost" onClick={() => void this.copyDetails()}>
              <Copy className="h-3.5 w-3.5" aria-hidden />
              {this.state.copied ? "Copied" : "Copy details"}
            </Button>
          </div>
          <span className="sr-only" role="status">
            {this.state.copied ? "Error details copied" : ""}
          </span>
        </div>
      )
    }
    return this.props.children
  }
}
