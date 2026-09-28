"""Database explorer endpoints: papers facets, suggest, all-papers, export, detail, tables, RAG diagnostics."""

from __future__ import annotations

import json as _json
from typing import Any

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from src.models.papers import decode_html_entities
from src.web.papers_query import (
    InvalidQueryError,
    PaperFilters,
    fetch_export_rows,
    fetch_facet_counts,
    fetch_outcome_tables,
    fetch_paper_detail,
    fetch_papers_page,
    to_csv,
    to_ris,
)
from src.web.run_resolver import resolve_runtime_db

router = APIRouter(tags=["database_explorer"])


def _parse_papers_include(include: str) -> set[str]:
    """Parse comma-separated include tokens for papers-all."""
    if not include:
        return set()
    return {part.strip() for part in include.split(",") if part.strip()}


async def _fetch_papers_facets(db: aiosqlite.Connection) -> dict[str, Any]:
    async with db.execute("SELECT DISTINCT year FROM papers WHERE year IS NOT NULL ORDER BY year DESC") as cur:
        years = [row[0] for row in await cur.fetchall()]
    async with db.execute(
        "SELECT DISTINCT source_database FROM papers WHERE source_database IS NOT NULL ORDER BY source_database"
    ) as cur:
        sources = [row[0] for row in await cur.fetchall()]
    async with db.execute("SELECT DISTINCT country FROM papers WHERE country IS NOT NULL ORDER BY country") as cur:
        countries = [row[0] for row in await cur.fetchall()]
    async with db.execute(
        "SELECT DISTINCT final_decision FROM dual_screening_results "
        "WHERE stage = 'title_abstract' AND final_decision IS NOT NULL ORDER BY final_decision"
    ) as cur:
        ta_decisions = [row[0] for row in await cur.fetchall()]
    async with db.execute(
        "SELECT DISTINCT final_decision FROM dual_screening_results "
        "WHERE stage = 'fulltext' AND final_decision IS NOT NULL ORDER BY final_decision"
    ) as cur:
        ft_decisions = [row[0] for row in await cur.fetchall()]
    async with db.execute(
        """
        SELECT DISTINCT COALESCE(
            er.primary_study_status,
            json_extract(er.data, '$.primary_study_status'),
            'unknown'
        ) AS primary_status
        FROM extraction_records er
        WHERE COALESCE(
            er.primary_study_status,
            json_extract(er.data, '$.primary_study_status'),
            'unknown'
        ) IS NOT NULL
        ORDER BY primary_status
        """
    ) as cur:
        primary_statuses = [row[0] for row in await cur.fetchall()]
    return {
        "years": years,
        "sources": sources,
        "countries": countries,
        "ta_decisions": ta_decisions,
        "ft_decisions": ft_decisions,
        "primary_statuses": primary_statuses,
    }


class _FilterParams:
    """Shared query params for papers-all, papers-facets and papers-export."""

    def __init__(
        self,
        search: str = "",
        title: str = "",
        author: str = "",
        ta_decision: list[str] = Query(default=[]),
        ft_decision: list[str] = Query(default=[]),
        primary_status: list[str] = Query(default=[]),
        year: str = "",
        year_min: int | None = None,
        year_max: int | None = None,
        source: list[str] = Query(default=[]),
        country: list[str] = Query(default=[]),
        match: str = "contains",
    ) -> None:
        try:
            self.filters = PaperFilters(
                search=search,
                title=title,
                author=author,
                ta_decision=ta_decision,
                ft_decision=ft_decision,
                primary_status=primary_status,
                year=year,
                year_min=year_min,
                year_max=year_max,
                source=source,
                country=country,
                match=match,  # type: ignore[arg-type]
            )
        except InvalidQueryError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/db/{run_id}/papers-facets")
async def get_papers_facets(run_id: str, params: _FilterParams = Depends()) -> dict[str, Any]:
    """Distinct values for filter columns, plus per-value counts that respect the other active filters."""
    db_path = await resolve_runtime_db(run_id)
    try:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            facets = await _fetch_papers_facets(db)
            facets["counts"] = await fetch_facet_counts(db, params.filters)
            return facets
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/db/{run_id}/papers-suggest")
async def get_papers_suggest(
    run_id: str,
    column: str,
    q: str = "",
    limit: int = 10,
) -> dict[str, Any]:
    """Return distinct matching values for a column for autocomplete (title and author)."""
    if column not in ("title", "author"):
        raise HTTPException(status_code=400, detail="column must be 'title' or 'author'")
    db_path = await resolve_runtime_db(run_id)
    try:
        async with aiosqlite.connect(db_path) as db:
            like = f"%{q}%"
            if column == "title":
                async with db.execute(
                    "SELECT DISTINCT title FROM papers WHERE title LIKE ? AND title IS NOT NULL ORDER BY title LIMIT ?",
                    (like, limit),
                ) as cur:
                    suggestions = [decode_html_entities(row[0]) for row in await cur.fetchall()]
            else:
                async with db.execute(
                    "SELECT DISTINCT authors FROM papers WHERE authors LIKE ? AND authors IS NOT NULL LIMIT ?",
                    (like, limit),
                ) as cur:
                    raw_rows = [row[0] for row in await cur.fetchall()]
                seen: set[str] = set()
                suggestions = []
                for raw in raw_rows:
                    try:
                        authors_list = _json.loads(raw) if raw.startswith("[") else [raw]
                        for a in authors_list:
                            name = (a.get("name") or a.get("raw_name") or str(a)) if isinstance(a, dict) else str(a)
                            name = decode_html_entities(name)
                            if q.lower() in name.lower() and name not in seen:
                                seen.add(name)
                                suggestions.append(name)
                                if len(suggestions) >= limit:
                                    break
                    except Exception:
                        if raw not in seen:
                            seen.add(raw)
                            suggestions.append(raw)
                    if len(suggestions) >= limit:
                        break
        return {"suggestions": suggestions}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/db/{run_id}/papers-all")
async def get_papers_all(
    run_id: str,
    params: _FilterParams = Depends(),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    include: str = "",
    sort: str = "",
    direction: str = Query("desc", alias="dir"),
) -> dict[str, Any]:
    """Unified per-paper table joining papers with final screening decisions."""
    db_path = await resolve_runtime_db(run_id)
    try:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            total, papers = await fetch_papers_page(
                db, params.filters, sort=sort, direction=direction, offset=offset, limit=limit
            )
            response: dict[str, Any] = {"total": total, "offset": offset, "limit": limit, "papers": papers}
            if "facets" in _parse_papers_include(include):
                facets = await _fetch_papers_facets(db)
                facets["counts"] = await fetch_facet_counts(db, params.filters)
                response["facets"] = facets
            return response
    except InvalidQueryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/db/{run_id}/papers-export")
async def export_papers(
    run_id: str,
    params: _FilterParams = Depends(),
    fmt: str = Query("csv", alias="format"),
    sort: str = "",
    direction: str = Query("desc", alias="dir"),
) -> Response:
    """Download the full filtered paper set as CSV or RIS (same filters and sort as papers-all)."""
    if fmt not in ("csv", "ris"):
        raise HTTPException(status_code=400, detail="format must be 'csv' or 'ris'")
    db_path = await resolve_runtime_db(run_id)
    try:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            rows = await fetch_export_rows(db, params.filters, sort=sort, direction=direction)
    except InvalidQueryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    safe_id = "".join(ch for ch in run_id if ch.isalnum() or ch in "-_") or "run"
    if fmt == "csv":
        body, media_type = to_csv(rows), "text/csv; charset=utf-8"
    else:
        body, media_type = to_ris(rows), "application/x-research-info-systems; charset=utf-8"
    return Response(
        content=body,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="papers-{safe_id}.{fmt}"'},
    )


@router.get("/api/db/{run_id}/papers/{paper_id}")
async def get_paper_detail(run_id: str, paper_id: str) -> dict[str, Any]:
    """Full record for one paper: metadata, abstract, per-stage screening reasons, extraction and quality summary."""
    db_path = await resolve_runtime_db(run_id)
    try:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            detail = await fetch_paper_detail(db, paper_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if detail is None:
        raise HTTPException(status_code=404, detail="Paper not found")
    return detail


@router.get("/api/db/{run_id}/tables")
async def get_db_tables(
    run_id: str,
    params: _FilterParams = Depends(),
    offset: int = Query(0, ge=0),
    limit: int | None = Query(None, ge=1, le=500),
) -> dict[str, Any]:
    """Numeric extracted outcome rows grouped by paper, optionally filtered and paginated by outcome row."""
    db_path = await resolve_runtime_db(run_id)
    try:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            return await fetch_outcome_tables(db, params.filters, offset=offset, limit=limit)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/db/{run_id}/rag-diagnostics")
async def get_db_rag_diagnostics(run_id: str, run_root: str = "runs") -> dict[str, Any]:
    """Return per-section RAG retrieval diagnostics for a run."""
    db_path = await resolve_runtime_db(run_id, run_root)
    try:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT section, query_type, rerank_enabled, candidate_k, final_k,
                       retrieved_count, status, selected_chunks_json, error_message,
                       latency_ms, created_at
                FROM rag_retrieval_diagnostics
                ORDER BY created_at ASC
                """
            ) as cur:
                rows = await cur.fetchall()
        records: list[dict[str, Any]] = []
        for row in rows:
            chunks: list[dict[str, Any]] = []
            try:
                chunks = _json.loads(row["selected_chunks_json"] or "[]")
            except Exception:
                chunks = []
            records.append(
                {
                    "section": row["section"],
                    "query_type": row["query_type"],
                    "rerank_enabled": bool(row["rerank_enabled"]),
                    "candidate_k": row["candidate_k"],
                    "final_k": row["final_k"],
                    "retrieved_count": row["retrieved_count"],
                    "status": row["status"],
                    "selected_chunks": chunks,
                    "error_message": row["error_message"],
                    "latency_ms": row["latency_ms"],
                    "created_at": row["created_at"],
                }
            )
        return {"total": len(records), "records": records}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
