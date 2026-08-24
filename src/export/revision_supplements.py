"""Revision supplementary CSV exports for journal submission packages."""

from __future__ import annotations

import csv
from enum import Enum
from pathlib import Path

from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.quality.grade import build_sof_table


def _enum_value(value: object) -> str:
    if isinstance(value, Enum):
        return str(value.value)
    return str(value)


def _write_csv(path: Path, headers: list[str], rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for row in rows:
            writer.writerow(row)


async def _load_workflow_topic(db_path: str, workflow_id: str) -> str:
    async with get_db(db_path) as db:
        cursor = await db.execute(
            "SELECT topic FROM workflows WHERE workflow_id = ? LIMIT 1",
            (workflow_id,),
        )
        row = await cursor.fetchone()
    if row and row[0]:
        return str(row[0])
    return "Systematic Review"


async def export_extracted_data_by_outcome(
    db_path: str,
    workflow_id: str,
    out_path: Path,
) -> None:
    """Export one row per extracted outcome measure."""
    headers = [
        "paper_id",
        "study_design",
        "primary_study_status",
        "outcome_index",
        "outcome_name",
        "description",
        "effect_size",
        "se",
        "n",
        "ci_lower",
        "ci_upper",
        "p_value",
        "title",
        "variance",
    ]
    async with get_db(db_path) as db:
        repo = WorkflowRepository(db)
        records = await repo.load_extraction_records(workflow_id)

    rows: list[list[str]] = []
    for record in records:
        study_design = _enum_value(record.study_design)
        primary_status = _enum_value(record.primary_study_status)
        for idx, outcome in enumerate(record.outcomes):
            rows.append(
                [
                    record.paper_id,
                    study_design,
                    primary_status,
                    str(idx),
                    outcome.name,
                    outcome.description,
                    outcome.effect_size,
                    outcome.se,
                    outcome.n,
                    outcome.ci_lower,
                    outcome.ci_upper,
                    outcome.p_value,
                    outcome.title,
                    outcome.variance,
                ]
            )
    _write_csv(out_path, headers, rows)


async def export_rob2_assessments(db_path: str, workflow_id: str, out_path: Path) -> None:
    """Export RoB 2 domain judgments, one row per assessed study."""
    headers = [
        "paper_id",
        "domain_1_randomization",
        "domain_2_deviations",
        "domain_3_missing_data",
        "domain_4_measurement",
        "domain_5_selection",
        "overall_judgment",
        "assessment_source",
        "fallback_used",
    ]
    async with get_db(db_path) as db:
        repo = WorkflowRepository(db)
        rob2_list, _robins_i_list = await repo.load_rob_assessments(workflow_id)

    rows = [
        [
            a.paper_id,
            _enum_value(a.domain_1_randomization),
            _enum_value(a.domain_2_deviations),
            _enum_value(a.domain_3_missing_data),
            _enum_value(a.domain_4_measurement),
            _enum_value(a.domain_5_selection),
            _enum_value(a.overall_judgment),
            a.assessment_source,
            "1" if a.fallback_used else "0",
        ]
        for a in sorted(rob2_list, key=lambda x: x.paper_id)
    ]
    _write_csv(out_path, headers, rows)


async def export_robins_i_assessments(db_path: str, workflow_id: str, out_path: Path) -> None:
    """Export ROBINS-I domain judgments, one row per assessed study."""
    headers = [
        "paper_id",
        "domain_1_confounding",
        "domain_2_selection",
        "domain_3_classification",
        "domain_4_deviations",
        "domain_5_missing_data",
        "domain_6_measurement",
        "domain_7_reported_result",
        "overall_judgment",
        "assessment_source",
        "fallback_used",
    ]
    async with get_db(db_path) as db:
        repo = WorkflowRepository(db)
        _rob2_list, robins_i_list = await repo.load_rob_assessments(workflow_id)

    rows = [
        [
            a.paper_id,
            _enum_value(a.domain_1_confounding),
            _enum_value(a.domain_2_selection),
            _enum_value(a.domain_3_classification),
            _enum_value(a.domain_4_deviations),
            _enum_value(a.domain_5_missing_data),
            _enum_value(a.domain_6_measurement),
            _enum_value(a.domain_7_reported_result),
            _enum_value(a.overall_judgment),
            a.assessment_source,
            "1" if a.fallback_used else "0",
        ]
        for a in sorted(robins_i_list, key=lambda x: x.paper_id)
    ]
    _write_csv(out_path, headers, rows)


async def export_grade_sof(db_path: str, workflow_id: str, out_path: Path) -> None:
    """Export GRADE Summary of Findings rows."""
    headers = [
        "topic",
        "outcome_name",
        "n_studies",
        "study_design",
        "risk_of_bias",
        "inconsistency",
        "indirectness",
        "imprecision",
        "other_considerations",
        "certainty",
        "effect_summary",
    ]
    async with get_db(db_path) as db:
        repo = WorkflowRepository(db)
        assessments = await repo.load_grade_assessments(workflow_id)

    topic = await _load_workflow_topic(db_path, workflow_id)
    table = build_sof_table(assessments, topic=topic)
    rows = [
        [
            table.topic,
            r.outcome_name,
            str(r.n_studies),
            r.study_design,
            r.risk_of_bias,
            r.inconsistency,
            r.indirectness,
            r.imprecision,
            r.other_considerations,
            _enum_value(r.certainty),
            r.effect_summary,
        ]
        for r in table.rows
    ]
    _write_csv(out_path, headers, rows)


async def export_unretrieved_fulltext_reports(
    db_path: str,
    workflow_id: str,
    out_path: Path,
) -> None:
    """Export bibliographic details for full-text reports not retrieved."""
    headers = [
        "paper_id",
        "title",
        "authors",
        "year",
        "doi",
        "url",
        "journal",
        "source_database",
        "abstract",
        "exclusion_reason",
        "reason",
    ]
    async with get_db(db_path) as db:
        cursor = await db.execute(
            """
            SELECT DISTINCT
                p.paper_id,
                p.title,
                p.authors,
                p.year,
                p.doi,
                p.url,
                p.journal,
                p.source_database,
                p.abstract,
                sd.exclusion_reason,
                sd.reason
            FROM screening_decisions sd
            JOIN papers p ON p.paper_id = sd.paper_id
            WHERE sd.workflow_id = ?
              AND sd.stage = 'fulltext'
              AND lower(COALESCE(sd.exclusion_reason, '')) = 'no_full_text'
            ORDER BY p.paper_id
            """,
            (workflow_id,),
        )
        rows_raw = await cursor.fetchall()

    rows = [
        [
            str(paper_id or ""),
            str(title or ""),
            str(authors or ""),
            "" if year is None else str(year),
            str(doi or ""),
            str(url or ""),
            str(journal or ""),
            str(source_database or ""),
            str(abstract or "").replace("\n", " "),
            str(exclusion_reason or ""),
            str(reason or ""),
        ]
        for paper_id, title, authors, year, doi, url, journal, source_database, abstract, exclusion_reason, reason in rows_raw
    ]
    _write_csv(out_path, headers, rows)


async def export_revision_supplements(db_path: str, workflow_id: str, supp_dir: Path) -> None:
    """Write all revision supplementary CSV exports into supp_dir."""
    supp_dir.mkdir(parents=True, exist_ok=True)
    await export_extracted_data_by_outcome(db_path, workflow_id, supp_dir / "extracted_data_by_outcome.csv")
    await export_rob2_assessments(db_path, workflow_id, supp_dir / "rob2_assessments.csv")
    await export_robins_i_assessments(db_path, workflow_id, supp_dir / "robins_i_assessments.csv")
    await export_grade_sof(db_path, workflow_id, supp_dir / "grade_sof.csv")
    await export_unretrieved_fulltext_reports(
        db_path,
        workflow_id,
        supp_dir / "unretrieved_fulltext_reports.csv",
    )
