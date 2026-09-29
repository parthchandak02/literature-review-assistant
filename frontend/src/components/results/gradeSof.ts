import type { BadgeVariant } from "@/components/ui/badge"
import type { GradeSofRow } from "@/lib/api"
import { humanizeIdentifier } from "@/lib/humanize"

const DESIGN_LABELS: Record<string, string> = {
  rct: "RCT",
  cross_sectional: "Cross-sectional",
  non_randomized: "Non-randomised",
  non_randomised: "Non-randomised",
  mixed_methods: "Mixed methods",
}

const DOMAINS: { key: keyof GradeSofRow; label: string }[] = [
  { key: "risk_of_bias", label: "Risk of bias" },
  { key: "inconsistency", label: "Inconsistency" },
  { key: "indirectness", label: "Indirectness" },
  { key: "imprecision", label: "Imprecision" },
  { key: "other_considerations", label: "Other considerations" },
]

const CERTAINTY_BADGE: Record<string, BadgeVariant> = {
  high: "success",
  moderate: "info",
  low: "warning",
  very_low: "danger",
}

const RANDOMISED_DESIGNS = new Set(["rct", "randomized_controlled_trial", "randomised_controlled_trial", "randomized", "randomised"])

export interface GradeRowView {
  key: string
  outcome: string | null
  studies: string | null
  downgrades: string[]
  downgradeNote: string
  certainty: string | null
  certaintyVariant: BadgeVariant
  rationale: string | null
}

function certaintyKeyOf(value: string | null | undefined): string {
  return value?.trim().toLowerCase().replace(/[\s-]+/g, "_") ?? ""
}

function capitalizeFirst(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1)
}

function startingCertainty(row: GradeSofRow): string {
  const explicit = certaintyKeyOf(row.starting_certainty)
  if (explicit) return explicit
  const design = certaintyKeyOf(row.study_design)
  if (!design) return ""
  return RANDOMISED_DESIGNS.has(design) ? "high" : "low"
}

function downgradeNoteFor(row: GradeSofRow, downgrades: string[], certaintyKey: string): string {
  if (downgrades.length > 0) return downgrades.join(", ")
  const start = startingCertainty(row)
  if (start && start === certaintyKey && start !== "high") {
    const design = certaintyKeyOf(row.study_design)
    const why = design && !RANDOMISED_DESIGNS.has(design) ? " (observational design)" : ""
    return `Starts ${humanizeIdentifier(start).toLowerCase()}${why}`
  }
  return "None"
}

function isSerious(judgment: unknown): judgment is string {
  return typeof judgment === "string" && /^(very )?serious$/i.test(judgment.trim())
}

export function gradeRowView(row: GradeSofRow, index: number): GradeRowView {
  const outcomeName = row.outcome_name?.trim()
  const outcome = outcomeName ? capitalizeFirst(outcomeName) : null
  const design = row.study_design?.trim()
  const designLabel = design ? DESIGN_LABELS[design.toLowerCase()] ?? humanizeIdentifier(design) : null
  const count = row.n_studies != null && row.n_studies > 0 ? `${row.n_studies} ${row.n_studies === 1 ? "study" : "studies"}` : null
  const studies = [count, designLabel].filter(Boolean).join(" · ") || null
  const downgrades = DOMAINS.filter(({ key }) => isSerious(row[key])).map(({ key, label }) => {
    const judgment = String(row[key]).trim().toLowerCase()
    return judgment === "serious" ? label : `${label} (very serious)`
  })
  const certaintyKey = certaintyKeyOf(row.certainty)
  return {
    key: `${index}-${outcome ?? "outcome"}`,
    outcome,
    studies,
    downgrades,
    downgradeNote: downgradeNoteFor(row, downgrades, certaintyKey),
    certainty: certaintyKey ? humanizeIdentifier(certaintyKey) : null,
    certaintyVariant: CERTAINTY_BADGE[certaintyKey] ?? "neutral",
    rationale: row.effect_summary?.trim() || null,
  }
}
