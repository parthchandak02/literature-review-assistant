import { humanizeSnake } from "@/lib/humanize"
import { apiFetch } from "@/lib/api"
import type { BadgeVariant } from "@/components/ui/badge"

export interface ManuscriptAuditFindingRow {
  finding_id: string
  severity: string
  category: string
  section?: string | null
  evidence: string
  recommendation: string
  owner_module?: string
  blocking?: boolean
}

export interface ManuscriptContractViolationRow {
  code: string
  severity: string
  message: string
  expected?: string | null
  actual?: string | null
}

export interface ManuscriptAuditPayload {
  run_id: string
  workflow_id: string
  latest_run: {
    audit_run_id: string
    verdict: string
    passed: boolean
    contract_violations?: ManuscriptContractViolationRow[]
  } | null
  findings: ManuscriptAuditFindingRow[]
  audit_summary: {
    verdict: string
    status_label: string
    blocking_count: number
    total_findings: number
    summary: string
    gate_failure_reasons: string[]
    top_recommendations: string[]
  } | null
}

export function fetchRunManuscriptAudit(runId: string): Promise<ManuscriptAuditPayload> {
  return apiFetch(`/run/${encodeURIComponent(runId)}/manuscript-audit`)
}

export type AuditItemKind = "failure" | "warning" | "note"

export interface AuditItem {
  id: string
  kind: AuditItemKind
  severityLabel: string
  title: string
  detail: string
  recommendation: string | null
  section: string | null
}

const FAILURE_SEVERITIES = new Set(["major", "error", "critical", "blocking", "high"])
const WARNING_SEVERITIES = new Set(["minor", "warning", "warn", "medium"])

function kindFor(severity: string, blocking: boolean): AuditItemKind {
  const s = severity.toLowerCase()
  if (blocking || FAILURE_SEVERITIES.has(s)) return "failure"
  if (WARNING_SEVERITIES.has(s)) return "warning"
  return "note"
}

const KIND_ORDER: Record<AuditItemKind, number> = { failure: 0, warning: 1, note: 2 }

export function auditItemsFromPayload(payload: ManuscriptAuditPayload | null | undefined): AuditItem[] {
  if (!payload) return []
  const items: AuditItem[] = []
  for (const v of payload.latest_run?.contract_violations ?? []) {
    const detail = [v.message, v.expected ? `Expected ${v.expected}` : "", v.actual ? `got ${v.actual}` : ""]
      .filter(Boolean)
      .join(" · ")
    items.push({
      id: `contract-${v.code}-${items.length}`,
      kind: kindFor(v.severity, false),
      severityLabel: v.severity || "contract",
      title: `Contract: ${v.code}`,
      detail,
      recommendation: null,
      section: null,
    })
  }
  for (const f of payload.findings ?? []) {
    items.push({
      id: f.finding_id,
      kind: kindFor(f.severity, Boolean(f.blocking)),
      severityLabel: f.blocking ? "blocking" : f.severity,
      title: f.category,
      detail: f.evidence,
      recommendation: f.recommendation || null,
      section: f.section ?? null,
    })
  }
  return items
    .map((item, index) => ({ item, index }))
    .sort((a, b) => KIND_ORDER[a.item.kind] - KIND_ORDER[b.item.kind] || a.index - b.index)
    .map(({ item }) => item)
}

export const AUDIT_KIND_BADGE: Record<AuditItemKind, BadgeVariant> = {
  failure: "danger",
  warning: "warning",
  note: "neutral",
}

export function splitAuditSummary(text: string): { title: string | null; body: string }[] {
  return text
    .split(/\s+\|\s+/)
    .map((part) => part.trim())
    .filter(Boolean)
    .map((part) => {
      const match = /^([a-z0-9_]+\/)?([a-z0-9_]+):\s+/i.exec(part)
      if (!match) return { title: null, body: part }
      return { title: humanizeSnake(match[2]), body: part.slice(match[0].length) }
    })
}
