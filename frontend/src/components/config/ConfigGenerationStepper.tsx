import {
  HorizontalStepper,
  type StepperStep,
  type StepperStepStatus,
} from "@/components/ui/HorizontalStepper"

export type ConfigGenStepStatus = "done" | "degraded" | "skipped" | "active" | "pending"

export interface ConfigGenStepDisplay {
  key: string
  label: string
  shortLabel: string
  detail?: string | null
  status: ConfigGenStepStatus
}

function mapConfigStatus(status: ConfigGenStepStatus): StepperStepStatus {
  switch (status) {
    case "done":
      return "done"
    case "active":
      return "active"
    case "degraded":
      return "warning"
    case "skipped":
      return "skipped"
    default:
      return "pending"
  }
}

interface ConfigGenerationStepperProps {
  steps: ConfigGenStepDisplay[]
}

export function ConfigGenerationStepper({ steps }: ConfigGenerationStepperProps) {
  const mapped: StepperStep[] = steps.map((step) => ({
    key: step.key,
    label: step.shortLabel,
    status: mapConfigStatus(step.status),
    title: step.detail ?? step.label,
  }))

  return <HorizontalStepper steps={mapped} />
}
