import { apiFetch } from "./client"

export interface ReserveWorkflowDraftResponse {
  workflow_id: string
  db_path: string
  run_dir: string
}

export async function reserveWorkflowDraft(
  topic: string,
  runRoot = "runs",
): Promise<ReserveWorkflowDraftResponse> {
  return apiFetch<ReserveWorkflowDraftResponse>("/workflow/reserve", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ topic, run_root: runRoot }),
  })
}

export async function saveWorkflowConfigDraft(
  workflowId: string,
  reviewYaml: string,
  runRoot = "runs",
): Promise<{ workflow_id: string; status: string }> {
  return apiFetch<{ workflow_id: string; status: string }>(
    `/workflow/${encodeURIComponent(workflowId)}/config-draft`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ review_yaml: reviewYaml, run_root: runRoot }),
    },
  )
}
