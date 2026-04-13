import type { ManuscriptAuditRun } from "./api"

export function selectManuscriptAuditRun(
  latestRun: ManuscriptAuditRun | null,
  history: ManuscriptAuditRun[],
  auditRunId: string | null,
): ManuscriptAuditRun | null {
  if (auditRunId) {
    const selected = history.find((run) => run.audit_run_id === auditRunId)
    if (selected) return selected
  }
  return latestRun
}

export function describeManuscriptGate(run: ManuscriptAuditRun | null): string {
  if (!run) return "No audit run selected."
  if (run.gate_blocked && run.gate_action === "advisory_only") {
    return "Audit completed with blocking findings, but workflow completion stayed advisory."
  }
  if (run.gate_blocked) return "Workflow blocked by manuscript audit gate."
  if (run.passed) return "Audit gate passed."
  return "Audit completed with findings."
}

export function describeManuscriptContract(run: ManuscriptAuditRun | null): string {
  if (!run) return "No contract data."
  const status = run.contract_passed ? "passed" : "failed"
  return `Contract gate ${status} in ${run.contract_mode} mode with ${run.contract_violation_count} violation(s).`
}

export function describeAuditStatusChip(run: ManuscriptAuditRun | null): string {
  if (!run) return "pending"
  if (run.gate_blocked && run.gate_action === "advisory_only") return "completed_with_findings"
  if (run.gate_blocked) return "blocked"
  if (run.passed) return "passed"
  return "review"
}
