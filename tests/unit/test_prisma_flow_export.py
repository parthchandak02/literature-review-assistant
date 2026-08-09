"""Unit tests for PRISMA flow CSV/ZIP export."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from src.db.database import get_db
from src.export.prisma_flow_export import build_prisma_flow_zip_bytes, export_prisma_flow_to_directory


@pytest.mark.asyncio
async def test_build_prisma_flow_zip_contains_expected_csvs(tmp_path: Path) -> None:
    workflow_id = "wf-prisma-export"
    db_path = tmp_path / "runtime.db"

    async with get_db(str(db_path)) as db:
        await db.execute(
            "INSERT INTO workflows (workflow_id, topic, config_hash, status, dedup_count) VALUES (?, ?, ?, ?, ?)",
            (workflow_id, "Topic", "hash", "completed", 2),
        )
        await db.execute(
            """
            INSERT INTO papers (
                paper_id, title, authors, year, source_database, source_category, doi, url
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("p1", "Included study", '["Alice"]', 2024, "pubmed", "database", "10.1/a", "https://example.com/p1"),
        )
        await db.execute(
            """
            INSERT INTO papers (
                paper_id, title, authors, year, source_database, source_category, doi, url
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("p2", "Excluded study", '["Bob"]', 2023, "openalex", "database", "10.1/b", "https://example.com/p2"),
        )
        await db.execute(
            """
            INSERT INTO search_results (
                database_name, source_category, search_date, search_query, records_retrieved, workflow_id
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("pubmed", "database", "2026-01-01", "health promotion", 10, workflow_id),
        )
        await db.execute(
            """
            INSERT INTO dual_screening_results (
                workflow_id, paper_id, stage, agreement, final_decision, adjudication_needed
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (workflow_id, "p1", "title_abstract", 1, "include", 0),
        )
        await db.execute(
            """
            INSERT INTO dual_screening_results (
                workflow_id, paper_id, stage, agreement, final_decision, adjudication_needed
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (workflow_id, "p1", "fulltext", 1, "include", 0),
        )
        await db.execute(
            """
            INSERT INTO dual_screening_results (
                workflow_id, paper_id, stage, agreement, final_decision, adjudication_needed
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (workflow_id, "p2", "title_abstract", 1, "exclude", 0),
        )
        await db.execute(
            """
            INSERT INTO study_cohort_membership (
                workflow_id, paper_id, screening_status, fulltext_status, synthesis_eligibility
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (workflow_id, "p1", "included", "assessed", "included_primary"),
        )
        await db.execute(
            """
            INSERT INTO study_cohort_membership (
                workflow_id, paper_id, screening_status, fulltext_status, synthesis_eligibility,
                exclusion_reason_code
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (workflow_id, "p2", "excluded", "unknown", "excluded_screening", "wrong_population"),
        )
        await db.commit()

    zip_bytes = await build_prisma_flow_zip_bytes(str(db_path), workflow_id)
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        names = set(archive.namelist())
        assert "prisma_flow_summary.csv" in names
        assert "prisma_records.csv" in names
        assert "search_identification.csv" in names
        assert "README.txt" in names

        records_csv = archive.read("prisma_records.csv").decode("utf-8")
        assert "Included study" in records_csv
        assert "Excluded study" in records_csv
        assert "https://example.com/p1" in records_csv
        assert "wrong_population" in records_csv

        summary_csv = archive.read("prisma_flow_summary.csv").decode("utf-8")
        assert "duplicates_removed" in summary_csv
        assert "2" in summary_csv

        search_csv = archive.read("search_identification.csv").decode("utf-8")
        assert "pubmed" in search_csv


@pytest.mark.asyncio
async def test_export_prisma_flow_to_directory_writes_supplementary_files(tmp_path: Path) -> None:
    workflow_id = "wf-prisma-dir"
    db_path = tmp_path / "runtime.db"
    out_dir = tmp_path / "supplementary"

    async with get_db(str(db_path)) as db:
        await db.execute(
            "INSERT INTO workflows (workflow_id, topic, config_hash, status, dedup_count) VALUES (?, ?, ?, ?, ?)",
            (workflow_id, "Topic", "hash", "completed", 0),
        )
        await db.commit()

    await export_prisma_flow_to_directory(out_dir, str(db_path), workflow_id)
    assert (out_dir / "prisma_flow_summary.csv").exists()
    assert (out_dir / "prisma_records.csv").exists()
    assert (out_dir / "search_identification.csv").exists()
    assert (out_dir / "README_prisma_flow.txt").exists()
