import { Component, type ErrorInfo, type ReactNode } from "react"
import { AlertTriangle } from "lucide-react"

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
}

export class ViewBoundary extends Component<ViewBoundaryProps, ViewBoundaryState> {
  constructor(props: ViewBoundaryProps) {
    super(props)
    this.state = { hasError: false, message: "" }
  }

  static getDerivedStateFromError(error: Error): ViewBoundaryState {
    return { hasError: true, message: error.message || "Unknown error" }
  }

  componentDidUpdate(prevProps: ViewBoundaryProps) {
    if (prevProps.resetKey !== this.props.resetKey && this.state.hasError) {
      this.setState({ hasError: false, message: "" })
    }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("[ViewBoundary]", error, info.componentStack)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
          <AlertTriangle className="h-8 w-8 text-intent-danger" />
          <p className="text-sm font-medium text-foreground">
            {this.props.label ? `Could not load ${this.props.label}` : "Could not load this view"}
          </p>
          <p className="text-meta text-muted max-w-sm">{this.state.message}</p>
          <button
            type="button"
            className="mt-1 px-3 py-1.5 text-sm rounded bg-surface-2 hover:bg-surface-3 text-foreground transition-colors"
            onClick={() => this.setState({ hasError: false, message: "" })}
          >
            Try again
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
