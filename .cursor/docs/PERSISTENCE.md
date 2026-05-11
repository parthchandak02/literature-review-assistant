# Persistence Contract

## Databases

- Per-run runtime DB: `runs/.../runtime.db` (schema in `src/db/schema.sql`)
- Global workflow registry DB: `runs/workflows_registry.db` (schema in `src/db/workflow_registry.py`)

## Runtime DB Core Table Families

- Search and corpus: `papers`, `search_results`
- Screening: `screening_decisions`, `dual_screening_results`, `screening_corrections`
- Extraction and cohort: `extraction_records`, `study_cohort_membership`
- Synthesis and graph: `synthesis_results`, `paper_relationships`, `graph_communities`, `research_gaps`
- Writing and manuscript: `section_drafts`, `manuscript_sections`, `manuscript_blocks`, `manuscript_assets`
- Control plane: `workflow_steps`, `recovery_policies`, `writing_manifests`, `checkpoints`, `event_log`
- Validation and audit: `validation_runs`, `validation_checks`, `manuscript_audit_runs`, `manuscript_audit_findings`
- Cost tracking: `cost_records`

## Registry Responsibilities

`workflows_registry.db` tracks workflow identity, path resolution, status, archive buckets, and heartbeat metadata.

Use `db_path` from registry rows to resolve runtime DB locations.
Do not reconstruct run paths by string assumptions.

## Canonical Truth Rules

- Included studies canonical source: `study_cohort_membership` where `synthesis_eligibility='included_primary'`
- Cost canonical source: `cost_records`
- Status repair may use durable evidence (`event_log`, checkpoints, summaries), not in-memory state only

## Resume and Rewind

Resume checkpoints are backend-driven through `src/orchestration/resume.py` and persisted checkpoint rows.
When rewinding writing stages, clear associated outline/checkpoint state, not only section drafts.
