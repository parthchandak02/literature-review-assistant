"""Database explorer endpoints: papers facets, suggest, all-papers, tables, RAG diagnostics."""

from __future__ import annotations

import json as _json
from typing import Any

import aiosqlite
from fastapi import APIRouter, HTTPException

from src.web.state import _get_db_path, _resolve_db_path_from_run_or_workflow

router = APIRouter(tags=["database_explorer"])


@router.get("/api/db/{run_id}/papers-facets")
async def get_papers_facets(run_id: str) -> dict[str, Any]:
    """Return distinct values for all filter columns (used by autocomplete dropdowns)."""
    db_path = _get_db_path(run_id)
    try:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT DISTINCT year FROM papers WHERE year IS NOT NULL ORDER BY year DESC") as cur:
                years = [row[0] for row in await cur.fetchall()]
            async with db.execute(
                "SELECT DISTINCT source_database FROM papers WHERE source_database IS NOT NULL ORDER BY source_database"
            ) as cur:
                sources = [row[0] for row in await cur.fetchall()]
            async with db.execute(
                "SELECT DISTINCT country FROM papers WHERE country IS NOT NULL ORDER BY country"
            ) as cur:
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
                SELECT DISTINCT COALESCE(json_extract(er.data, '$.primary_study_status'), 'unknown') AS primary_status
                FROM extraction_records er
                WHERE COALESCE(json_extract(er.data, '$.primary_study_status'), 'unknown') IS NOT NULL
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
    db_path = _get_db_path(run_id)
    try:
        async with aiosqlite.connect(db_path) as db:
            like = f"%{q}%"
            if column == "title":
                async with db.execute(
                    "SELECT DISTINCT title FROM papers WHERE title LIKE ? AND title IS NOT NULL ORDER BY title LIMIT ?",
                    (like, limit),
                ) as cur:
                    suggestions = [row[0] for row in await cur.fetchall()]
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
    search: str = "",
    title: str = "",
    author: str = "",
    ta_decision: str = "",
    ft_decision: str = "",
    primary_status: str = "",
    year: str = "",
    source: str = "",
    country: str = "",
    offset: int = 0,
    limit: int = 50,
) -> dict[str, Any]:
    """Unified per-paper table joining papers with final screening decisions."""
    db_path = _get_db_path(run_id)
    try:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row

            conditions: list[str] = []
            params: list[Any] = []

            if search:
                like = f"%{search}%"
                conditions.append("(p.title LIKE ? OR p.abstract LIKE ? OR p.authors LIKE ?)")
                params.extend([like, like, like])
            if title:
                conditions.append("COALESCE(p.title, '') LIKE ?")
                params.append(f"%{title}%")
            if author:
                conditions.append("COALESCE(p.authors, '') LIKE ?")
                params.append(f"%{author}%")
            if ta_decision:
                conditions.append("COALESCE(ta.final_decision, '') LIKE ?")
                params.append(f"%{ta_decision}%")
            if ft_decision:
                conditions.append("COALESCE(ft.final_decision, '') LIKE ?")
                params.append(f"%{ft_decision}%")
            if primary_status:
                conditions.append("COALESCE(json_extract(er.data, '$.primary_study_status'), 'unknown') LIKE ?")
                params.append(f"%{primary_status}%")
            if year:
                conditions.append("CAST(p.year AS TEXT) LIKE ?")
                params.append(f"%{year}%")
            if source:
                conditions.append("COALESCE(p.source_database, '') LIKE ?")
                params.append(f"%{source}%")
            if country:
                conditions.append("COALESCE(p.country, '') LIKE ?")
                params.append(f"%{country}%")

            where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

            base_query = f"""
                FROM papers p
                LEFT JOIN dual_screening_results ta
                  ON p.paper_id = ta.paper_id AND ta.stage = 'title_abstract'
                LEFT JOIN dual_screening_results ft
                  ON p.paper_id = ft.paper_id AND ft.stage = 'fulltext'
                LEFT JOIN extraction_records er
                  ON p.paper_id = er.paper_id
                LEFT JOIN rob_assessments ra
                  ON p.paper_id = ra.paper_id
                {where}
            """

            async with db.execute(
                f"""SELECT p.paper_id, p.title, p.authors, p.year,
                           p.source_database, p.doi, p.url, p.country,
                           ta.final_decision AS ta_decision,
                           ft.final_decision AS ft_decision,
                           COALESCE(json_extract(er.data, '$.primary_study_status'), 'unknown')
                               AS primary_study_status,
                           er.data AS extraction_data,
                           ra.assessment_data AS rob_assessment_data
                    {base_query}
                    ORDER BY p.year DESC LIMIT ? OFFSET ?""",
                (*params, limit, offset),
            ) as cur:
                rows = await cur.fetchall()

            async with db.execute(f"SELECT COUNT(*) {base_query}", params) as cur:
                total = (await cur.fetchone())[0]  # type: ignore[index]

            papers = []
            for row in rows:
                raw = row["authors"] or ""
                try:
                    authors_list = _json.loads(raw) if raw.startswith("[") else [raw]
                    authors_fmt = ", ".join(
                        (a.get("name") or a.get("raw_name") or str(a)) if isinstance(a, dict) else str(a)
                        for a in authors_list
                    )
                except Exception:
                    authors_fmt = raw
                extraction_confidence: float | None = None
                try:
                    if row["extraction_data"]:
                        ed = _json.loads(row["extraction_data"])
                        extraction_confidence = ed.get("extraction_confidence")
                except Exception:
                    pass

                assessment_source: str | None = None
                try:
                    if row["rob_assessment_data"]:
                        rad = _json.loads(row["rob_assessment_data"])
                        assessment_source = rad.get("assessment_source")
                except Exception:
                    pass

                papers.append(
                    {
                        "paper_id": row["paper_id"],
                        "title": row["title"],
                        "authors": authors_fmt,
                        "year": row["year"],
                        "source_database": row["source_database"],
                        "doi": row["doi"],
                        "url": row["url"],
                        "country": row["country"],
                        "ta_decision": row["ta_decision"],
                        "ft_decision": row["ft_decision"],
                        "primary_study_status": row["primary_study_status"],
                        "extraction_confidence": extraction_confidence,
                        "assessment_source": assessment_source,
                    }
                )

            return {"total": total, "offset": offset, "limit": limit, "papers": papers}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/db/{run_id}/tables")
async def get_db_tables(run_id: str) -> dict[str, Any]:
    """Vision-extracted quantitative outcome table rows grouped by paper."""
    db_path = _get_db_path(run_id)
    try:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT er.paper_id, er.data, er.extraction_source, p.title, p.doi
                FROM extraction_records er
                LEFT JOIN papers p USING (paper_id)
                WHERE er.data IS NOT NULL
                ORDER BY er.paper_id
                """
            ) as cur:
                rows = await cur.fetchall()

        papers_out: list[dict[str, Any]] = []
        total_rows = 0
        for row in rows:
            try:
                record_data: dict[str, Any] = _json.loads(row["data"] or "{}")
            except Exception:
                record_data = {}
            outcomes: list[dict[str, Any]] = record_data.get("outcomes") or []
            extraction_source: str = str(row["extraction_source"] or record_data.get("extraction_source") or "text")
            numeric_outcomes = [o for o in outcomes if o.get("effect_size") or o.get("p_value") or o.get("ci_lower")]
            if not numeric_outcomes:
                continue
            total_rows += len(numeric_outcomes)
            papers_out.append(
                {
                    "paper_id": row["paper_id"],
                    "title": row["title"] or "",
                    "doi": row["doi"],
                    "extraction_source": extraction_source,
                    "outcomes": numeric_outcomes,
                }
            )

        return {"total_rows": total_rows, "papers": papers_out}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/db/{run_id}/rag-diagnostics")
async def get_db_rag_diagnostics(run_id: str, run_root: str = "runs") -> dict[str, Any]:
    """Return per-section RAG retrieval diagnostics for a run."""
    db_path = await _resolve_db_path_from_run_or_workflow(run_id, run_root)
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
