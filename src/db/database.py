"""SQLite connection and migration helpers."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
_logger = logging.getLogger(__name__)


async def _init_connection(db: aiosqlite.Connection) -> None:
    await db.execute("PRAGMA journal_mode = WAL")
    await db.execute("PRAGMA synchronous = NORMAL")
    await db.execute("PRAGMA foreign_keys = ON")
    await db.execute("PRAGMA cache_size = 10000")
    await db.execute("PRAGMA temp_store = MEMORY")


async def run_migrations(db: aiosqlite.Connection) -> None:
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    try:
        await db.executescript(schema_sql)
    except Exception as exc:
        msg = str(exc).lower()
        # Historical DBs can fail on new desired-state indexes that reference columns
        # introduced by later ordered migrations. Apply a compatibility pass and
        # then let ordered migrations bring the DB up to date.
        if "no such column: workflow_id" in msg:
            compat_sql = schema_sql.replace(
                "CREATE INDEX IF NOT EXISTS idx_decision_log_workflow_phase ON decision_log(workflow_id, phase);",
                "",
            )
            await db.executescript(compat_sql)
        else:
            raise
    await db.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
    async with db.execute("SELECT COALESCE(MAX(version), 0) FROM schema_version") as cur:
        row = await cur.fetchone()
    current_version = int(row[0]) if row and row[0] is not None else 0

    async def _apply(version: int, sql: str) -> None:
        nonlocal current_version
        if current_version >= version:
            return
        for stmt in (s.strip() for s in sql.split(";")):
            if not stmt:
                continue
            try:
                await db.execute(stmt)
            except Exception as exc:
                msg = str(exc).lower()
                # Idempotent re-runs on older/newer DBs may already have these columns.
                if "duplicate column name" in msg or "already exists" in msg:
                    continue
                raise
        await db.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))
        current_version = version

    # 1. Add canonical papers metadata fields used by UI and export.
    await _apply(
        1,
        """
        ALTER TABLE papers ADD COLUMN country TEXT;
        ALTER TABLE papers ADD COLUMN display_label TEXT;
        """,
    )
    # 2. Persist dedup count for PRISMA accounting.
    await _apply(2, "ALTER TABLE workflows ADD COLUMN dedup_count INTEGER;")
    # 3. Ensure extraction source is first-class in extraction_records.
    await _apply(
        3,
        "ALTER TABLE extraction_records ADD COLUMN extraction_source TEXT NOT NULL DEFAULT 'text';",
    )
    # 4. Add workflow_id to cost_records for cross-run analytics and robust attribution.
    await _apply(
        4,
        "ALTER TABLE cost_records ADD COLUMN workflow_id TEXT NOT NULL DEFAULT '';",
    )
    # 5. Performance and activity-log indexes for production workloads.
    await _apply(
        5,
        """
        CREATE INDEX IF NOT EXISTS idx_search_results_workflow ON search_results(workflow_id);
        CREATE INDEX IF NOT EXISTS idx_dual_screening_stage_decision
            ON dual_screening_results(workflow_id, stage, final_decision);
        CREATE INDEX IF NOT EXISTS idx_extraction_records_workflow ON extraction_records(workflow_id);
        CREATE INDEX IF NOT EXISTS idx_event_log_workflow_type ON event_log(workflow_id, event_type);
        CREATE INDEX IF NOT EXISTS idx_section_drafts_workflow ON section_drafts(workflow_id);
        CREATE INDEX IF NOT EXISTS idx_cost_records_phase_model ON cost_records(phase, model);
        """,
    )
    # 6. Add workflow attribution to decision log for deterministic per-run audit queries.
    await _apply(
        6,
        """
        ALTER TABLE decision_log ADD COLUMN workflow_id TEXT NOT NULL DEFAULT '';
        CREATE INDEX IF NOT EXISTS idx_decision_log_workflow_phase ON decision_log(workflow_id, phase);
        """,
    )
    # 7. Persist per-section RAG retrieval diagnostics.
    await _apply(
        7,
        """
        CREATE TABLE IF NOT EXISTS rag_retrieval_diagnostics (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            workflow_id         TEXT NOT NULL,
            section             TEXT NOT NULL,
            query_type          TEXT NOT NULL,
            rerank_enabled      INTEGER NOT NULL DEFAULT 1,
            candidate_k         INTEGER NOT NULL,
            final_k             INTEGER NOT NULL,
            retrieved_count     INTEGER NOT NULL DEFAULT 0,
            status              TEXT NOT NULL,
            selected_chunks_json TEXT NOT NULL DEFAULT '[]',
            error_message       TEXT,
            latency_ms          INTEGER,
            created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_rag_diag_workflow_section
            ON rag_retrieval_diagnostics(workflow_id, section, created_at);
        """,
    )
    # 8. DB-first manuscript source-of-truth tables.
    await _apply(
        8,
        """
        CREATE TABLE IF NOT EXISTS manuscript_sections (
            workflow_id TEXT NOT NULL,
            section_key TEXT NOT NULL,
            section_order INTEGER NOT NULL,
            version INTEGER NOT NULL,
            title TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft',
            source TEXT NOT NULL,
            boundary_confidence REAL NOT NULL DEFAULT 1.0,
            content_hash TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (workflow_id, section_key, version)
        );
        CREATE TABLE IF NOT EXISTS manuscript_blocks (
            workflow_id TEXT NOT NULL,
            section_key TEXT NOT NULL,
            section_version INTEGER NOT NULL,
            block_order INTEGER NOT NULL,
            block_type TEXT NOT NULL,
            text TEXT NOT NULL,
            meta_json TEXT NOT NULL DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (workflow_id, section_key, section_version, block_order)
        );
        CREATE TABLE IF NOT EXISTS manuscript_assets (
            workflow_id TEXT NOT NULL,
            asset_key TEXT NOT NULL,
            asset_type TEXT NOT NULL,
            format TEXT NOT NULL,
            content TEXT NOT NULL,
            source_path TEXT,
            version INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (workflow_id, asset_key, version)
        );
        CREATE TABLE IF NOT EXISTS manuscript_assemblies (
            workflow_id TEXT NOT NULL,
            assembly_id TEXT NOT NULL,
            target_format TEXT NOT NULL,
            content TEXT NOT NULL,
            manifest_json TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (workflow_id, assembly_id, target_format)
        );
        CREATE INDEX IF NOT EXISTS idx_manuscript_sections_workflow_order
            ON manuscript_sections(workflow_id, section_order);
        CREATE INDEX IF NOT EXISTS idx_manuscript_blocks_workflow_section_order
            ON manuscript_blocks(workflow_id, section_key, section_version, block_order);
        CREATE INDEX IF NOT EXISTS idx_manuscript_assets_workflow_type_key
            ON manuscript_assets(workflow_id, asset_type, asset_key);
        """,
    )
    # 9. Deterministic ordering semantics for manuscript sections.
    await _apply(
        9,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_manuscript_sections_workflow_order_version
            ON manuscript_sections(workflow_id, section_order, version);
        """,
    )
    # 10. Canonical primary-study classification status on extraction records.
    await _apply(
        10,
        "ALTER TABLE extraction_records ADD COLUMN primary_study_status TEXT NOT NULL DEFAULT 'unknown';",
    )
    # 11. Canonical cohort membership ledger across screening/synthesis/export.
    await _apply(
        11,
        """
        CREATE TABLE IF NOT EXISTS study_cohort_membership (
            workflow_id TEXT NOT NULL,
            paper_id TEXT NOT NULL REFERENCES papers(paper_id),
            screening_status TEXT NOT NULL DEFAULT 'unknown',
            fulltext_status TEXT NOT NULL DEFAULT 'unknown',
            synthesis_eligibility TEXT NOT NULL DEFAULT 'pending',
            exclusion_reason_code TEXT,
            source_phase TEXT NOT NULL DEFAULT 'unknown',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (workflow_id, paper_id)
        );
        CREATE INDEX IF NOT EXISTS idx_study_cohort_workflow
            ON study_cohort_membership(workflow_id);
        CREATE INDEX IF NOT EXISTS idx_study_cohort_synthesis
            ON study_cohort_membership(workflow_id, synthesis_eligibility);
        """,
    )
    # 12. Screening decision idempotency for resume/re-run safety.
    await _apply(
        12,
        """
        DELETE FROM screening_decisions
        WHERE id NOT IN (
            SELECT MAX(id)
            FROM screening_decisions
            GROUP BY workflow_id, paper_id, stage, reviewer_type
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_screening_decisions_unique
            ON screening_decisions(workflow_id, paper_id, stage, reviewer_type);
        """,
    )
    # 13. Manuscript audit persistence tables (phase_7_audit).
    await _apply(
        13,
        """
        CREATE TABLE IF NOT EXISTS manuscript_audit_runs (
            audit_run_id TEXT PRIMARY KEY,
            workflow_id TEXT NOT NULL,
            mode TEXT NOT NULL,
            verdict TEXT NOT NULL,
            passed INTEGER NOT NULL,
            selected_profiles_json TEXT NOT NULL DEFAULT '[]',
            summary TEXT NOT NULL DEFAULT '',
            total_findings INTEGER NOT NULL DEFAULT 0,
            major_count INTEGER NOT NULL DEFAULT 0,
            minor_count INTEGER NOT NULL DEFAULT 0,
            note_count INTEGER NOT NULL DEFAULT 0,
            blocking_count INTEGER NOT NULL DEFAULT 0,
            contract_mode TEXT NOT NULL DEFAULT 'observe',
            contract_passed INTEGER NOT NULL DEFAULT 1,
            contract_violation_count INTEGER NOT NULL DEFAULT 0,
            contract_violations_json TEXT NOT NULL DEFAULT '[]',
            gate_blocked INTEGER NOT NULL DEFAULT 0,
            gate_failure_reasons_json TEXT NOT NULL DEFAULT '[]',
            total_cost_usd REAL NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS manuscript_audit_findings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            audit_run_id TEXT NOT NULL REFERENCES manuscript_audit_runs(audit_run_id),
            workflow_id TEXT NOT NULL,
            finding_id TEXT NOT NULL,
            profile TEXT NOT NULL,
            severity TEXT NOT NULL,
            category TEXT NOT NULL,
            section TEXT,
            evidence TEXT NOT NULL,
            recommendation TEXT NOT NULL,
            owner_module TEXT NOT NULL,
            blocking INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_manuscript_audit_runs_workflow
            ON manuscript_audit_runs(workflow_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_manuscript_audit_findings_run
            ON manuscript_audit_findings(audit_run_id, id);
        """,
    )
    # 14. Persist contract and gate-block metadata on manuscript audit runs.
    await _apply(
        14,
        """
        ALTER TABLE manuscript_audit_runs ADD COLUMN contract_mode TEXT NOT NULL DEFAULT 'observe';
        ALTER TABLE manuscript_audit_runs ADD COLUMN contract_passed INTEGER NOT NULL DEFAULT 1;
        ALTER TABLE manuscript_audit_runs ADD COLUMN contract_violation_count INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE manuscript_audit_runs ADD COLUMN contract_violations_json TEXT NOT NULL DEFAULT '[]';
        ALTER TABLE manuscript_audit_runs ADD COLUMN gate_blocked INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE manuscript_audit_runs ADD COLUMN gate_failure_reasons_json TEXT NOT NULL DEFAULT '[]';
        """,
    )
    await _validate_schema_contract(db)
    await db.commit()


async def _table_columns(db: aiosqlite.Connection, table: str) -> set[str]:
    async with db.execute(f"PRAGMA table_info({table})") as cur:
        rows = await cur.fetchall()
    return {str(row[1]) for row in rows}


async def _validate_schema_contract(db: aiosqlite.Connection) -> None:
    """Fail fast when critical runtime.db contract columns are missing."""
    required: dict[str, set[str]] = {
        "event_log": {"workflow_id", "event_type", "payload", "ts"},
        "cost_records": {"workflow_id", "model", "phase", "tokens_in", "tokens_out", "cost_usd", "latency_ms"},
        "decision_log": {"workflow_id", "decision_type", "phase", "actor"},
        "dual_screening_results": {"workflow_id", "paper_id", "stage", "final_decision"},
        "screening_decisions": {"workflow_id", "paper_id", "stage", "decision"},
        "extraction_records": {
            "workflow_id",
            "paper_id",
            "study_design",
            "primary_study_status",
            "extraction_source",
            "data",
        },
        "study_cohort_membership": {
            "workflow_id",
            "paper_id",
            "screening_status",
            "fulltext_status",
            "synthesis_eligibility",
            "source_phase",
        },
        "section_drafts": {"workflow_id", "section", "version", "content"},
        "manuscript_sections": {"workflow_id", "section_key", "section_order", "version", "content"},
        "manuscript_blocks": {"workflow_id", "section_key", "section_version", "block_order", "block_type", "text"},
        "manuscript_assemblies": {"workflow_id", "assembly_id", "target_format", "content", "manifest_json"},
        "manuscript_audit_runs": {
            "audit_run_id",
            "workflow_id",
            "mode",
            "verdict",
            "passed",
            "contract_mode",
            "contract_passed",
            "gate_blocked",
        },
        "manuscript_audit_findings": {"audit_run_id", "workflow_id", "finding_id", "severity", "evidence"},
    }
    for table, required_cols in required.items():
        cols = await _table_columns(db, table)
        missing = sorted(required_cols - cols)
        if missing:
            raise RuntimeError(f"runtime.db schema contract violation: {table} missing columns: {missing}")


async def repair_foreign_key_integrity(db: aiosqlite.Connection) -> int:
    """Insert stub papers for orphaned paper_id references and stub workflows for
    orphaned workflow_id references. Returns count of stubs inserted.

    Old DBs may have screening_decisions, extraction_records, checkpoints, etc.
    referencing paper_ids or workflow_ids not in papers/workflows (e.g. from
    migration or corruption). This causes FOREIGN KEY constraint failed on INSERT.
    We insert minimal stub rows.
    """
    cursor = await db.execute("SELECT paper_id FROM papers")
    existing_papers = {str(row[0]) for row in await cursor.fetchall()}
    missing_papers: set[str] = set()

    async def collect_paper_ids(query: str, col_idx: int = 0) -> None:
        try:
            cur = await db.execute(query)
            for row in await cur.fetchall():
                pid = str(row[col_idx]) if row else None
                if pid and pid not in existing_papers:
                    missing_papers.add(pid)
        except Exception as e:
            _logger.debug("repair_foreign_key_integrity: skip query %s: %s", query[:50], e)

    await collect_paper_ids("SELECT DISTINCT paper_id FROM screening_decisions")
    await collect_paper_ids("SELECT DISTINCT paper_id FROM dual_screening_results")
    await collect_paper_ids("SELECT DISTINCT paper_id FROM extraction_records")
    await collect_paper_ids("SELECT DISTINCT paper_id FROM paper_chunks_meta")
    await collect_paper_ids("SELECT DISTINCT paper_id FROM screening_corrections")
    await collect_paper_ids("SELECT DISTINCT paper_id FROM rob_assessments")
    await collect_paper_ids("SELECT DISTINCT source_paper_id FROM paper_relationships", 0)
    await collect_paper_ids("SELECT DISTINCT target_paper_id FROM paper_relationships", 0)

    inserted = 0
    for pid in missing_papers:
        try:
            await db.execute(
                """
                INSERT OR IGNORE INTO papers
                (paper_id, title, authors, source_database, source_category)
                VALUES (?, '[Recovered]', '[]', 'integrity_repair', 'database')
                """,
                (pid,),
            )
            inserted += 1
        except Exception as e:
            _logger.warning("repair_foreign_key_integrity: could not insert stub paper %s: %s", pid, e)

    # Stub workflows for orphaned workflow_id refs (e.g. checkpoints referencing
    # workflows that were never created or were deleted).
    try:
        cur = await db.execute("SELECT workflow_id FROM workflows")
        existing_workflows = {str(row[0]) for row in await cur.fetchall()}
        missing_workflows: set[str] = set()
        for table, col in [("checkpoints", "workflow_id")]:
            try:
                cur = await db.execute(f"SELECT DISTINCT {col} FROM {table}")
                for row in await cur.fetchall():
                    wid = str(row[0]) if row else None
                    if wid and wid not in existing_workflows:
                        missing_workflows.add(wid)
            except Exception as e:
                _logger.debug("repair_foreign_key_integrity: skip %s.%s: %s", table, col, e)
        for wid in missing_workflows:
            try:
                await db.execute(
                    """
                    INSERT OR IGNORE INTO workflows (workflow_id, topic, config_hash, status)
                    VALUES (?, '[Recovered]', '', 'running')
                    """,
                    (wid,),
                )
                inserted += 1
            except Exception as e:
                _logger.warning("repair_foreign_key_integrity: could not insert stub workflow %s: %s", wid, e)
    except Exception as e:
        _logger.debug("repair_foreign_key_integrity: workflow stub phase skipped: %s", e)

    if inserted:
        await db.commit()
        _logger.info("repair_foreign_key_integrity: inserted %d stub rows for orphaned refs", inserted)
    return inserted


@asynccontextmanager
async def get_db(db_path: str = "data/checkpoints/review_state.db") -> AsyncIterator[aiosqlite.Connection]:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = await aiosqlite.connect(str(path))
    try:
        db.row_factory = aiosqlite.Row
        await _init_connection(db)
        await run_migrations(db)
        yield db
    finally:
        await db.close()
