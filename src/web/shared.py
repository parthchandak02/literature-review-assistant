"""Shared pure utility functions and request/response models for the web layer.

This module contains helpers used across multiple router modules but does NOT
depend on mutable process state (like ``_active_runs``).  Import mutable state
from ``src.web.state`` instead.
"""

from __future__ import annotations

import datetime
import json as _json
import logging
import pathlib
import sqlite3
from typing import Any, Literal

import aiosqlite
import pydantic
from fastapi import HTTPException
from pydantic import BaseModel

from src.db.workflow_registry import _open_registry as _open_registry_db
from src.models import ManuscriptAuditResult

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class RunRequest(BaseModel):
    review_yaml: str
    gemini_api_key: str = ""
    deepseek_api_key: str | None = None
    openrouter_api_key: str | None = None
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    groq_api_key: str | None = None
    mistral_api_key: str | None = None
    cohere_api_key: str | None = None
    openalex_api_key: str | None = None
    ieee_api_key: str | None = None
    pubmed_email: str | None = None
    pubmed_api_key: str | None = None
    perplexity_api_key: str | None = None
    semantic_scholar_api_key: str | None = None
    crossref_email: str | None = None
    wos_api_key: str | None = None
    scopus_api_key: str | None = None
    run_root: str = "runs"
    parent_db_path: str | None = None


class RunResponse(BaseModel):
    run_id: str
    topic: str


class HistoryEntry(BaseModel):
    workflow_id: str
    topic: str
    status: str
    db_path: str
    created_at: str
    updated_at: str | None = None
    papers_found: int | None = None
    papers_included: int | None = None
    total_cost: float | None = None
    artifacts_count: int | None = None
    stats_ok: bool | None = None
    stats_error: str | None = None
    live_run_id: str | None = None
    notes: str | None = None
    is_archived: bool = False
    archived_at: str | None = None
    is_completed_hidden: bool = False
    completed_hidden_at: str | None = None


class AttachRequest(BaseModel):
    workflow_id: str
    topic: str
    db_path: str
    status: str = "completed"


class ResumeRequest(BaseModel):
    workflow_id: str
    db_path: str
    topic: str
    from_phase: str | None = None
    verbose: bool = False
    debug: bool = False


class _NoteBody(BaseModel):
    note: str
    run_root: str = "runs"


class _GenerateConfigRequest(BaseModel):
    research_question: str
    deepseek_api_key: str = ""
    gemini_api_key: str = ""
    generation_profile: Literal["standard", "health_sdg"] = "standard"


class ScreeningOverride(pydantic.BaseModel):
    """A single human override of an AI screening decision."""

    paper_id: str
    decision: str  # 'include' | 'exclude'
    reason: str | None = None


class ApproveScreeningRequest(pydantic.BaseModel):
    """Request body for approve-screening endpoint."""

    overrides: list[ScreeningOverride] = []


# ---------------------------------------------------------------------------
# Pure utility functions
# ---------------------------------------------------------------------------


def _is_missing_table_error(exc: Exception, table_names: set[str]) -> bool:
    """Return True when sqlite reports a missing table from a known set."""
    if not isinstance(exc, sqlite3.OperationalError):
        return False
    text = str(exc).lower()
    if "no such table" not in text:
        return False
    return any(name.lower() in text for name in table_names)


def _validate_db_path(path: str, run_root: str | None = None) -> pathlib.Path:
    """Resolve and validate a user-supplied database path.

    When *run_root* is provided, the resolved path must be under that directory.
    Always requires the path to end with ``.db`` and exist on disk.
    Raises HTTPException(400) on validation failure.
    """
    resolved = pathlib.Path(path).resolve()
    if run_root is not None:
        root = pathlib.Path(run_root).resolve()
        try:
            resolved.relative_to(root)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid database path")
    if not resolved.suffix == ".db":
        raise HTTPException(status_code=400, detail="Invalid database path")
    if not resolved.is_file():
        raise HTTPException(status_code=400, detail="Invalid database path")
    return resolved


def _json_safe(obj: Any) -> str:
    def _default(o: Any) -> Any:
        try:
            return str(o)
        except Exception:
            return None

    return _json.dumps(obj, default=_default)


def _normalize_status(value: str | None) -> str:
    s = (value or "").strip().lower()
    if s in ("done", "completed", "success"):
        return "completed"
    if s in ("failed", "error"):
        return "failed"
    if s in ("cancelled", "interrupted"):
        return "interrupted"
    return s


def _parse_sqlite_ts(value: Any) -> datetime.datetime | None:
    if value is None:
        return None
    try:
        ts = datetime.datetime.fromisoformat(str(value))
    except Exception:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=datetime.UTC)
    return ts


def _age_seconds(value: Any) -> float | None:
    ts = _parse_sqlite_ts(value)
    if ts is None:
        return None
    return (datetime.datetime.now(datetime.UTC) - ts).total_seconds()


async def _resolve_db_path(run_root: str, workflow_id: str) -> str | None:
    """Look up db_path in the central workflows_registry.db."""
    registry = pathlib.Path(run_root) / "workflows_registry.db"
    if not registry.exists():
        return None
    try:
        async with _open_registry_db(str(registry)) as db:
            async with db.execute(
                "SELECT db_path FROM workflows_registry WHERE workflow_id = ?",
                (workflow_id,),
            ) as cursor:
                row = await cursor.fetchone()
                return str(row[0]) if row else None
    except Exception:
        return None


async def _ensure_runtime_db_migrated(db_path: str) -> None:
    """Run runtime.db migrations once before historical read endpoints use it."""
    try:
        from src.db.database import get_db as _get_db
        from src.db.repositories import WorkflowRepository as _WorkflowRepository

        async with _get_db(db_path) as _db:
            try:
                _repo = _WorkflowRepository(_db)
                async with _db.execute("SELECT workflow_id FROM workflows ORDER BY created_at DESC LIMIT 1") as _cur:
                    _row = await _cur.fetchone()
                if _row and _row[0]:
                    _wid = str(_row[0])
                    await _repo.backfill_manuscript_sections_from_drafts(_wid)
                    _legacy_md = pathlib.Path(db_path).parent / "doc_manuscript.md"
                    if _legacy_md.exists():
                        try:
                            parity = await _repo.validate_manuscript_md_parity(
                                _wid, _legacy_md.read_text(encoding="utf-8")
                            )
                            if parity.has_assembly and not (parity.citation_set_match and parity.section_count_match):
                                _logger.warning(
                                    "runtime.db manuscript parity warning for %s: %s",
                                    _wid,
                                    parity,
                                )
                        except Exception as _parity_exc:
                            _logger.debug("runtime.db manuscript parity check skipped: %s", _parity_exc)
            except Exception as _bf_exc:
                _logger.debug("runtime.db manuscript backfill skipped: %s", _bf_exc)
    except Exception as exc:
        _logger.warning("Historical runtime.db migration skipped for %s: %s", db_path, exc)


async def _resolve_workflow_id_from_db(db_path: str) -> str | None:
    try:
        async with aiosqlite.connect(db_path) as db:
            async with db.execute("SELECT workflow_id FROM workflows ORDER BY rowid DESC LIMIT 1") as cur:
                row = await cur.fetchone()
                if row and row[0]:
                    return str(row[0])
    except Exception:
        return None
    return None


async def _query_included_papers_rows(
    db: aiosqlite.Connection,
    workflow_id: str,
    *,
    for_fetch: bool,
) -> list[aiosqlite.Row]:
    """Return included-paper rows with fulltext->extraction fallback precedence."""
    if for_fetch:
        primary_select_cols = "p.paper_id, p.title, p.authors, p.year, p.doi, p.url, p.source_database"
        legacy_select_cols = primary_select_cols
        order_by = "p.paper_id"
        fallback_select_cols = primary_select_cols
    else:
        primary_select_cols = (
            "p.paper_id, p.title, p.authors, p.year, p.source_database, p.doi, p.url, p.country, "
            "'include' AS final_decision"
        )
        legacy_select_cols = (
            "p.paper_id, p.title, p.authors, p.year, p.source_database, p.doi, p.url, p.country, ft.final_decision"
        )
        order_by = "p.year DESC"
        fallback_select_cols = (
            "p.paper_id, p.title, p.authors, p.year, p.source_database, p.doi, p.url, p.country, "
            "'include' AS final_decision"
        )

    primary_query = f"""
        SELECT {primary_select_cols}
        FROM papers p
        JOIN study_cohort_membership scm
          ON p.paper_id = scm.paper_id
        WHERE scm.workflow_id = ?
          AND scm.synthesis_eligibility = 'included_primary'
        ORDER BY {order_by}
    """
    async with db.execute(primary_query, (workflow_id,)) as cur:
        rows = await cur.fetchall()
    if rows:
        return rows

    legacy_query = f"""
        SELECT {legacy_select_cols}
        FROM papers p
        JOIN dual_screening_results ft
          ON p.paper_id = ft.paper_id AND ft.stage = 'fulltext'
        WHERE ft.workflow_id = ? AND ft.final_decision = 'include'
        ORDER BY {order_by}
    """
    async with db.execute(legacy_query, (workflow_id,)) as cur:
        rows = await cur.fetchall()
    if rows:
        return rows

    fallback_query = f"""
        SELECT {fallback_select_cols}
        FROM papers p
        JOIN extraction_records er
          ON p.paper_id = er.paper_id AND er.workflow_id = ?
        ORDER BY {order_by}
    """
    async with db.execute(fallback_query, (workflow_id,)) as fallback_cur:
        return await fallback_cur.fetchall()


_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "of",
        "in",
        "on",
        "to",
        "for",
        "with",
        "is",
        "are",
        "what",
        "how",
        "why",
        "which",
        "that",
        "this",
        "do",
        "does",
        "from",
        "by",
        "at",
        "as",
        "its",
    }
)


def _make_download_slug(workflow_id: str, topic: str, max_words: int = 5) -> str:
    """Build a filesystem-safe download slug: '<workflow_id>-<short-topic>'."""
    import re

    words = re.sub(r"[^a-zA-Z0-9 ]", " ", topic).lower().split()
    meaningful = [w for w in words if w not in _STOP_WORDS and len(w) > 1]
    short = "-".join(meaningful[:max_words]) if meaningful else "review"
    return f"{workflow_id}-{short}"


async def _get_topic_for_db(db_path: str) -> str:
    """Read topic from the workflows table in *db_path*. Returns empty string on failure."""
    try:
        async with aiosqlite.connect(db_path) as db:
            async with db.execute("SELECT topic FROM workflows LIMIT 1") as cur:
                row = await cur.fetchone()
                return str(row[0]) if row and row[0] else ""
    except Exception:
        return ""


def _format_manuscript_audit_summary(latest_run: ManuscriptAuditResult | None) -> dict[str, Any] | None:
    if latest_run is None:
        return None
    gate_action = str(latest_run.gate_action or "strict_block")
    gate_blocked = bool(latest_run.gate_blocked)
    passed = bool(latest_run.passed)
    if gate_blocked and gate_action == "advisory_only":
        status_label = "completed_with_findings"
    elif gate_blocked:
        status_label = "blocked"
    elif passed:
        status_label = "passed"
    else:
        status_label = "completed_with_findings"
    return {
        "audit_run_id": latest_run.audit_run_id,
        "verdict": latest_run.verdict,
        "passed": passed,
        "gate_blocked": gate_blocked,
        "gate_mode": latest_run.gate_mode,
        "gate_action": gate_action,
        "status_label": status_label,
        "blocking_count": int(latest_run.blocking_count or 0),
        "total_findings": int(latest_run.total_findings or 0),
        "summary": str(latest_run.summary or ""),
        "top_recommendations": list(latest_run.top_recommendations or []),
        "gate_failure_reasons": list(latest_run.gate_failure_reasons or []),
        "last_audited_at": latest_run.last_audited_at or latest_run.created_at,
    }
