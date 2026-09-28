"""Parameterised SQL builders for the Data tab papers explorer (filters, sort, facets, export)."""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field
from typing import Any, Literal

import aiosqlite

from src.models.papers import decode_html_entities

NONE_SENTINEL = "__none__"

PRIMARY_STATUS_EXPR = "COALESCE(er.primary_study_status, json_extract(er.data, '$.primary_study_status'), 'unknown')"

FROM_CLAUSE = """
    FROM papers p
    LEFT JOIN dual_screening_results ta
      ON p.paper_id = ta.paper_id AND ta.stage = 'title_abstract'
    LEFT JOIN dual_screening_results ft
      ON p.paper_id = ft.paper_id AND ft.stage = 'fulltext'
    LEFT JOIN extraction_records er
      ON p.paper_id = er.paper_id
    LEFT JOIN rob_assessments ra
      ON p.paper_id = ra.paper_id
"""

SORT_COLUMNS: dict[str, str] = {
    "title": "p.title COLLATE NOCASE",
    "year": "p.year",
    "source": "p.source_database COLLATE NOCASE",
    "ta_decision": "ta.final_decision",
    "ft_decision": "ft.final_decision",
    "primary_status": PRIMARY_STATUS_EXPR,
    "confidence": "CAST(json_extract(er.data, '$.extraction_confidence') AS REAL)",
}

FacetField = Literal["ta_decision", "ft_decision", "primary_status", "year", "source", "country"]

FACET_COLUMNS: dict[str, str] = {
    "ta_decision": "ta.final_decision",
    "ft_decision": "ft.final_decision",
    "primary_status": PRIMARY_STATUS_EXPR,
    "year": "p.year",
    "source": "p.source_database",
    "country": "p.country",
}

_CATEGORICAL_COLUMNS: dict[str, str] = {
    "ta_decision": "ta.final_decision",
    "ft_decision": "ft.final_decision",
    "primary_status": PRIMARY_STATUS_EXPR,
    "source": "p.source_database",
    "country": "p.country",
}

SELECT_COLUMNS = f"""
    p.paper_id, p.title, p.authors, p.year, p.abstract,
    p.source_database, p.doi, p.url, p.country, p.journal,
    ta.final_decision AS ta_decision,
    ft.final_decision AS ft_decision,
    {PRIMARY_STATUS_EXPR} AS primary_study_status,
    er.data AS extraction_data,
    ra.assessment_data AS rob_assessment_data
"""


class InvalidQueryError(ValueError):
    """Raised for sort/dir/format values outside the whitelist."""


def _clean(values: list[str] | None) -> list[str]:
    return [v for v in (values or []) if v is not None and v != ""]


@dataclass
class PaperFilters:
    search: str = ""
    title: str = ""
    author: str = ""
    ta_decision: list[str] = field(default_factory=list)
    ft_decision: list[str] = field(default_factory=list)
    primary_status: list[str] = field(default_factory=list)
    source: list[str] = field(default_factory=list)
    country: list[str] = field(default_factory=list)
    year: str = ""
    year_min: int | None = None
    year_max: int | None = None
    match: Literal["contains", "exact"] = "contains"

    def __post_init__(self) -> None:
        if self.match not in ("contains", "exact"):
            raise InvalidQueryError("match must be 'contains' or 'exact'")
        for name in _CATEGORICAL_COLUMNS:
            setattr(self, name, _clean(getattr(self, name)))

    def where(self, exclude: str | None = None) -> tuple[str, list[Any]]:
        """Return a WHERE clause and bound params, optionally skipping one facet's own filter."""
        conditions: list[str] = []
        params: list[Any] = []
        if self.search:
            like = f"%{self.search}%"
            conditions.append("(p.title LIKE ? OR p.abstract LIKE ? OR p.authors LIKE ?)")
            params.extend([like, like, like])
        if self.title:
            conditions.append("COALESCE(p.title, '') LIKE ?")
            params.append(f"%{self.title}%")
        if self.author:
            conditions.append("COALESCE(p.authors, '') LIKE ?")
            params.append(f"%{self.author}%")
        for name, column in _CATEGORICAL_COLUMNS.items():
            if name == exclude:
                continue
            values: list[str] = getattr(self, name)
            if not values:
                continue
            clause, clause_params = self._categorical(column, values)
            conditions.append(clause)
            params.extend(clause_params)
        if exclude != "year":
            if self.year:
                conditions.append("CAST(p.year AS TEXT) LIKE ?")
                params.append(f"%{self.year}%")
            if self.year_min is not None:
                conditions.append("p.year >= ?")
                params.append(self.year_min)
            if self.year_max is not None:
                conditions.append("p.year <= ?")
                params.append(self.year_max)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        return where, params

    def _categorical(self, column: str, values: list[str]) -> tuple[str, list[Any]]:
        if self.match == "contains":
            parts = [f"COALESCE({column}, '') LIKE ?" for _ in values]
            return f"({' OR '.join(parts)})", [f"%{v}%" for v in values]
        include_null = NONE_SENTINEL in values
        concrete = [v for v in values if v != NONE_SENTINEL]
        parts = []
        if concrete:
            parts.append(f"{column} IN ({', '.join('?' for _ in concrete)})")
        if include_null:
            parts.append(f"{column} IS NULL")
        return f"({' OR '.join(parts)})", list(concrete)


def order_by(sort: str, direction: str) -> str:
    """Build an ORDER BY clause from whitelisted identifiers only."""
    if direction not in ("asc", "desc"):
        raise InvalidQueryError("dir must be 'asc' or 'desc'")
    if not sort:
        return "ORDER BY p.year DESC, p.paper_id ASC"
    expr = SORT_COLUMNS.get(sort)
    if expr is None:
        raise InvalidQueryError(f"sort must be one of: {', '.join(sorted(SORT_COLUMNS))}")
    return f"ORDER BY ({expr}) IS NULL ASC, {expr} {direction.upper()}, p.paper_id ASC"


def format_authors(raw: str | None) -> list[str]:
    raw = raw or ""
    try:
        authors_list = json.loads(raw) if raw.startswith("[") else [raw]
    except Exception:
        return [decode_html_entities(raw)] if raw else []
    names: list[str] = []
    for a in authors_list:
        name = (a.get("name") or a.get("raw_name") or str(a)) if isinstance(a, dict) else str(a)
        if name:
            names.append(decode_html_entities(name))
    return names


def _json_field(raw: str | None, key: str) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw).get(key)
    except Exception:
        return None


def row_to_paper(row: aiosqlite.Row) -> dict[str, Any]:
    return {
        "paper_id": row["paper_id"],
        "title": decode_html_entities(row["title"] or ""),
        "authors": ", ".join(format_authors(row["authors"])),
        "year": row["year"],
        "source_database": row["source_database"],
        "doi": row["doi"],
        "url": row["url"],
        "country": row["country"],
        "ta_decision": row["ta_decision"],
        "ft_decision": row["ft_decision"],
        "primary_study_status": row["primary_study_status"],
        "extraction_confidence": _json_field(row["extraction_data"], "extraction_confidence"),
        "assessment_source": _json_field(row["rob_assessment_data"], "assessment_source"),
    }


async def fetch_papers_page(
    db: aiosqlite.Connection,
    filters: PaperFilters,
    *,
    sort: str,
    direction: str,
    offset: int,
    limit: int,
) -> tuple[int, list[dict[str, Any]]]:
    order = order_by(sort, direction)
    where, params = filters.where()
    async with db.execute(
        f"SELECT {SELECT_COLUMNS} {FROM_CLAUSE} {where} {order} LIMIT ? OFFSET ?",
        (*params, limit, offset),
    ) as cur:
        rows = await cur.fetchall()
    async with db.execute(f"SELECT COUNT(*) {FROM_CLAUSE} {where}", params) as cur:
        total = (await cur.fetchone())[0]  # type: ignore[index]
    return total, [row_to_paper(r) for r in rows]


async def fetch_facet_counts(db: aiosqlite.Connection, filters: PaperFilters) -> dict[str, list[dict[str, Any]]]:
    """Counts per value for each facet, applying every active filter except the facet's own."""
    counts: dict[str, list[dict[str, Any]]] = {}
    for name, column in FACET_COLUMNS.items():
        where, params = filters.where(exclude=name)
        order = "value DESC" if name == "year" else "count DESC, value ASC"
        async with db.execute(
            f"SELECT {column} AS value, COUNT(DISTINCT p.paper_id) AS count {FROM_CLAUSE} {where} "
            f"GROUP BY value ORDER BY {order}",
            params,
        ) as cur:
            counts[name] = [{"value": r[0], "count": r[1]} for r in await cur.fetchall()]
    return counts


EXPORT_COLUMNS = [
    "paper_id",
    "title",
    "authors",
    "year",
    "journal",
    "source_database",
    "doi",
    "url",
    "country",
    "ta_decision",
    "ft_decision",
    "primary_study_status",
    "extraction_confidence",
    "abstract",
]


async def fetch_export_rows(
    db: aiosqlite.Connection, filters: PaperFilters, *, sort: str, direction: str
) -> list[dict[str, Any]]:
    order = order_by(sort, direction)
    where, params = filters.where()
    async with db.execute(f"SELECT {SELECT_COLUMNS} {FROM_CLAUSE} {where} {order}", params) as cur:
        rows = await cur.fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        paper = row_to_paper(r)
        paper["author_list"] = format_authors(r["authors"])
        paper["abstract"] = decode_html_entities(r["abstract"] or "")
        paper["journal"] = r["journal"]
        out.append(paper)
    return out


def _csv_safe(value: Any) -> Any:
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return f"'{value}"
    return "" if value is None else value


def to_csv(rows: list[dict[str, Any]]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(EXPORT_COLUMNS)
    for row in rows:
        writer.writerow([_csv_safe(row.get(col)) for col in EXPORT_COLUMNS])
    return buf.getvalue()


def _ris_line(tag: str, value: Any) -> str:
    text = " ".join(str(value).split())
    return f"{tag}  - {text}"


def to_ris(rows: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for row in rows:
        lines.append(_ris_line("TY", "JOUR"))
        if row.get("title"):
            lines.append(_ris_line("TI", row["title"]))
        for author in row.get("author_list") or []:
            lines.append(_ris_line("AU", author))
        if row.get("year") is not None:
            lines.append(_ris_line("PY", row["year"]))
        if row.get("journal"):
            lines.append(_ris_line("JO", row["journal"]))
        if row.get("doi"):
            lines.append(_ris_line("DO", row["doi"]))
        if row.get("url"):
            lines.append(_ris_line("UR", row["url"]))
        if row.get("abstract"):
            lines.append(_ris_line("AB", row["abstract"]))
        if row.get("source_database"):
            lines.append(_ris_line("DB", row["source_database"]))
        notes = [
            f"{label}: {row[key]}"
            for key, label in (
                ("ta_decision", "Title/abstract"),
                ("ft_decision", "Full text"),
                ("primary_study_status", "Primary status"),
            )
            if row.get(key)
        ]
        if notes:
            lines.append(_ris_line("N1", "; ".join(notes)))
        lines.append(_ris_line("ID", row["paper_id"]))
        lines.append("ER  - ")
        lines.append("")
    return "\r\n".join(lines)


_EXTRACTION_SUMMARY_KEYS = (
    "study_design",
    "primary_study_status",
    "extraction_source",
    "extraction_confidence",
    "participant_count",
    "setting",
    "country",
    "study_duration",
    "intervention_description",
    "comparator_description",
    "results_summary",
    "funding_source",
)


async def fetch_paper_detail(db: aiosqlite.Connection, paper_id: str) -> dict[str, Any] | None:
    async with db.execute(
        "SELECT paper_id, title, authors, year, source_database, doi, url, country, journal, abstract, keywords "
        "FROM papers WHERE paper_id = ?",
        (paper_id,),
    ) as cur:
        paper = await cur.fetchone()
    if paper is None:
        return None

    keywords: list[str] = []
    try:
        parsed = json.loads(paper["keywords"]) if paper["keywords"] else []
        keywords = [str(k) for k in parsed] if isinstance(parsed, list) else []
    except Exception:
        keywords = [paper["keywords"]] if paper["keywords"] else []

    async with db.execute(
        "SELECT stage, final_decision, agreement, adjudication_needed FROM dual_screening_results WHERE paper_id = ?",
        (paper_id,),
    ) as cur:
        finals = {r["stage"]: r for r in await cur.fetchall()}
    async with db.execute(
        "SELECT stage, reviewer_type, decision, reason, exclusion_reason, confidence, created_at "
        "FROM screening_decisions WHERE paper_id = ? ORDER BY created_at ASC, id ASC",
        (paper_id,),
    ) as cur:
        decisions = await cur.fetchall()

    stage_order = ["title_abstract", "fulltext"]
    stages = list(dict.fromkeys([*stage_order, *finals.keys(), *(d["stage"] for d in decisions)]))
    screening: list[dict[str, Any]] = []
    for stage in stages:
        final = finals.get(stage)
        stage_decisions = [
            {
                "reviewer_type": d["reviewer_type"],
                "decision": d["decision"],
                "reason": d["reason"],
                "exclusion_reason": d["exclusion_reason"],
                "confidence": d["confidence"],
                "created_at": d["created_at"],
            }
            for d in decisions
            if d["stage"] == stage
        ]
        if final is None and not stage_decisions:
            continue
        screening.append(
            {
                "stage": stage,
                "final_decision": final["final_decision"] if final else None,
                "agreement": bool(final["agreement"]) if final else None,
                "adjudication_needed": bool(final["adjudication_needed"]) if final else None,
                "decisions": stage_decisions,
            }
        )

    extraction: dict[str, Any] | None = None
    async with db.execute(
        "SELECT study_design, primary_study_status, extraction_source, data FROM extraction_records "
        "WHERE paper_id = ? LIMIT 1",
        (paper_id,),
    ) as cur:
        er = await cur.fetchone()
    if er is not None:
        try:
            data = json.loads(er["data"] or "{}")
        except Exception:
            data = {}
        extraction = {key: data.get(key) for key in _EXTRACTION_SUMMARY_KEYS}
        extraction["study_design"] = er["study_design"] or extraction["study_design"]
        extraction["primary_study_status"] = er["primary_study_status"] or extraction["primary_study_status"]
        extraction["extraction_source"] = er["extraction_source"] or extraction["extraction_source"]
        outcomes = data.get("outcomes") or []
        extraction["outcome_count"] = len(outcomes) if isinstance(outcomes, list) else 0

    quality: dict[str, Any] | None = None
    async with db.execute(
        "SELECT tool_used, overall_judgment, assessment_data FROM rob_assessments WHERE paper_id = ? LIMIT 1",
        (paper_id,),
    ) as cur:
        rob = await cur.fetchone()
    if rob is not None:
        quality = {
            "tool_used": rob["tool_used"],
            "overall_judgment": rob["overall_judgment"],
            "assessment_source": _json_field(rob["assessment_data"], "assessment_source"),
        }

    return {
        "paper_id": paper["paper_id"],
        "title": decode_html_entities(paper["title"] or ""),
        "authors": format_authors(paper["authors"]),
        "year": paper["year"],
        "source_database": paper["source_database"],
        "doi": paper["doi"],
        "url": paper["url"],
        "country": paper["country"],
        "journal": paper["journal"],
        "abstract": decode_html_entities(paper["abstract"] or "") or None,
        "keywords": keywords,
        "screening": screening,
        "extraction": extraction,
        "quality": quality,
    }
