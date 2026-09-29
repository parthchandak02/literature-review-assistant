import { humanizeIdentifier, humanizeSnake } from "@/lib/humanize"
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
    contract_passed?: boolean | null
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

export type AuditGate = "contract" | "audit"

export interface AuditItem {
  id: string
  gate: AuditGate
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
    const detail = [
      plainAuditText(v.message),
      v.expected ? `Expected ${formatExpectation(plainAuditText(v.expected), v.code)}` : "",
      v.actual ? `got ${plainAuditText(v.actual)}` : "",
    ]
      .filter(Boolean)
      .join(" · ")
    items.push({
      id: `contract-${v.code}-${items.length}`,
      gate: "contract",
      kind: kindFor(v.severity, false),
      severityLabel: v.severity || "contract",
      title: contractCheckTitle(v.code),
      detail,
      recommendation: null,
      section: null,
    })
  }
  for (const f of payload.findings ?? []) {
    items.push({
      id: f.finding_id,
      gate: "audit",
      kind: kindFor(f.severity, Boolean(f.blocking)),
      severityLabel: f.blocking ? "blocking" : f.severity,
      title: f.category,
      detail: plainAuditText(f.evidence),
      recommendation: f.recommendation ? plainAuditText(f.recommendation) : null,
      section: f.section ?? null,
    })
  }
  return items
    .map((item, index) => ({ item, index }))
    .sort((a, b) => KIND_ORDER[a.item.kind] - KIND_ORDER[b.item.kind] || a.index - b.index)
    .map(({ item }) => item)
}

const CONTRACT_CHECK_TITLES: Record<string, string> = {
  ABSTRACT_OVER_LIMIT: "Abstract is over the word limit",
  ABSTRACT_RESULTS_PLACEHOLDER: "Abstract results are placeholder text",
  ABSTRACT_STRUCTURE_MISSING_FIELDS: "Abstract is missing structured headings",
  ABSTRACT_UNDER_MINIMUM: "Abstract is too short",
  AI_LEAKAGE: "AI assistant wording left in the text",
  ARTIFACT_PLACEHOLDER_LEAK: "Placeholder text in a generated artifact",
  COUNT_DISCLOSURE_MISMATCH: "Reported counts disagree with the data",
  DOMAIN_SCOPE_DRIFT: "Out-of-scope topics mentioned",
  DOMAIN_TERM_FIDELITY_WEAK: "Key topic terms used too rarely",
  EXTRACTION_YIELD_LOW: "Too little data extracted from studies",
  FAILED_DB_DISCLOSURE_MISSING: "Failed database searches not disclosed",
  FAILED_DB_STATUS_MISCHARACTERIZED: "Failed database searches described wrongly",
  FIGURE_ASSET_MISSING: "Referenced figure file is missing",
  FIGURE_LATEX_MISMATCH: "Figures differ between Markdown and LaTeX",
  FIGURE_NUMBERING_INVALID: "Figure numbering is out of order",
  GRADE_TABLE_PIPELINE_JARGON: "GRADE table contains internal jargon",
  GRADE_UNGROUNDED: "GRADE ratings lack supporting assessments",
  HEADING_PARITY_MISMATCH: "Headings differ between Markdown and LaTeX",
  IMPLICATIONS_MISPLACED: "Implications appear in the wrong section",
  INCLUDED_COUNT_MISMATCH: "Study table count differs from included studies",
  MALFORMED_SECTION_HEADING: "Malformed section heading",
  META_FEASIBILITY_CONTRADICTION: "Meta-analysis feasibility is contradicted",
  MODEL_ID_LEAKAGE: "AI model names left in the text",
  NON_PRIMARY_IN_TABLE: "Non-primary study listed in the study table",
  PLACEHOLDER_FRAGMENT: "Placeholder fragment in the text",
  PLACEHOLDER_LEAK: "Placeholder text left in the manuscript",
  PRISMA_STATEMENT_MISSING: "PRISMA statement missing",
  PROTOCOL_REGISTRATION_CONTRADICTION: "Protocol registration is contradicted",
  PROTOCOL_REGISTRATION_FUTURE_TENSE: "Registration described as not yet done",
  QUALITY_ASSESSMENT_CORRUPTED_INPUT: "Quality assessment input is corrupted",
  REQUIRED_SECTION_MISSING: "Required section missing",
  REVIEW_FACTS_CROSS_ARTIFACT: "Counts differ across outputs",
  ROB_FIGURE_CAPTION_MISMATCH: "Risk-of-bias figure caption does not match",
  SECTION_CONTENT_INCOMPLETE: "Section content is incomplete",
  SECTION_DETERMINISTIC_FALLBACK: "Section used fallback text",
  SECTION_ORDER_INVALID: "Sections are out of order",
  SNAKE_CASE_LEAKAGE: "Internal identifiers left in the text",
  STUDY_TABLE_FILLER_LEAK: "Filler text in the study table",
  UNRESOLVED_CITATIONS: "Citations that do not resolve",
  UNUSED_BIB_ENTRY: "Unused bibliography entries",
}

const COMPARISON_WORDS: [string, string][] = [
  [">=", "at least"],
  ["=>", "at least"],
  ["≥", "at least"],
  ["<=", "at most"],
  ["=<", "at most"],
  ["≤", "at most"],
  ["!=", "not"],
  ["≠", "not"],
  ["==", "exactly"],
  [">", "more than"],
  ["<", "fewer than"],
  ["=", "exactly"],
]

/** Units for bare numeric expectations, by contract code. */
const EXPECTATION_UNITS: Record<string, string> = {
  ABSTRACT_UNDER_MINIMUM: "words",
  ABSTRACT_OVER_LIMIT: "words",
}

/** `>= 210` -> `at least 210 words` (unit from the check code when the value is a bare number). */
export function formatExpectation(expected: string, code = ""): string {
  const text = expected.trim()
  const match = COMPARISON_WORDS.find(([op]) => text.startsWith(op))
  if (!match) return text
  const rest = text.slice(match[0].length).trim()
  if (!rest) return text
  const unit = EXPECTATION_UNITS[code.toUpperCase()]
  return `${match[1]} ${rest}${unit && /^\d+(?:\.\d+)?%?$/.test(rest) ? ` ${unit}` : ""}`
}

export function contractCheckTitle(code: string): string {
  return CONTRACT_CHECK_TITLES[code.toUpperCase()] ?? humanizeIdentifier(code)
}

const QUOTED_ITEM = String.raw`'(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*"`
const LIST_LITERAL = new RegExp(String.raw`\[\s*(?:${QUOTED_ITEM})(?:\s*,\s*(?:${QUOTED_ITEM}))*\s*,?\s*\]`, "g")
const QUOTED_ITEM_GLOBAL = new RegExp(QUOTED_ITEM, "g")

/** `['tennis', 'badminton']` -> `tennis, badminton`. */
export function formatListLiterals(text: string): string {
  return text.replace(LIST_LITERAL, (list) =>
    (list.match(QUOTED_ITEM_GLOBAL) ?? []).map((item) => item.slice(1, -1)).join(", "),
  )
}

const JARGON_REPLACEMENTS: [RegExp, string][] = [
  [/\bthe canonical synthesis cohort of (\d+) (studies|papers)\b/gi, "the $1 included $2"],
  [/\bthe canonical synthesis cohort\b/gi, "the included studies"],
  [/\bcanonical synthesis cohort\b/gi, "included studies"],
  [/\bthe deterministic contract (also )?flags\b/gi, "the consistency checks $1flag"],
  [/\bthe deterministic contract\b/gi, "the consistency checks"],
  [/\bdeterministic contract\b/gi, "consistency checks"],
  [/\bcontract gate\b/gi, "consistency checks"],
]

const KNOWN_CODE = /\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b/g

/** Plain wording for audit text: list literals, pipeline jargon and known check codes. */
export function plainAuditText(text: string): string {
  let out = formatListLiterals(text)
  for (const [re, plain] of JARGON_REPLACEMENTS) {
    out = out.replace(re, (match, ...groups: unknown[]) => {
      const text = plain.replace(/\$(\d)/g, (_, n: string) => String(groups[Number(n) - 1] ?? ""))
      return /^[A-Z]/.test(match) ? text.charAt(0).toUpperCase() + text.slice(1) : text
    })
  }
  return out.replace(KNOWN_CODE, (code) => (CONTRACT_CHECK_TITLES[code] ? `"${CONTRACT_CHECK_TITLES[code]}"` : code))
}

export interface ContractGateSummary {
  items: AuditItem[]
  passed: boolean
  errors: number
  warnings: number
}

export interface AuditGateSummary {
  items: AuditItem[]
  verdict: string
  passed: boolean
  blocking: number
  major: number
  minor: number
  notes: number
}

export interface AuditGates {
  contract: ContractGateSummary
  audit: AuditGateSummary
}

export function auditGates(payload: ManuscriptAuditPayload | null | undefined): AuditGates | null {
  const run = payload?.latest_run
  if (!payload || !run) return null
  const items = auditItemsFromPayload(payload)
  const contractItems = items.filter((i) => i.gate === "contract")
  const auditItems = items.filter((i) => i.gate === "audit")
  const errors = contractItems.filter((i) => i.kind === "failure").length
  const findings = payload.findings ?? []
  const nonBlocking = findings.filter((f) => !f.blocking).map((f) => kindFor(f.severity, false))
  return {
    contract: {
      items: contractItems,
      passed: run.contract_passed ?? errors === 0,
      errors,
      warnings: contractItems.length - errors,
    },
    audit: {
      items: auditItems,
      verdict: run.verdict,
      passed: run.passed,
      blocking: findings.filter((f) => f.blocking).length,
      major: nonBlocking.filter((k) => k === "failure").length,
      minor: nonBlocking.filter((k) => k === "warning").length,
      notes: nonBlocking.filter((k) => k === "note").length,
    },
  }
}

export function contractGateCountLine(gate: ContractGateSummary): string {
  if (gate.items.length === 0) return "No violations"
  const parts = [plural(gate.items.length, "violation", "violations")]
  if (gate.errors > 0) parts.push(plural(gate.errors, "error", "errors"))
  if (gate.warnings > 0) parts.push(plural(gate.warnings, "warning", "warnings"))
  return parts.join(" · ")
}

export function auditGateCountLine(gate: AuditGateSummary): string {
  if (gate.items.length === 0) return "No findings"
  const parts = [plural(gate.items.length, "finding", "findings")]
  if (gate.blocking > 0) parts.push(`${gate.blocking} blocking`)
  if (gate.major > 0) parts.push(`${gate.major} major`)
  if (gate.minor > 0) parts.push(`${gate.minor} minor`)
  if (gate.notes > 0) parts.push(plural(gate.notes, "note", "notes"))
  return parts.join(" · ")
}

export function gateOverviewLine(preWritingStatus: string | null | undefined, gates: AuditGates | null): string | null {
  if (!gates) return null
  const pre = (preWritingStatus ?? "").toLowerCase()
  const prePassed = pre === "passed" || pre === "pass"
  const failures: string[] = []
  if (!gates.contract.passed) failures.push("the consistency checks failed")
  if (!gates.audit.passed) failures.push(`the manuscript audit returned ${humanizeSnake(gates.audit.verdict).toLowerCase()}`)
  if (!prePassed) return null
  if (failures.length === 0) return "Pre-writing validation, consistency checks and manuscript audit all passed."
  return `Pre-writing validation passed, but after writing ${failures.join(" and ")}.`
}

/** Badge tone for an audit verdict such as "major_revisions" or "accept". */
export function verdictBadgeVariant(verdict: string | null | undefined, passed?: boolean): BadgeVariant {
  const v = (verdict ?? "").toLowerCase()
  if (/major|reject|fail|block/.test(v)) return "danger"
  if (/minor|revis|warn/.test(v)) return "warning"
  if (passed || /accept|pass|ok/.test(v)) return "success"
  return "neutral"
}

export const AUDIT_KIND_BADGE: Record<AuditItemKind, BadgeVariant> = {
  failure: "danger",
  warning: "warning",
  note: "neutral",
}

function plural(count: number, one: string, many: string): string {
  return `${count} ${count === 1 ? one : many}`
}

const CONTRACT_GATE_REASON = /^contract gate failed in mode=\w+ with (\d+) violation\(s\)$/i
const AUDIT_GATE_REASON = /^audit gate failed in mode=\w+ \(verdict=(\w+), blocking=(\d+)\)$/i

/** Backend gate failure strings -> plain sentences; unknown text is returned unchanged. */
export function humanizeGateReason(raw: string): string {
  const text = raw.trim()
  const contract = CONTRACT_GATE_REASON.exec(text)
  if (contract) {
    return `Consistency checks failed: ${plural(Number(contract[1]), "violation", "violations")}`
  }
  const audit = AUDIT_GATE_REASON.exec(text)
  if (audit) {
    const verdict = humanizeSnake(audit[1]).toLowerCase()
    return `Audit verdict: ${verdict} (${plural(Number(audit[2]), "blocking issue", "blocking issues")})`
  }
  return raw
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
