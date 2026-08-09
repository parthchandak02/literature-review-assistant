"""PRISMA 2020 flow data export for research submission supplements."""

from __future__ import annotations

import csv
import io
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.prisma.diagram import _EXCLUSION_REASON_LABELS, build_prisma_counts

_EXCLUSION_REASON_LABELS_EXPORT = dict(_EXCLUSION_REASON_LABELS)

_SUMMARY_COLUMNS = [
    "workflow_id",
    "databases_identified",
    "other_sources_identified",
    "registers_identified",
    "duplicates_removed",
    "automation_excluded",
    "records_screened",
    "records_excluded_title_abstract",
    "reports_sought",
    "reports_not_retrieved",
    "reports_assessed",
    "reports_excluded_fulltext",
    "studies_included_qualitative",
    "studies_included_quantitative",
    "studies_included_total",
    "arithmetic_valid",
    "note_duplicates_not_in_records_csv",
]

_RECORD_COLUMNS = [
    "workflow_id",
    "paper_id",
    "title",
    "authors",
    "year",
    "journal",
    "source_database",
    "source_category",
    "doi",
    "url",
    "openalex_id",
    "prisma_stage",
    "terminal_decision",
    "exclusion_reason_code",
    "exclusion_reason_label",
    "exclusion_rationale",
    "screening_status",
    "fulltext_status",
    "synthesis_eligibility",
    "ta_final_decision",
    "ft_final_decision",
    "included_in_synthesis",
]

_SEARCH_COLUMNS = [
    "workflow_id",
    "database_name",
    "source_category",
    "search_date",
    "search_query",
    "records_retrieved",
]

_README = """PRISMA 2020 Flow Data Export
=============================

This ZIP contains the data backing the PRISMA flow diagram for this review.

Files:
- prisma_flow_summary.csv: aggregate counts that should match the PRISMA diagram boxes
- prisma_records.csv: one row per persisted paper with terminal disposition and exclusion reasons
- search_identification.csv: per-database identification counts from the search phase
- README.txt: this file

Important limitations:
- Duplicate records removed during deduplication are counted in prisma_flow_summary.csv but
  are not listed as individual rows in prisma_records.csv (they were never persisted).
- The diagram may fold other-source identification into the databases total for arithmetic
  consistency; see search_identification.csv for per-source breakdown.
- Abstract text is omitted from exports by default.
"""


def _reason_label(code: str | None) -> str:
    if not code:
        return ""
    normalized = str(code).strip().lower().replace(" ", "_")
    return _EXCLUSION_REASON_LABELS_EXPORT.get(normalized, normalized.replace("_", " ").title())


def _format_authors(raw: str | None) -> str:
    if not raw:
        return ""
    try:
        if raw.startswith("["):
            authors_list = json.loads(raw)
            return ", ".join(
                (a.get("name") or a.get("raw_name") or str(a)) if isinstance(a, dict) else str(a)
                for a in authors_list
            )
    except (json.JSONDecodeError, TypeError, AttributeError):
        pass
    return raw


def _classify_prisma_stage(
    *,
    ta_decision: str | None,
    ft_decision: str | None,
    synthesis_eligibility: str | None,
    fulltext_status: str | None,
    exclusion_reason_code: str | None,
) -> tuple[str, str]:
    """Return (prisma_stage, terminal_decision) for one paper."""
    if synthesis_eligibility == "included_primary":
        return "included", "include"
    if ft_decision == "batch_screened_low":
        return "removed_automation", "automation_exclude"
    if fulltext_status == "not_retrieved" or (exclusion_reason_code or "").lower() == "no_full_text":
        return "not_retrieved", "not_retrieved"
    if ft_decision == "exclude":
        return "excluded_ft", "exclude"
    if ta_decision == "exclude":
        return "excluded_ta", "exclude"
    if ft_decision in ("include", "uncertain") and fulltext_status == "assessed":
        return "assessed_ft", ft_decision
    if ta_decision in ("include", "uncertain"):
        return "sought_ft", ta_decision
    if synthesis_eligibility and synthesis_eligibility.startswith("excluded"):
        return "excluded_ft", "exclude"
    return "screened", ta_decision or "unknown"


async def _fetch_record_rows(db_path: str, workflow_id: str) -> list[dict[str, Any]]:
    async with get_db(db_path) as db:
        cursor = await db.execute(
            """
            SELECT
                p.paper_id,
                p.title,
                p.authors,
                p.year,
                p.journal,
                p.source_database,
                p.source_category,
                p.doi,
                p.url,
                p.openalex_id,
                ta.final_decision AS ta_decision,
                ft.final_decision AS ft_decision,
                scm.screening_status,
                scm.fulltext_status,
                scm.synthesis_eligibility,
                scm.exclusion_reason_code,
                ft_reason.exclusion_reason AS ft_exclusion_reason,
                ft_reason.reason AS exclusion_rationale
            FROM papers p
            LEFT JOIN dual_screening_results ta
              ON p.paper_id = ta.paper_id
             AND ta.workflow_id = ?
             AND ta.stage = 'title_abstract'
            LEFT JOIN dual_screening_results ft
              ON p.paper_id = ft.paper_id
             AND ft.workflow_id = ?
             AND ft.stage = 'fulltext'
            LEFT JOIN study_cohort_membership scm
              ON p.paper_id = scm.paper_id
             AND scm.workflow_id = ?
            LEFT JOIN (
                SELECT
                    paper_id,
                    exclusion_reason,
                    reason,
                    ROW_NUMBER() OVER (
                        PARTITION BY paper_id
                        ORDER BY
                            CASE reviewer_type
                                WHEN 'human_override' THEN 0
                                WHEN 'adjudicator' THEN 1
                                WHEN 'reviewer_a' THEN 2
                                WHEN 'reviewer_b' THEN 3
                                ELSE 4
                            END,
                            datetime(created_at) DESC,
                            id DESC
                    ) AS rn
                FROM screening_decisions
                WHERE workflow_id = ? AND stage = 'fulltext' AND decision = 'exclude'
            ) ft_reason
              ON p.paper_id = ft_reason.paper_id AND ft_reason.rn = 1
            ORDER BY p.year DESC NULLS LAST, p.paper_id
            """,
            (workflow_id, workflow_id, workflow_id, workflow_id),
        )
        rows = await cursor.fetchall()

    records: list[dict[str, Any]] = []
    for row in rows:
        (
            paper_id,
            title,
            authors_raw,
            year,
            journal,
            source_database,
            source_category,
            doi,
            url,
            openalex_id,
            ta_decision,
            ft_decision,
            screening_status,
            fulltext_status,
            synthesis_eligibility,
            exclusion_reason_code,
            ft_exclusion_reason,
            exclusion_rationale,
        ) = row
        exclusion_code = str(exclusion_reason_code or "").strip() or None
        if not exclusion_code and ft_exclusion_reason:
            exclusion_code = str(ft_exclusion_reason).strip()

        prisma_stage, terminal_decision = _classify_prisma_stage(
            ta_decision=str(ta_decision) if ta_decision else None,
            ft_decision=str(ft_decision) if ft_decision else None,
            synthesis_eligibility=str(synthesis_eligibility) if synthesis_eligibility else None,
            fulltext_status=str(fulltext_status) if fulltext_status else None,
            exclusion_reason_code=exclusion_code,
        )
        records.append(
            {
                "workflow_id": workflow_id,
                "paper_id": str(paper_id),
                "title": title or "",
                "authors": _format_authors(str(authors_raw) if authors_raw else None),
                "year": year if year is not None else "",
                "journal": journal or "",
                "source_database": source_database or "",
                "source_category": source_category or "",
                "doi": doi or "",
                "url": url or "",
                "openalex_id": openalex_id or "",
                "prisma_stage": prisma_stage,
                "terminal_decision": terminal_decision,
                "exclusion_reason_code": exclusion_code or "",
                "exclusion_reason_label": _reason_label(exclusion_code),
                "exclusion_rationale": (str(exclusion_rationale) if exclusion_rationale else "")[:500],
                "screening_status": screening_status or "",
                "fulltext_status": fulltext_status or "",
                "synthesis_eligibility": synthesis_eligibility or "",
                "ta_final_decision": ta_decision or "",
                "ft_final_decision": ft_decision or "",
                "included_in_synthesis": "true" if synthesis_eligibility == "included_primary" else "false",
            }
        )
    return records


async def _fetch_search_rows(db_path: str, workflow_id: str) -> list[dict[str, Any]]:
    async with get_db(db_path) as db:
        cursor = await db.execute(
            """
            SELECT database_name, source_category, search_date, search_query, records_retrieved
            FROM search_results
            WHERE workflow_id = ?
            ORDER BY source_category, database_name
            """,
            (workflow_id,),
        )
        rows = await cursor.fetchall()
    return [
        {
            "workflow_id": workflow_id,
            "database_name": str(row[0]),
            "source_category": str(row[1]),
            "search_date": str(row[2]),
            "search_query": str(row[3]),
            "records_retrieved": int(row[4]),
        }
        for row in rows
    ]


def _write_csv(columns: list[str], rows: list[dict[str, Any]]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue()


@dataclass(frozen=True)
class PrismaFlowExportPayload:
    summary_csv: str
    records_csv: str
    search_csv: str
    readme: str


async def build_prisma_flow_payload(db_path: str, workflow_id: str) -> PrismaFlowExportPayload:
    """Build PRISMA flow CSV payloads from runtime database state."""
    async with get_db(db_path) as db:
        repo = WorkflowRepository(db)
        dedup_count = int(await repo.get_dedup_count(workflow_id) or 0)
        included_ids, _ = await repo.resolve_canonical_included_paper_ids(workflow_id)
        included_qualitative = 0
        included_quantitative = len(included_ids)
        counts = await build_prisma_counts(
            repo,
            workflow_id,
            dedup_count,
            included_qualitative=included_qualitative,
            included_quantitative=included_quantitative,
        )

    ft_excluded_total = sum(counts.reports_excluded_with_reasons.values())
    summary_row = {
        "workflow_id": workflow_id,
        "databases_identified": counts.total_identified_databases,
        "other_sources_identified": counts.total_identified_other,
        "registers_identified": 0,
        "duplicates_removed": counts.duplicates_removed,
        "automation_excluded": counts.automation_excluded,
        "records_screened": counts.records_screened,
        "records_excluded_title_abstract": counts.records_excluded_screening,
        "reports_sought": counts.reports_sought,
        "reports_not_retrieved": counts.reports_not_retrieved,
        "reports_assessed": counts.reports_assessed,
        "reports_excluded_fulltext": ft_excluded_total,
        "studies_included_qualitative": counts.studies_included_qualitative,
        "studies_included_quantitative": counts.studies_included_quantitative,
        "studies_included_total": counts.total_included,
        "arithmetic_valid": str(counts.arithmetic_valid).lower(),
        "note_duplicates_not_in_records_csv": (
            "Duplicate records removed before screening are counted here but not listed in prisma_records.csv"
        ),
    }

    record_rows = await _fetch_record_rows(db_path, workflow_id)
    search_rows = await _fetch_search_rows(db_path, workflow_id)
    return PrismaFlowExportPayload(
        summary_csv=_write_csv(_SUMMARY_COLUMNS, [summary_row]),
        records_csv=_write_csv(_RECORD_COLUMNS, record_rows),
        search_csv=_write_csv(_SEARCH_COLUMNS, search_rows),
        readme=_README,
    )


async def export_prisma_flow_to_directory(out_dir: Path, db_path: str, workflow_id: str) -> None:
    """Write PRISMA flow CSVs (and README) into a submission supplementary directory."""
    payload = await build_prisma_flow_payload(db_path, workflow_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "README_prisma_flow.txt").write_text(payload.readme, encoding="utf-8")
    (out_dir / "prisma_flow_summary.csv").write_text(payload.summary_csv, encoding="utf-8")
    (out_dir / "prisma_records.csv").write_text(payload.records_csv, encoding="utf-8")
    (out_dir / "search_identification.csv").write_text(payload.search_csv, encoding="utf-8")


async def build_prisma_flow_zip_bytes(db_path: str, workflow_id: str) -> bytes:
    """Build a ZIP archive with PRISMA flow summary, per-paper records, and search identification."""
    payload = await build_prisma_flow_payload(db_path, workflow_id)

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("README.txt", payload.readme)
        archive.writestr("prisma_flow_summary.csv", payload.summary_csv)
        archive.writestr("prisma_records.csv", payload.records_csv)
        archive.writestr("search_identification.csv", payload.search_csv)
    return zip_buffer.getvalue()
