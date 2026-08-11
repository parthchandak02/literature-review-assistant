import { apiFetch } from "./client"

export interface ValidationSummary {
  workflow_id: string
  latest_run: {
    validation_run_id: string
    profile: string
    status: string
    tool_version: string
    summary: Record<string, unknown>
    started_at: string
    completed_at: string
    error_count: number
    warn_count: number
    total_checks: number
  } | null
  checks?: ValidationCheck[]
}

export interface ValidationCheck {
  phase: string
  check_name: string
  status: string
  severity: string
  metric_value: number | null
  details: Record<string, unknown>
  source_module: string | null
  paper_id: string | null
  created_at: string
}

export async function fetchWorkflowValidationSummary(workflowId: string): Promise<ValidationSummary> {
  return apiFetch(`/workflow/${workflowId}/validation/summary`)
}

export interface ValidationSummaryWithChecks extends ValidationSummary {
  checks: ValidationCheck[]
}

export async function fetchWorkflowValidationSummaryWithChecks(
  workflowId: string,
): Promise<ValidationSummaryWithChecks> {
  return apiFetch(`/workflow/${workflowId}/validation/summary?include=checks`)
}

export async function fetchWorkflowValidationChecks(
  workflowId: string,
  validationRunId?: string,
): Promise<{ workflow_id: string; validation_run_id: string | null; checks: ValidationCheck[] }> {
  const params = new URLSearchParams()
  if (validationRunId) params.set("validation_run_id", validationRunId)
  const suffix = params.toString() ? `?${params.toString()}` : ""
  return apiFetch(`/workflow/${workflowId}/validation/checks${suffix}`)
}
