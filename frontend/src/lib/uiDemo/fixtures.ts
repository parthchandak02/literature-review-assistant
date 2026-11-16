import type { EnvKeysStatus, HistoryEntry, HistoryRailEntry, ReviewEvent } from "@/lib/api"

export const DEMO_WORKFLOW_ID = "demo-ui-01"

export const demoEnvKeysStatus: EnvKeysStatus = {
  required_ui_keys: ["fireworks", "gemini"],
  server_ready: true,
  providers: {
    fireworks: { configured: true, masked: "fw_…demo", source: "env", required: true },
    gemini: { configured: true, masked: "…demo", source: "env", required: true },
  },
}

const demoRail: HistoryRailEntry[] = [
  {
    workflow_id: DEMO_WORKFLOW_ID,
    topic: "Effects of mindfulness programs on nurse burnout in acute care hospitals",
    status: "done",
    db_path: "demo/runtime.db",
    created_at: "2026-03-12 14:22:00",
    papers_found: 1847,
    papers_included: 12,
    total_cost: 4.52,
    stats_ok: true,
    live_run_id: null,
    is_archived: false,
    is_completed_hidden: false,
    lane_override: null,
    notes: null,
  },
  {
    workflow_id: "demo-ui-02",
    topic: "Hospital geriatric palliative care models in India: organization and outcomes",
    status: "awaiting_review",
    db_path: "demo/runtime.db",
    created_at: "2026-03-10 09:15:00",
    papers_found: 2103,
    papers_included: 0,
    total_cost: 2.18,
    stats_ok: true,
    live_run_id: null,
    is_archived: false,
    is_completed_hidden: false,
    lane_override: null,
    notes: null,
  },
  {
    workflow_id: "demo-ui-03",
    topic: "UV-C autonomous cleaning versus manual disinfection in outpatient clinics",
    status: "config_ready",
    db_path: "demo/runtime.db",
    created_at: "2026-03-08 16:40:00",
    papers_found: 0,
    papers_included: 0,
    total_cost: 0.12,
    stats_ok: true,
    live_run_id: null,
    is_archived: false,
    is_completed_hidden: false,
    lane_override: null,
    notes: null,
  },
]

export function demoHistoryEntries(): HistoryEntry[] {
  return demoRail.map((row) => ({
    workflow_id: row.workflow_id,
    topic: row.topic,
    status: row.status,
    db_path: row.db_path,
    created_at: row.created_at,
    updated_at: row.created_at,
    papers_found: row.papers_found,
    papers_included: row.papers_included,
    total_cost: row.total_cost,
    artifacts_count: row.status === "done" ? 14 : 0,
    stats_ok: true,
    stats_error: null,
    live_run_id: null,
    notes: null,
    is_archived: false,
    archived_at: null,
    is_completed_hidden: false,
    completed_hidden_at: null,
    lane_override: row.lane_override,
  }))
}

export function demoHistoryRail(): HistoryRailEntry[] {
  return demoRail
}

export const demoConfigYaml = `research_question: >-
  What is the effect of structured mindfulness programs on nurse burnout
  in acute care hospitals?
review_type: systematic
question_framework: PICO
`

export function demoWorkflowEvents(workflowId: string): ReviewEvent[] {
  if (workflowId !== DEMO_WORKFLOW_ID && workflowId !== "demo-ui-02") return []
  const ts = "2026-03-12T14:30:00Z"
  return [
    { type: "phase_start", phase: "search", description: "Database search", total: 8, ts },
    { type: "phase_done", phase: "search", summary: { records: 1847 }, total: 8, completed: 8, ts },
    { type: "phase_done", phase: "screening", summary: { screened: 1847, included: 42 }, total: null, completed: null, ts },
    { type: "phase_done", phase: "synthesis", summary: { included: 12 }, total: null, completed: null, ts },
    { type: "done", outputs: { manuscript: true }, ts },
  ]
}

export function demoPrismaCounts(workflowId: string) {
  return {
    workflow_id: workflowId,
    live: {
      records_identified: 1847,
      records_after_duplicates: 1715,
      records_screened: 1715,
      records_excluded: 1673,
      reports_sought: 52,
      reports_assessed: 42,
      reports_excluded_with_reasons: { wrong_design: 18, wrong_population: 12 },
      total_included: 12,
      arithmetic_valid: true,
    },
    sidecar: null,
    figure_stale: false,
  }
}

export function demoCostDashboard() {
  return {
    total_cost: 4.52,
    total_tokens_in: 182_000,
    total_tokens_out: 24_500,
    total_calls: 186,
    by_model: [{ model: "accounts/fireworks/models/llama-v3p3-70b-instruct", cost: 3.1, calls: 120 }],
    by_phase: [{ phase: "screening", cost: 2.4, calls: 80 }],
  }
}
