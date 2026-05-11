import { useCallback, useEffect, useRef, useState } from "react"
import {
  AlertTriangle,
  BookOpen,
  CheckCircle,
  XCircle,
} from "lucide-react"
import {
  fetchDbRagDiagnostics,
  fetchManuscriptAudit,
  fetchPrismaChecklist,
  fetchRunDiagnostics,
  fetchRunReadiness,
  fetchWorkflowManuscriptAuditFindings,
  fetchWorkflowManuscriptAuditSummary,
} from "@/lib/api"
import { Skeleton } from "@/components/ui/skeleton"
import { EmptyState, FetchError } from "@/components/ui/feedback"
import { CollapsibleSection } from "@/components/ui/section"
import { cn } from "@/lib/utils"
import type {
  ManuscriptAuditFinding,
  ManuscriptAuditPayload,
  PrismaChecklist,
  RagDiagnosticsPayload,
  ReadinessScorecard,
  RunDiagnosticsPayload,
} from "@/lib/api"
import {
  describeAuditStatusChip,
  describeManuscriptContract,
  describeManuscriptGate,
  selectManuscriptAuditRun,
} from "@/lib/manuscriptAudit"

function formatLabel(value: string): string {
  return value
    .replace(/_/g, " ")
    .replace(/\b\w/g, (m) => m.toUpperCase())
}

function PrismaStatusIcon({ status }: { status: string }) {
  if (status === "REPORTED") return <CheckCircle className="h-3.5 w-3.5 text-emerald-400 shrink-0" />
  if (status === "PARTIAL") return <AlertTriangle className="h-3.5 w-3.5 text-amber-400 shrink-0" />
  if (status === "NOT_APPLICABLE") return <BookOpen className="h-3.5 w-3.5 text-zinc-500 shrink-0" />
  return <XCircle className="h-3.5 w-3.5 text-red-400 shrink-0" />
}

function auditStatusBadgeClass(status: string): string {
  if (status === "passed") return "text-emerald-400 border-emerald-800 bg-emerald-900/20"
  if (status === "blocked") return "text-red-300 border-red-800 bg-red-900/20"
  if (status === "completed_with_findings") return "text-amber-300 border-amber-800 bg-amber-900/20"
  return "text-zinc-300 border-zinc-700 bg-zinc-900/40"
}

function ReadinessCard({ runId, workflowId }: { runId: string; workflowId?: string | null }) {
  const [data, setData] = useState<ReadinessScorecard | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setData(await fetchRunReadiness(runId, "runs", workflowId))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [runId, workflowId])

  useEffect(() => {
    void load()
  }, [load])

  const exportReady = data ? (data.submission_ready ?? data.ready) : false
  const contractReady = data ? (data.contract_ready ?? data.contract_passed) : false
  const auditReady = data ? (data.audit_ready ?? false) : false

  return (
    <CollapsibleSection
      icon={CheckCircle}
      title="Readiness Checks"
      description={
        data
          ? (exportReady
              ? "Detailed backend checks behind the ready state shown in Results."
              : "Detailed backend checks behind the blocked state shown in Results.")
          : "Detailed readiness diagnostics for the current run."
      }
      defaultOpen={false}
    >
      <div className="p-4">
        {loading ? (
          <div className="space-y-2">
            <Skeleton className="h-4 w-40" />
            <Skeleton className="h-16 w-full" />
          </div>
        ) : error ? (
          <FetchError message={error} onRetry={() => void load()} />
        ) : data ? (
          <div className="space-y-3">
            <div
              className={`rounded-xl border px-3 py-3 text-sm ${exportReady ? "border-emerald-500/30 bg-emerald-500/8 text-emerald-200" : "border-amber-500/30 bg-amber-500/8 text-amber-200"}`}
            >
              <div className="font-medium">{exportReady ? "Ready for manuscript export." : "Export blocked by readiness checks."}</div>
              <div className="mt-1 text-xs opacity-80">
                {data.fallback_event_count > 0
                  ? `${data.fallback_event_count} deterministic fallback event(s) recorded.`
                  : "No fallback events recorded."}
              </div>
              <div className="mt-2 flex flex-wrap gap-2 text-[11px]">
                <span className={cn("rounded-full border px-2 py-0.5", contractReady ? "border-emerald-800 bg-emerald-900/20 text-emerald-300" : "border-amber-800 bg-amber-900/20 text-amber-300")}>
                  Contract {contractReady ? "ready" : "blocked"}
                </span>
                <span className={cn("rounded-full border px-2 py-0.5", auditReady ? "border-emerald-800 bg-emerald-900/20 text-emerald-300" : "border-amber-800 bg-amber-900/20 text-amber-300")}>
                  Audit {auditReady ? "ready" : "blocked"}
                </span>
                <span className={cn("rounded-full border px-2 py-0.5", exportReady ? "border-emerald-800 bg-emerald-900/20 text-emerald-300" : "border-amber-800 bg-amber-900/20 text-amber-300")}>
                  Submission {exportReady ? "ready" : "blocked"}
                </span>
              </div>
            </div>
            <div className="grid gap-2">
              {data.checks.map((check) => (
                <div key={check.name} className="rounded-lg border border-zinc-800 bg-zinc-950/60 px-3 py-2">
                  <div className="flex items-start gap-2">
                    {check.ok ? (
                      <CheckCircle className="mt-0.5 h-4 w-4 text-emerald-400 shrink-0" />
                    ) : (
                      <AlertTriangle className="mt-0.5 h-4 w-4 text-amber-400 shrink-0" />
                    )}
                    <div className="min-w-0">
                      <div className="text-sm text-zinc-200">{formatLabel(check.name)}</div>
                      {check.detail && <div className="mt-0.5 text-xs text-zinc-500">{check.detail}</div>}
                    </div>
                  </div>
                </div>
              ))}
            </div>
            {!exportReady && data.blocking_reasons.length > 0 && (
              <div className="rounded-xl border border-red-500/20 bg-red-500/5 px-3 py-3">
                <div className="text-xs font-semibold text-red-300">Blocking reasons</div>
                <div className="mt-1 space-y-1">
                  {data.blocking_reasons.map((reason, idx) => (
                    <div key={`${idx}-${reason}`} className="text-xs text-red-200/80">
                      {reason}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : null}
      </div>
    </CollapsibleSection>
  )
}

function PrismaCard({ runId }: { runId: string }) {
  const [open, setOpen] = useState(false)
  const [data, setData] = useState<PrismaChecklist | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sectionFilter, setSectionFilter] = useState<string>("All")
  const hasFetched = useRef(false)

  const fetchChecklist = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setData(await fetchPrismaChecklist(runId))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [runId])

  useEffect(() => {
    hasFetched.current = false
    setData(null)
    setError(null)
    setSectionFilter("All")
  }, [runId])

  function handleToggle() {
    setOpen((v) => !v)
    if (!hasFetched.current) {
      hasFetched.current = true
      void fetchChecklist()
    }
  }

  const sections = data
    ? ["All", ...Array.from(new Set(data.items.map((item) => item.section)))]
    : ["All"]

  const filtered = data
    ? sectionFilter === "All"
      ? data.items
      : data.items.filter((item) => item.section === sectionFilter)
    : []

  const scoreChip =
    data && data.total > 0 ? (
      <span
        className={cn(
          "text-[10px] font-mono px-1.5 py-0.5 rounded border shrink-0",
          data.passed
            ? "text-emerald-400 border-emerald-800 bg-emerald-900/20"
            : "text-amber-400 border-amber-800 bg-amber-900/20",
        )}
      >
        {data.reported_count}/{data.total} {data.passed ? "PASS" : "review"}
      </span>
    ) : null

  return (
    <CollapsibleSection
      icon={CheckCircle}
      title="PRISMA 2020 Compliance"
      badge={scoreChip}
      open={open}
      onToggle={handleToggle}
    >
      <div className="p-4 space-y-4">
        {loading && (
          <div className="space-y-3">
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-5/6" />
            <Skeleton className="h-4 w-full" />
          </div>
        )}
        {error && <FetchError message={`Failed to load: ${error}`} onRetry={() => void fetchChecklist()} />}
        {data && data.source_state === "artifact_missing" && (
          <EmptyState
            icon={AlertTriangle}
            heading="PRISMA source manuscript artifact is missing."
            sub="Run may not have reached writing/finalize yet, or manuscript artifacts are unavailable for this run."
            className="py-10"
          />
        )}
        {data && data.source_state !== "artifact_missing" && (
          <>
            <div className="flex items-center gap-4 text-xs flex-wrap p-3 rounded-lg glass-panel">
              <span className="text-emerald-400 font-semibold">{data.reported_count} Reported</span>
              <span className="text-amber-400 font-semibold">{data.partial_count} Partial</span>
              <span className="text-red-400 font-semibold">{data.missing_count} Missing</span>
              <span className="text-zinc-400 font-semibold">{data.not_applicable_count} N/A</span>
            </div>

            <div className="flex items-center gap-1 flex-wrap">
              {sections.map((section) => (
                <button
                  key={section}
                  onClick={() => setSectionFilter(section)}
                  className={cn(
                    "px-2.5 py-1 rounded-full text-xs border transition-colors",
                    sectionFilter === section
                      ? "border-violet-600 bg-violet-900/40 text-violet-300"
                      : "border-zinc-700 text-zinc-500 hover:text-zinc-300",
                  )}
                >
                  {section}
                </button>
              ))}
            </div>

            <div className="space-y-1">
              {filtered.map((item) => (
                <div
                  key={item.item_id}
                  className={cn(
                    "flex items-start gap-2.5 px-3 py-2 rounded-lg text-xs",
                    item.status === "REPORTED"
                      ? "bg-emerald-900/10"
                      : item.status === "PARTIAL"
                        ? "bg-amber-900/10"
                        : item.status === "NOT_APPLICABLE"
                          ? "bg-zinc-900/40"
                          : "bg-red-900/10",
                  )}
                >
                  <PrismaStatusIcon status={item.status} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-mono text-zinc-500 shrink-0">{item.item_id}</span>
                      <span className="text-zinc-400 font-medium leading-snug">{item.description}</span>
                      <span className="text-zinc-600 ml-auto shrink-0">{item.section}</span>
                    </div>
                    {item.rationale && <p className="text-zinc-600 mt-0.5 leading-relaxed">{item.rationale}</p>}
                  </div>
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </CollapsibleSection>
  )
}

function ManuscriptAuditCard({ runId }: { runId: string }) {
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [data, setData] = useState<ManuscriptAuditPayload | null>(null)
  const [findings, setFindings] = useState<ManuscriptAuditFinding[]>([])
  const [selectedAuditRunId, setSelectedAuditRunId] = useState<string | null>(null)
  const hasFetched = useRef(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const payload = await fetchManuscriptAudit(runId)
      let nextPayload = payload
      let nextFindings = payload.findings
      let nextSelectedAuditRunId = payload.latest_run?.audit_run_id ?? null
      if (payload.workflow_id) {
        const summary = await fetchWorkflowManuscriptAuditSummary(payload.workflow_id)
        nextPayload = {
          ...payload,
          latest_run: summary.latest_run,
          history: summary.history,
        }
        nextSelectedAuditRunId = summary.latest_run?.audit_run_id ?? nextSelectedAuditRunId
        const findingsPayload = await fetchWorkflowManuscriptAuditFindings(
          payload.workflow_id,
          nextSelectedAuditRunId,
        )
        nextFindings = findingsPayload.findings
      }
      setSelectedAuditRunId(nextSelectedAuditRunId)
      setFindings(nextFindings)
      setData(nextPayload)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [runId])

  const loadSelectedFindings = useCallback(async (workflowId: string, auditRunId: string | null) => {
    setLoading(true)
    setError(null)
    try {
      const payload = await fetchWorkflowManuscriptAuditFindings(workflowId, auditRunId)
      setFindings(payload.findings)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    hasFetched.current = false
    setData(null)
    setFindings([])
    setSelectedAuditRunId(null)
    setError(null)
  }, [runId])

  function handleToggle() {
    setOpen((v) => !v)
    if (!hasFetched.current) {
      hasFetched.current = true
      void load()
    }
  }

  const latest = data?.latest_run ?? null
  const history = data?.history ?? []
  const selectedRun = selectManuscriptAuditRun(latest, history, selectedAuditRunId)
  const auditStatus = describeAuditStatusChip(selectedRun)

  useEffect(() => {
    if (!open || !hasFetched.current || !data?.workflow_id || !selectedAuditRunId) return
    if (selectedAuditRunId === latest?.audit_run_id) return
    void loadSelectedFindings(data.workflow_id, selectedAuditRunId)
  }, [data?.workflow_id, latest?.audit_run_id, loadSelectedFindings, open, selectedAuditRunId])

  return (
    <CollapsibleSection
      icon={AlertTriangle}
      title="Audit Findings"
      description={
        selectedRun?.gate_action === "advisory_only"
          ? "Detailed audit findings for a workflow that completed in advisory mode."
          : selectedRun
            ? "Detailed manuscript review history, evidence, and next-fix guidance."
            : "Open to inspect full audit history and detailed findings."
      }
      open={open}
      onToggle={handleToggle}
      badge={
        selectedRun ? (
          <span
            className={cn(
              "text-[10px] font-mono px-1.5 py-0.5 rounded border shrink-0",
              auditStatusBadgeClass(auditStatus),
            )}
          >
            {auditStatus}
          </span>
        ) : null
      }
    >
      <div className="p-4 space-y-3">
        {loading && (
          <div className="space-y-2">
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-5/6" />
          </div>
        )}
        {error && <FetchError message={`Failed to load audit: ${error}`} onRetry={() => void load()} />}
        {!loading && !error && !latest && (
          <EmptyState
            icon={AlertTriangle}
            heading="No manuscript audit data yet."
            sub="Run must complete phase_7_audit before findings appear."
            className="py-6"
          />
        )}
        {selectedRun && (
          <>
            <div className="flex items-center gap-2 flex-wrap">
              {history.map((run) => (
                <button
                  key={run.audit_run_id}
                  type="button"
                  className={cn(
                    "text-[10px] font-mono px-2 py-1 rounded border",
                    selectedAuditRunId === run.audit_run_id
                      ? "border-violet-700 bg-violet-900/30 text-violet-200"
                      : "border-zinc-800 bg-zinc-900/40 text-zinc-400 hover:text-zinc-200",
                  )}
                  onClick={() => {
                    setSelectedAuditRunId(run.audit_run_id)
                    if (data?.workflow_id) void loadSelectedFindings(data.workflow_id, run.audit_run_id)
                  }}
                >
                  {run.audit_run_id}
                </button>
              ))}
            </div>
            <div className="text-xs text-zinc-400">
              <span className="text-zinc-300 font-medium">Summary:</span> {selectedRun.summary || "No summary."}
            </div>
            <div
              className={cn(
                "rounded-xl border px-3 py-3 text-sm",
                auditStatus === "passed"
                  ? "border-emerald-500/30 bg-emerald-500/8 text-emerald-200"
                  : auditStatus === "blocked"
                    ? "border-red-500/30 bg-red-500/8 text-red-100"
                    : "border-amber-500/30 bg-amber-500/8 text-amber-100",
              )}
            >
              <div className="font-medium">
                {selectedRun.gate_action === "advisory_only"
                  ? "Workflow completed with advisory audit findings."
                  : selectedRun.gate_blocked
                    ? "Audit blocked workflow completion."
                    : selectedRun.passed
                      ? "Audit passed."
                      : "Audit completed with findings."}
              </div>
              <div className="mt-1 text-xs opacity-80">
                Verdict={selectedRun.verdict} | gate={selectedRun.gate_mode ?? "strict"} | last audited={selectedRun.last_audited_at ?? selectedRun.created_at}
              </div>
            </div>
            <div className="flex items-center gap-3 text-xs flex-wrap p-3 rounded-lg glass-panel">
              <span className="text-zinc-300">Findings: {selectedRun.total_findings}</span>
              <span className="text-red-400">Major: {selectedRun.major_count}</span>
              <span className="text-amber-400">Minor: {selectedRun.minor_count}</span>
              <span className="text-zinc-400">Notes: {selectedRun.note_count}</span>
              <span className="text-violet-400">Blocking: {selectedRun.blocking_count}</span>
            </div>
            {selectedRun.top_recommendations && selectedRun.top_recommendations.length > 0 && (
              <div className="rounded-lg border border-zinc-800 bg-zinc-950/60 px-3 py-3">
                <div className="text-xs font-semibold text-zinc-200">Top next fixes</div>
                <div className="mt-2 space-y-2">
                  {selectedRun.top_recommendations.slice(0, 3).map((recommendation) => (
                    <div key={recommendation} className="text-xs text-zinc-400">
                      {recommendation}
                    </div>
                  ))}
                </div>
              </div>
            )}
            <div className="text-xs rounded-lg px-3 py-2 bg-zinc-900/50 border border-zinc-800 space-y-1">
              <div className="text-zinc-200">{describeManuscriptGate(selectedRun)}</div>
              <div className="text-zinc-400">{describeManuscriptContract(selectedRun)}</div>
              {selectedRun.gate_failure_reasons.length > 0 && (
                <div className="space-y-1 pt-1">
                  {selectedRun.gate_failure_reasons.map((reason) => (
                    <div key={reason} className="text-amber-300">
                      {reason}
                    </div>
                  ))}
                </div>
              )}
              {selectedRun.contract_violations.slice(0, 5).map((violation) => (
                <div key={`${violation.code}-${violation.message}`} className="text-zinc-500">
                  {violation.code}: {violation.message}
                </div>
              ))}
            </div>
            <div className="space-y-1">
              {findings.slice(0, 12).map((finding) => (
                <div
                  key={finding.finding_id}
                  className="text-xs rounded-lg px-3 py-2 bg-zinc-900/50 border border-zinc-800"
                >
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-zinc-500">{finding.profile}</span>
                    <span
                      className={cn(
                        "uppercase text-[10px] font-semibold",
                        finding.severity === "major"
                          ? "text-red-400"
                          : finding.severity === "minor"
                            ? "text-amber-400"
                            : "text-zinc-400",
                      )}
                    >
                      {finding.severity}
                    </span>
                    {finding.section ? <span className="text-zinc-500">[{finding.section}]</span> : null}
                  </div>
                  <div className="text-zinc-300 mt-1">{finding.evidence}</div>
                  <div className="text-zinc-500 mt-1">Fix: {finding.recommendation}</div>
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </CollapsibleSection>
  )
}

function RunDiagnosticsCard({ runId, workflowId }: { runId: string; workflowId?: string | null }) {
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [data, setData] = useState<RunDiagnosticsPayload | null>(null)
  const hasFetched = useRef(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setData(await fetchRunDiagnostics(runId, "runs", workflowId))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [runId, workflowId])

  useEffect(() => {
    hasFetched.current = false
    setData(null)
    setError(null)
  }, [runId])

  function handleToggle() {
    setOpen((v) => !v)
    if (!hasFetched.current) {
      hasFetched.current = true
      void load()
    }
  }

  return (
    <CollapsibleSection
      icon={BookOpen}
      title="Run Diagnostics"
      open={open}
      onToggle={handleToggle}
      badge={
        data ? (
          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded border shrink-0 border-zinc-700 bg-zinc-900/40 text-zinc-300">
            {data.writing_manifests.length} manifests
          </span>
        ) : null
      }
    >
      <div className="p-4 space-y-3">
        {loading && (
          <div className="space-y-2">
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-5/6" />
          </div>
        )}
        {error && <FetchError message={`Run diagnostics failed: ${error}`} onRetry={() => void load()} />}
        {data && (
          <>
            <div className="grid gap-2 md:grid-cols-3">
              <div className="rounded-lg border border-zinc-800 bg-zinc-950/60 px-3 py-2 text-xs">
                <div className="text-zinc-500">Workflow</div>
                <div className="mt-1 font-mono text-zinc-200">{data.workflow_id}</div>
              </div>
              <div className="rounded-lg border border-zinc-800 bg-zinc-950/60 px-3 py-2 text-xs">
                <div className="text-zinc-500">Step failures</div>
                <div className="mt-1 text-zinc-200">{data.step_failures}</div>
              </div>
              <div className="rounded-lg border border-zinc-800 bg-zinc-950/60 px-3 py-2 text-xs">
                <div className="text-zinc-500">Fallback events</div>
                <div className="mt-1 text-zinc-200">{data.fallback_count}</div>
              </div>
            </div>

            <div className="rounded-lg border border-zinc-800 bg-zinc-950/60 px-3 py-3">
              <div className="text-xs font-semibold text-zinc-300">Step summary</div>
              <div className="mt-2 space-y-2">
                {Object.entries(data.step_summary).map(([phase, statuses]) => (
                  <div key={phase} className="text-xs flex items-start justify-between gap-4">
                    <span className="font-mono text-zinc-400">{phase}</span>
                    <span className="text-zinc-500 text-right">
                      {Object.entries(statuses)
                        .map(([status, count]) => `${status}: ${count}`)
                        .join(" | ")}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-lg border border-zinc-800 bg-zinc-950/60 px-3 py-3">
              <div className="text-xs font-semibold text-zinc-300">Fallback summary</div>
              <div className="mt-2 space-y-2">
                {data.fallback_summary.length === 0 ? (
                  <div className="text-xs text-zinc-500">No fallback events recorded for the active generation.</div>
                ) : (
                  data.fallback_summary.map((row) => (
                    <div key={`${row.phase}-${row.module}-${row.fallback_type}`} className="text-xs flex items-start justify-between gap-4">
                      <span className="text-zinc-400">{row.phase} / {row.module}</span>
                      <span className="text-zinc-500">{row.fallback_type} x {row.event_count}</span>
                    </div>
                  ))
                )}
              </div>
            </div>

            <div className="rounded-lg border border-zinc-800 bg-zinc-950/60 px-3 py-3">
              <div className="text-xs font-semibold text-zinc-300">Writing manifests</div>
              <div className="mt-2 space-y-2">
                {data.writing_manifests.length === 0 ? (
                  <div className="text-xs text-zinc-500">No writing manifests recorded.</div>
                ) : (
                  data.writing_manifests.slice(0, 12).map((row) => (
                    <div key={`${row.section_key}-${row.attempt_number}-${row.generation}`} className="rounded-md border border-zinc-800/80 px-3 py-2 text-xs">
                      <div className="flex items-center justify-between gap-3">
                        <span className="font-mono text-zinc-300">{row.section_key}</span>
                        <span className="text-zinc-500">attempt {row.attempt_number} / gen {row.generation}</span>
                      </div>
                      <div className="mt-1 text-zinc-500">
                        contract={row.contract_status} | retries={row.retry_count} | fallback={row.fallback_used ? "yes" : "no"} | words={row.word_count ?? "n/a"}
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          </>
        )}
      </div>
    </CollapsibleSection>
  )
}

function RagDiagnosticsCard({ runId, workflowId }: { runId: string; workflowId?: string | null }) {
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [data, setData] = useState<RagDiagnosticsPayload | null>(null)
  const hasFetched = useRef(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setData(await fetchDbRagDiagnostics(runId, workflowId))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [runId, workflowId])

  useEffect(() => {
    hasFetched.current = false
    setData(null)
    setError(null)
  }, [runId])

  function handleToggle() {
    setOpen((v) => !v)
    if (!hasFetched.current) {
      hasFetched.current = true
      void load()
    }
  }

  return (
    <CollapsibleSection
      icon={BookOpen}
      title="RAG Retrieval Diagnostics"
      open={open}
      onToggle={handleToggle}
      badge={
        data ? (
          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded border shrink-0 border-zinc-700 bg-zinc-900/40 text-zinc-300">
            {data.total} records
          </span>
        ) : null
      }
    >
      <div className="p-4 space-y-3">
        {loading && (
          <div className="space-y-2">
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-5/6" />
          </div>
        )}
        {error && <FetchError message={`RAG diagnostics failed: ${error}`} onRetry={() => void load()} />}
        {data && (
          <div className="space-y-2">
            {data.records.length === 0 ? (
              <div className="text-xs text-zinc-500">No RAG diagnostics recorded for this run.</div>
            ) : (
              data.records.slice(0, 12).map((row, idx) => (
                <div key={`${row.section}-${row.created_at}-${idx}`} className="rounded-lg border border-zinc-800 bg-zinc-950/60 px-3 py-3 text-xs">
                  <div className="flex items-center justify-between gap-3">
                    <span className="font-mono text-zinc-300">{row.section}</span>
                    <span className={cn("uppercase tracking-wide", row.status === "ok" ? "text-emerald-400" : "text-amber-400")}>
                      {row.status}
                    </span>
                  </div>
                  <div className="mt-1 text-zinc-500">
                    {row.query_type} | retrieved={row.retrieved_count} | candidate_k={row.candidate_k} | final_k={row.final_k} | latency={row.latency_ms}ms | rerank={row.rerank_enabled ? "yes" : "no"}
                  </div>
                  {row.error_message && <div className="mt-1 text-red-300">{row.error_message}</div>}
                  {row.selected_chunks.length > 0 && (
                    <div className="mt-2 text-zinc-500">
                      Top chunks: {row.selected_chunks.slice(0, 3).map((chunk) => chunk.citekey || chunk.paper_id || chunk.chunk_id || "chunk").join(", ")}
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        )}
      </div>
    </CollapsibleSection>
  )
}

interface QualityViewProps {
  exportRunId?: string | null
  workflowId?: string | null
}

export function QualityView({ exportRunId, workflowId }: QualityViewProps) {
  if (!exportRunId) {
    return (
      <EmptyState
        icon={CheckCircle}
        heading="Quality checks available once the review completes."
        sub="Finish the review to inspect readiness, reporting compliance, and the final audit."
        className="h-64"
      />
    )
  }

  return (
    <div className="flex flex-col gap-3 min-h-[520px]">
      <div className="rounded-xl border border-zinc-800 bg-zinc-950/60 px-4 py-4">
        <div className="text-sm font-semibold text-zinc-100">Advanced quality diagnostics</div>
        <div className="mt-1 text-sm text-zinc-300">
          Use Results for the primary submission decision. This tab is the deep-dive for readiness checks, audit findings, PRISMA detail, and diagnostics.
        </div>
      </div>
      <ReadinessCard runId={exportRunId} workflowId={workflowId} />
      <ManuscriptAuditCard runId={exportRunId} />
      <PrismaCard runId={exportRunId} />
      <RunDiagnosticsCard runId={exportRunId} workflowId={workflowId} />
      <RagDiagnosticsCard runId={exportRunId} workflowId={workflowId} />
    </div>
  )
}
