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

3. Export detailed CSV outputs for manual review
- Create a run-scoped review folder:
  - Preferred: `<run_dir>/manual_review/`
  - Fallback: `runs/manual_review/`
- Export at minimum:
  - `*_screening_manual_review.csv` with paper metadata, abstract, per-gate decisions, reviewer A/B decisions, confidences, reasons, and latest final decision if available.
  - `*_reviewer_disagreements.csv` where reviewer A decision differs from reviewer B decision.

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

5) Manual review CSV export (sqlite3 shell):
```bash
sqlite3 -header -csv "<runtime.db>" "<SQL_QUERY>" > "<run_dir>/manual_review/<file>.csv"
```

## Live-Run Handling

- Running workflows: query the same DB repeatedly to confirm progress.
- Cancelled or interrupted workflows: audit last durable state from `event_log` and `decision_log`.
- Completed workflows: perform full ratio and rationale quality audit, then suggest pipeline fixes if needed.

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
