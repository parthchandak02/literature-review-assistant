---
name: run-database-audit
description: Audits live or completed run databases using SQL queries, CSV exports, and YAML alignment checks. Use when the user asks for manual run verification, why papers were included or excluded, mid-workflow validation, runtime.db analysis, or database-driven debugging across running, cancelled, interrupted, or completed runs.
---

# Run Database Audit

## Purpose

Use this skill to do database-first run audits that are evidence-first:
- Resolve any run from `workflow_id` to `runtime.db`.
- Query live or historical run state from SQLite tables.
- Export paper-level screening details to CSV.
- Analyze gate behavior and rationale quality.
- Check alignment with review YAML intent.
- Recommend pipeline fixes, not run artifact edits.

## Operational Learnings To Apply

Apply these defaults unless the user asks otherwise:
- Treat a run as healthy when `progress` events keep advancing for the active phase.
- Use a stall threshold: if active phase progress does not advance for 10+ minutes, escalate to a blocker check.
- For CSV row counts, do not trust physical line counts when abstracts contain embedded newlines; parse CSV rows.
- In connector footprint queries, avoid assuming optional columns like `error_message` exist in `search_results`.
- For final included-study audits, use `study_cohort_membership` (`synthesis_eligibility='included_primary'`) as the canonical set, with `dual_screening_results` as fallback for legacy runs.
- Always run a final-include sanity scan for review/protocol-style titles against strict primary-study criteria.

## When To Apply

Apply when requests include:
- manual check
- why included
- why excluded
- screening audit
- mid-workflow test
- csv output analysis
- config yaml alignment
- is screening logic working
- database audit
- runtime.db check
- running or cancelled run check
- are we on track

## Required Workflow

1. Resolve run database context
- Identify `workflow_id`.
- Resolve `runtime.db` via `runs/workflows_registry.db`.
- Read the run `config_snapshot.yaml` or `review.yaml` in run directory.

2. Run SQL evidence queries first
- Always pull:
  - run status and heartbeat from registry
  - event progression from `event_log`
  - gate counts from `screening_decisions` and `decision_log`
  - connector retrieval counts from `search_results`
- Use explicit SQL, then summarize results before recommending changes.
- If connector schema differs, first inspect with `PRAGMA table_info(search_results);` and adapt query columns.
- For replay validation audits, include:
  - `validation_runs` (latest profile/status)
  - `validation_checks` (phase-level failures/warnings)
  - `validation_artifacts` (if present)

3. Export detailed CSV outputs for manual review
- Create a run-scoped review folder:
  - Preferred: `<run_dir>/manual_review/`
  - Fallback: `runs/manual_review/`
- Export at minimum:
  - `*_screening_manual_review.csv` with paper metadata, abstract, per-gate decisions, reviewer A/B decisions, confidences, reasons, and latest final decision if available.
  - `*_reviewer_disagreements.csv` where reviewer A decision differs from reviewer B decision.
- After export, compute true row counts with a CSV parser and report parsed row totals.

4. Analyze outputs, do not stop at export
- Funnel and gate coverage:
  - deduped, to_llm, forwarded, currently finalized.
- Decision distribution:
  - by `keyword_filter`, `batch_ranker`, `reviewer_a`, `reviewer_b`.
- Quality signals:
  - out-of-domain includes,
  - low-confidence includes or excludes,
  - disagreement clusters,
  - repeated rationale patterns that indicate prompt drift.
- Include-specific sanity checks:
  - final includes containing keywords such as `systematic review`, `scoping review`, `narrative review`, `meta-analysis`, `protocol`.
  - final includes with likely non-target populations (for example, nursing-heavy titles if target is undergraduate medical students only).
- Disagreement split:
  - include/exclude pair counts (`reviewer_a` vs `reviewer_b`) to detect directional bias.

5. YAML alignment check
- Compare sampled include and exclude rationales against:
  - `research_question`,
  - `pico.population`, `pico.intervention`, `pico.outcome`,
  - inclusion and exclusion criteria.
- Flag mismatches as:
  - likely false include,
  - likely false exclude,
  - ambiguous, needs adjudication.

6. Recommend robust fixes
- Suggest code and config fix locations, for example:
  - `src/screening/dual_screener.py`
  - `src/screening/prompts.py`
  - `src/search/strategy.py`
  - `config/settings.yaml`
- Focus on process fixes that improve future runs.
- Never patch files under `runs/`.

## SQL Example Queries

Use these exact patterns as a baseline.

1) Resolve runtime.db:
```sql
SELECT workflow_id, status, db_path, heartbeat_at
FROM workflows_registry
WHERE workflow_id = 'wf-XXXX';
```

2) Stage progression snapshot:
```sql
SELECT event_type, COUNT(*)
FROM event_log
GROUP BY event_type
ORDER BY COUNT(*) DESC;
```

3) Gate-level decision counts:
```sql
SELECT reviewer_type, decision, COUNT(*)
FROM screening_decisions
GROUP BY reviewer_type, decision
ORDER BY reviewer_type, decision;
```

4) Connector retrieval footprint:
```sql
SELECT database_name, records_retrieved, limits_applied
FROM search_results
ORDER BY id;
```

5) Latest final screening decision rollup:
```sql
WITH finals AS (
  SELECT id, paper_id, decision
  FROM decision_log
  WHERE decision_type IN ('dual_screening_final', 'screening_adjudication', 'screening_protocol_heuristic')
    AND paper_id IS NOT NULL
),
latest AS (
  SELECT f.paper_id, f.decision
  FROM finals f
  JOIN (
    SELECT paper_id, MAX(id) AS max_id
    FROM finals
    GROUP BY paper_id
  ) m ON f.paper_id = m.paper_id AND f.id = m.max_id
)
SELECT decision, COUNT(*) FROM latest GROUP BY decision ORDER BY decision;
```

10) Latest validation run summary:
```sql
SELECT validation_run_id, profile, status, tool_version, started_at, completed_at
FROM validation_runs
WHERE workflow_id = 'wf-XXXX'
ORDER BY started_at DESC
LIMIT 1;
```

11) Validation check breakdown:
```sql
SELECT phase, check_name, status, severity, metric_value
FROM validation_checks
WHERE validation_run_id = 'val-XXXX'
ORDER BY id;
```

6) Live progress probe for active screening phase:
```sql
SELECT payload, ts
FROM event_log
WHERE event_type = 'progress'
  AND payload LIKE '%"phase": "phase_3_screening"%'
ORDER BY id DESC
LIMIT 20;
```

7) Canonical included set count:
```sql
SELECT COUNT(*) AS included_primary
FROM study_cohort_membership
WHERE workflow_id = 'wf-XXXX'
  AND synthesis_eligibility = 'included_primary';
```

8) Candidate include mismatch scan (title heuristic):
```sql
SELECT p.paper_id, p.title, p.year, p.source_database, p.doi
FROM study_cohort_membership scm
JOIN papers p ON p.paper_id = scm.paper_id
WHERE scm.workflow_id = 'wf-XXXX'
  AND scm.synthesis_eligibility = 'included_primary'
  AND (
    LOWER(p.title) LIKE '%review%' OR
    LOWER(p.title) LIKE '%scoping%' OR
    LOWER(p.title) LIKE '%narrative%' OR
    LOWER(p.title) LIKE '%meta-analysis%' OR
    LOWER(p.title) LIKE '%protocol%'
  )
ORDER BY p.title;
```

9) Manual review CSV export (sqlite3 shell):
```bash
sqlite3 -header -csv "<runtime.db>" "<SQL_QUERY>" > "<run_dir>/manual_review/<file>.csv"
```

## Control-Plane and Writing Diagnostics

When debugging step failures, stalled writing, retries, or fallback spikes, query these tables:

- `workflow_steps` -- per-phase step execution (status, duration, failure category, recovery action)
- `recovery_policies` -- retry/rewind accounting per phase+step
- `writing_manifests` -- per-section writing provenance (grounding hash, evidence IDs, contract status, retry count, fallback flag)

Quick SQL examples:

```sql
-- Step journal overview
SELECT phase, step_name, status, duration_ms, failure_category, recovery_action
FROM workflow_steps WHERE workflow_id = 'wf-XXXX' ORDER BY started_at;

-- Writing manifest per section
SELECT section_key, attempt_number, contract_status, word_count, fallback_used
FROM writing_manifests WHERE workflow_id = 'wf-XXXX' ORDER BY section_key;

-- Recovery policy exhaustion
SELECT phase, step_name, current_retries, max_retries, current_rewinds, max_rewinds, policy_status
FROM recovery_policies WHERE workflow_id = 'wf-XXXX';
```

API shortcut: `GET /api/run/{run_id}/diagnostics` returns aggregated step summary, failure counts, fallback events, and writing manifests.

Readiness check: `GET /api/run/{run_id}/readiness` returns the export readiness scorecard (finalize checkpoint, PRISMA arithmetic, contracts, fallback events, PDF presence).

## Live-Run Handling

- Running workflows: query the same DB repeatedly to confirm progress.
- Cancelled or interrupted workflows: audit last durable state from `event_log` and `decision_log`.
- Completed workflows: perform full ratio and rationale quality audit, then suggest pipeline fixes if needed.
- For workflow replay visibility, correlate DB checks with:
  - `GET /api/run/{run_id}/events` (live run replay buffer)
  - `GET /api/workflow/{workflow_id}/events` (historical DB replay)
  - `GET /api/workflow/{workflow_id}/validation/summary` and `/validation/checks`
- Health rule of thumb:
  - Healthy: active phase `progress.current` advances within repeated checks.
  - At risk: no active-phase progress delta for 5+ minutes.
  - Stalled: no active-phase progress delta for 10+ minutes; run blocker queries immediately and report as incident.

## Output Format

Use this structure:

1. Snapshot
- workflow id, run status, key counts.
- db path used and whether run is running/cancelled/interrupted/completed.

2. CSV artifacts
- exact output paths and row counts.

3. Findings
- top 3-7 anomalies with paper examples.

4. YAML alignment
- what matches intent and what does not.

5. Fix plan
- concrete next edits by file path.

Prefer CSV exports for manual review in spreadsheet tools and keep SQL snippets in the response so users can rerun them directly.
