import type { ReviewEvent } from "./api"

export interface FunnelStage {
  key: string
  label: string
  count: number
  colorClass: string
}

/**
 * Derive the paper funnel stages from the SSE event stream.
 *
 * The full screening pipeline has eight stages derivable from stored events:
 *
 *   1. Raw searched       -- sum of connector_result.records (pre-dedup)
 *   2. After dedup        -- phase_done("phase_2_search").summary.papers
 *   3. After metadata     -- screening_prefilter_done.after_metadata
 *   4. BM25 selected      -- screening_prefilter_done.to_llm
 *                            (fallback: max progress.total for phase_3_screening)
 *                            These are the top-k papers selected by BM25 ranking,
 *                            which feed into the batch LLM pre-ranker.
 *   5. To dual-reviewer   -- batch_screen_done.forwarded
 *                            Papers that passed the batch LLM pre-ranker (score >= threshold).
 *                            Present only when batch ranking is enabled.
 *   6. Full-text assess   -- unique paper_ids in screening_decision where stage="fulltext"
 *   7. Final included     -- phase_done("phase_3_screening").summary.included
 *                            (live: count unique screening_decision includes)
 *   8. Via citation chase -- phase_done("citation_chasing").summary.chased_included
 *                            Only shown when > 0 additional papers were added via citation chasing.
 *
 * Stages are omitted when their count equals the previous stage (no meaningful
 * filter occurred) or when the count is not yet known.
 */
export function computeFunnelStages(events: ReviewEvent[]): FunnelStage[] {
  // --- Stage 1: raw searched ---
  let rawSearched = 0
  for (const e of events) {
    if (e.type === "connector_result" && e.status === "success") {
      rawSearched += e.records ?? 0
    }
  }

  // --- Stage 2: after dedup ---
  let deduped: number | null = null
  for (const e of events) {
    if (e.type === "phase_done" && e.phase === "phase_2_search") {
      const s = e.summary as Record<string, unknown> | null | undefined
      if (s?.papers != null) deduped = Number(s.papers)
    }
  }

  // --- Stages 3 & 4: from the new prefilter event ---
  let afterMetadata: number | null = null
  let toLlm: number | null = null
  for (const e of events) {
    if (e.type === "screening_prefilter_done") {
      afterMetadata = e.after_metadata
      toLlm = e.to_llm
    }
  }

  // Fallback for stage 4: max total seen in progress events for phase_3_screening.
  // This fires only after the first LLM paper begins, so it may lag by a few seconds.
  if (toLlm == null) {
    let maxProgressTotal = 0
    for (const e of events) {
      if (e.type === "progress" && e.phase === "phase_3_screening") {
        if (e.total > maxProgressTotal) maxProgressTotal = e.total
      }
    }
    if (maxProgressTotal > 0) toLlm = maxProgressTotal
  }

  // --- Stage 4b: batch LLM pre-ranker -> forwarded to dual-reviewer ---
  // Present only when batch_screen_done event exists (batch_screen_enabled=true).
  let toDualReview: number | null = null
  let capOverflowForwarded = 0
  for (const e of events) {
    if (e.type === "batch_screen_done") {
      const bs = e as unknown as Record<string, number>
      if (bs.forwarded != null) toDualReview = bs.forwarded
    }
    if (e.type === "screening_cap_overflow") {
      const ov = e as unknown as Record<string, number>
      capOverflowForwarded += ov.overflow_forwarded ?? 0
    }
  }
  if (toDualReview != null && capOverflowForwarded > 0) {
    toDualReview += capOverflowForwarded
  }

  // --- Stage 5: full-text assessed ---
  // Count unique paper_ids that have entered the full-text screening stage.
  const fulltextPaperIds = new Set<string>()
  for (const e of events) {
    if (e.type === "screening_decision" && e.stage === "fulltext") {
      fulltextPaperIds.add(e.paper_id)
    }
  }
  const fulltextAssessed = fulltextPaperIds.size > 0 ? fulltextPaperIds.size : null

  // --- Stage 6: included ---
  // Prefer the terminal phase_done count; fall back to fulltext-stage decisions.
  let included: number | null = null
  for (const e of events) {
    if (e.type === "phase_done" && e.phase === "phase_3_screening") {
      const s = e.summary as Record<string, unknown> | null | undefined
      if (s?.included != null) included = Number(s.included)
    }
  }
  if (included == null) {
    // First fallback: fulltext stage only, matching backend include semantics
    // (include OR uncertain after fulltext adjudication).
    const fulltextFinalDecision = new Map<string, string>()
    for (const e of events) {
      if (e.type === "screening_decision" && e.stage === "fulltext") {
        fulltextFinalDecision.set(e.paper_id, e.decision)
      }
    }
    const fulltextCount = [...fulltextFinalDecision.values()].filter(
      (d) => d === "include" || d === "uncertain",
    ).length
    if (fulltextCount > 0) {
      included = fulltextCount
    } else {
      // Legacy fallback for early-stage live runs where no fulltext decisions exist yet.
      const lastDecision = new Map<string, string>()
      for (const e of events) {
        if (e.type === "screening_decision") {
          lastDecision.set(e.paper_id, e.decision)
        }
      }
      const liveCount = [...lastDecision.values()].filter((d) => d === "include" || d === "uncertain").length
      if (liveCount > 0) included = liveCount
    }
  }

  // --- Stage 7: citation chasing additions ---
  // Papers found via citation chasing that passed screening. Only shown when > 0.
  // These papers are already counted within `included`; this stage surfaces that
  // citation chasing contributed additional papers beyond the main dual-reviewer pass.
  let chasedIncluded: number | null = null
  for (const e of events) {
    if (e.type === "phase_done" && e.phase === "citation_chasing") {
      const s = e.summary as Record<string, unknown> | null | undefined
      if (s?.chased_included != null) {
        const n = Number(s.chased_included)
        if (n > 0) chasedIncluded = n
      }
    }
  }

  // --- Build stage array, omitting unknown counts and no-op filters ---
  const stages: FunnelStage[] = []

  const push = (
    key: string,
    label: string,
    count: number | null,
    colorClass: string,
    prevCount: number | null,
  ) => {
    if (count == null || count <= 0) return
    // Omit if this stage did not filter anything relative to previous.
    if (prevCount != null && count === prevCount) return
    stages.push({ key, label, count, colorClass })
  }

  // Use deduped as the primary "start" count; fall back to raw if dedup not done yet.
  const startCount = deduped ?? (rawSearched > 0 ? rawSearched : null)

  // Show raw only when it meaningfully differs from deduped (duplicates were removed).
  if (rawSearched > 0 && deduped != null && rawSearched !== deduped) {
    stages.push({ key: "raw", label: "retrieved", count: rawSearched, colorClass: "text-blue-300" })
  }

  if (startCount != null && startCount > 0) {
    const prevCount = rawSearched > 0 && deduped != null && rawSearched !== deduped ? rawSearched : null
    push("deduped", "deduped", startCount, "text-blue-400", prevCount)
  }

  push("after_metadata", "filtered", afterMetadata, "text-violet-300", startCount)
  // "ranked" = top-k from keyword/BM25 ranking, fed into the batch LLM pre-ranker.
  push("to_llm", "ranked", toLlm, "text-violet-400", afterMetadata ?? startCount)
  // "screened" = papers that passed the batch LLM pre-ranker threshold.
  push("to_dual_review", "screened", toDualReview, "text-violet-500", toLlm ?? afterMetadata ?? startCount)
  push("fulltext", "eligible", fulltextAssessed, "text-amber-400", toDualReview ?? toLlm ?? afterMetadata ?? startCount)
  push("included", "included", included, "text-emerald-400", fulltextAssessed ?? toLlm ?? afterMetadata ?? startCount)

  // Citation chasing is additive (not a filter), so bypass the prev-count deduplication
  // by pushing directly. Only shown when citation chasing found at least one paper.
  if (chasedIncluded != null && chasedIncluded > 0) {
    stages.push({ key: "chased", label: "+ chased", count: chasedIncluded, colorClass: "text-teal-400" })
  }

  return stages
}
