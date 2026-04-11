from pathlib import Path

import aiosqlite
import pytest

from src.db.database import get_db
from src.db.repositories import CitationRepository, WorkflowRepository
from src.models import (
    CandidatePaper,
    CitationEntryRecord,
    DecisionLogEntry,
    FallbackEventRecord,
    GRADECertainty,
    GRADEOutcomeAssessment,
    ManuscriptAssembly,
    ReviewerType,
    ScreeningDecision,
    ScreeningDecisionType,
    SearchResult,
    SectionDraft,
    SourceCategory,
    ValidationCheckRecord,
    ValidationRunRecord,
    WritingManifestRecord,
)


@pytest.mark.asyncio
async def test_database_migrations_create_tables(tmp_path) -> None:
    db_path = tmp_path / "phase1.db"
    async with get_db(str(db_path)) as db:
        assert isinstance(db, aiosqlite.Connection)
        cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='gate_results'")
        row = await cursor.fetchone()
        assert row is not None
        schema_version_row = await (await db.execute("SELECT COALESCE(MAX(version), 0) FROM schema_version")).fetchone()
        assert schema_version_row is not None
        assert int(schema_version_row[0]) >= 8

        cols = await (await db.execute("PRAGMA table_info(cost_records)")).fetchall()
        col_names = {str(r[1]) for r in cols}
        assert "workflow_id" in col_names

        cols2 = await (await db.execute("PRAGMA table_info(extraction_records)")).fetchall()
        col_names2 = {str(r[1]) for r in cols2}
        assert "extraction_source" in col_names2

        cols3 = await (await db.execute("PRAGMA table_info(decision_log)")).fetchall()
        col_names3 = {str(r[1]) for r in cols3}
        assert "workflow_id" in col_names3

        cols4 = await (await db.execute("PRAGMA table_info(manuscript_sections)")).fetchall()
        assert "section_key" in {str(r[1]) for r in cols4}


@pytest.mark.asyncio
async def test_processed_paper_ids_query(tmp_path) -> None:
    db_path = tmp_path / "phase1_ids.db"
    async with get_db(str(db_path)) as db:
        repo = WorkflowRepository(db)
        await db.execute(
            """
            INSERT INTO papers (paper_id, title, authors, source_database)
            VALUES ('p1', 't', '["a"]', 'openalex')
            """
        )
        await db.commit()
        await repo.save_screening_decision(
            workflow_id="wf1",
            stage="title_abstract",
            decision=ScreeningDecision(
                paper_id="p1",
                decision=ScreeningDecisionType.INCLUDE,
                reviewer_type=ReviewerType.REVIEWER_A,
                confidence=0.91,
            ),
        )
        processed = await repo.get_processed_paper_ids("wf1", "title_abstract")
        assert processed == {"p1"}


@pytest.mark.asyncio
async def test_save_search_result_is_idempotent_for_same_query(tmp_path) -> None:
    db_path = tmp_path / "search_idempotent.db"
    async with get_db(str(db_path)) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-search", "topic", "hash")
        paper = CandidatePaper(
            paper_id="p1",
            title="Paper 1",
            authors=["A"],
            source_database="openalex",
            source_category=SourceCategory.DATABASE,
        )
        sr = SearchResult(
            workflow_id="wf-search",
            database_name="openalex",
            source_category=SourceCategory.DATABASE,
            search_date="2026-03-23",
            search_query="(ai) AND (review)",
            limits_applied=None,
            records_retrieved=1,
            papers=[paper],
        )
        await repo.save_search_result(sr)
        await repo.save_search_result(sr)
        row = await (
            await db.execute("SELECT COUNT(*) FROM search_results WHERE workflow_id = ?", ("wf-search",))
        ).fetchone()
        assert int(row[0]) == 1


@pytest.mark.asyncio
async def test_rollback_phase_data_clears_downstream_rows(tmp_path) -> None:
    db_path = tmp_path / "rollback_phase_data.db"
    async with get_db(str(db_path)) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-rb", "topic", "hash")
        await db.execute(
            """
            INSERT INTO papers (paper_id, title, authors, source_database, source_category)
            VALUES ('p1', 'Paper 1', '[]', 'openalex', 'database')
            """
        )
        await db.execute(
            """
            INSERT INTO search_results
            (database_name, source_category, search_date, search_query, records_retrieved, workflow_id)
            VALUES ('openalex', 'database', '2026-03-23', 'q', 1, 'wf-rb')
            """
        )
        await db.execute(
            """
            INSERT INTO screening_decisions
            (workflow_id, paper_id, stage, decision, reviewer_type, confidence)
            VALUES ('wf-rb', 'p1', 'title_abstract', 'include', 'reviewer_a', 0.9)
            """
        )
        await db.execute(
            """
            INSERT INTO dual_screening_results
            (workflow_id, paper_id, stage, agreement, final_decision, adjudication_needed)
            VALUES ('wf-rb', 'p1', 'title_abstract', 1, 'include', 0)
            """
        )
        await db.execute(
            """
            INSERT INTO study_cohort_membership
            (workflow_id, paper_id, screening_status, fulltext_status, synthesis_eligibility, source_phase)
            VALUES ('wf-rb', 'p1', 'included_title_abstract', 'pending', 'pending', 'phase_3_screening')
            """
        )
        await db.commit()

        await repo.rollback_phase_data("wf-rb", "phase_2_search")

        search_count = await (
            await db.execute("SELECT COUNT(*) FROM search_results WHERE workflow_id = 'wf-rb'")
        ).fetchone()
        screening_count = await (
            await db.execute("SELECT COUNT(*) FROM screening_decisions WHERE workflow_id = 'wf-rb'")
        ).fetchone()
        dual_count = await (
            await db.execute("SELECT COUNT(*) FROM dual_screening_results WHERE workflow_id = 'wf-rb'")
        ).fetchone()
        cohort_count = await (
            await db.execute("SELECT COUNT(*) FROM study_cohort_membership WHERE workflow_id = 'wf-rb'")
        ).fetchone()
        papers_count = await (await db.execute("SELECT COUNT(*) FROM papers")).fetchone()
        assert int(search_count[0]) == 0
        assert int(screening_count[0]) == 0
        assert int(dual_count[0]) == 0
        assert int(cohort_count[0]) == 0
        assert int(papers_count[0]) == 0


@pytest.mark.asyncio
async def test_get_citekeys_by_source_types(tmp_path) -> None:
    db_path = tmp_path / "citekeys_by_source.db"
    async with get_db(str(db_path)) as db:
        repo = CitationRepository(db)
        await repo.register_citation(
            CitationEntryRecord(
                citekey="Inc2024",
                doi=None,
                title="Included paper",
                authors=["A"],
                year=2024,
                journal=None,
                bibtex=None,
                resolved=True,
                source_type="included",
            )
        )
        await repo.register_citation(
            CitationEntryRecord(
                citekey="Bg2021SR",
                doi=None,
                title="Background SR",
                authors=["B"],
                year=2021,
                journal=None,
                bibtex=None,
                resolved=True,
                source_type="background_sr",
            )
        )
        await repo.register_citation(
            CitationEntryRecord(
                citekey="Page2021",
                doi=None,
                title="PRISMA",
                authors=["Page, M. J."],
                year=2021,
                journal=None,
                bibtex=None,
                resolved=True,
                source_type="methodology",
            )
        )
        keys = await repo.get_citekeys_by_source_types({"background_sr", "methodology"})
        assert keys == {"Bg2021SR", "Page2021"}


@pytest.mark.asyncio
async def test_register_citation_is_idempotent_for_existing_citekey(tmp_path) -> None:
    db_path = tmp_path / "citekey_idempotent.db"
    async with get_db(str(db_path)) as db:
        repo = CitationRepository(db)
        await repo.register_citation(
            CitationEntryRecord(
                citation_id="cit-1",
                citekey="Page2021",
                doi=None,
                title="Original title",
                authors=["Page, M. J."],
                year=2021,
                journal=None,
                bibtex=None,
                resolved=True,
                source_type="methodology",
            )
        )
        await repo.register_citation(
            CitationEntryRecord(
                citation_id="cit-2",
                citekey="Page2021",
                doi=None,
                title="Updated title",
                authors=["Page, M. J."],
                year=2021,
                journal="BMJ",
                bibtex=None,
                resolved=True,
                source_type="methodology",
            )
        )
        row = await (
            await db.execute(
                "SELECT COUNT(*), title, journal FROM citations WHERE citekey = ?",
                ("Page2021",),
            )
        ).fetchone()
        assert row is not None
        assert int(row[0]) == 1
        assert row[1] == "Updated title"
        assert row[2] == "BMJ"


@pytest.mark.asyncio
async def test_validation_run_and_checks_persistence(tmp_path) -> None:
    db_path = tmp_path / "validation_tables.db"
    async with get_db(str(db_path)) as db:
        repo = WorkflowRepository(db)
        run = ValidationRunRecord(
            validation_run_id="val-1",
            workflow_id="wf-1",
            profile="quick",
            status="running",
            tool_version="test",
        )
        await repo.save_validation_run(run)
        await repo.save_validation_check(
            ValidationCheckRecord(
                validation_run_id="val-1",
                workflow_id="wf-1",
                phase="phase_3_screening",
                check_name="batch_contract",
                status="pass",
                severity="warn",
                metric_value=0.0,
            )
        )
        latest = await repo.get_latest_validation_run("wf-1")
        assert latest is not None
        assert latest.validation_run_id == "val-1"
        checks = await repo.get_validation_checks("val-1")
        assert len(checks) == 1
        assert checks[0].check_name == "batch_contract"


@pytest.mark.asyncio
async def test_save_fallback_event_is_idempotent_within_generation(tmp_path) -> None:
    db_path = tmp_path / "fallback_event_idempotent.db"
    async with get_db(str(db_path)) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-fallback", "topic", "hash")
        record = FallbackEventRecord(
            workflow_id="wf-fallback",
            phase="phase_6_writing",
            module="writing.section_writer",
            fallback_type="deterministic_section_fallback",
            reason="section=abstract; validation_retries=1",
            paper_id=None,
            details_json='{"validation_issues":["trailing_fragment_punctuation"]}',
        )
        await repo.save_fallback_event(record)
        await repo.save_fallback_event(record)
        row = await (
            await db.execute(
                "SELECT COUNT(*) FROM fallback_events WHERE workflow_id = ?",
                ("wf-fallback",),
            )
        ).fetchone()
        assert row is not None
        assert int(row[0]) == 1


@pytest.mark.asyncio
async def test_get_included_paper_ids_includes_uncertain(tmp_path) -> None:
    """get_included_paper_ids returns papers with include or uncertain at fulltext."""
    db_path = tmp_path / "included_ids.db"
    async with get_db(str(db_path)) as db:
        await db.executescript(Path("src/db/schema.sql").read_text())
        await db.commit()
        repo = WorkflowRepository(db)
        await db.execute(
            "INSERT INTO papers (paper_id, title, authors, source_database) VALUES ('p1', 't1', '[]', 'openalex'), ('p2', 't2', '[]', 'openalex')"
        )
        await db.commit()
        await repo.create_workflow("wf-inc", "topic", "hash")
        await repo.save_dual_screening_result("wf-inc", "p1", "fulltext", True, ScreeningDecisionType.INCLUDE, False)
        await repo.save_dual_screening_result("wf-inc", "p2", "fulltext", True, ScreeningDecisionType.UNCERTAIN, False)
        included = await repo.get_included_paper_ids("wf-inc")
        assert included == {"p1", "p2"}


@pytest.mark.asyncio
async def test_prisma_counts_assessed_falls_back_to_sought_minus_not_retrieved(tmp_path) -> None:
    """reports_assessed should not collapse to 0 when fulltext rows are sparse."""
    db_path = tmp_path / "prisma_counts.db"
    async with get_db(str(db_path)) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-prisma", "topic", "hash")
        # papers table rows for FK integrity
        await db.executemany(
            "INSERT INTO papers (paper_id, title, authors, source_database) VALUES (?, ?, ?, ?)",
            [
                ("p1", "t1", "[]", "openalex"),
                ("p2", "t2", "[]", "openalex"),
                ("p3", "t3", "[]", "openalex"),
            ],
        )
        # title/abstract: all 3 included -> fulltext sought = 3
        await db.executemany(
            "INSERT INTO dual_screening_results (workflow_id, paper_id, stage, agreement, final_decision, adjudication_needed) VALUES (?, ?, ?, ?, ?, ?)",
            [
                ("wf-prisma", "p1", "title_abstract", 1, "include", 0),
                ("wf-prisma", "p2", "title_abstract", 1, "include", 0),
                ("wf-prisma", "p3", "title_abstract", 1, "include", 0),
            ],
        )
        # fulltext-stage rows are absent/sparse, but one no_full_text exclusion exists.
        await db.execute(
            """
            INSERT INTO screening_decisions
                (workflow_id, paper_id, stage, decision, reason, exclusion_reason, reviewer_type, confidence)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("wf-prisma", "p1", "fulltext", "exclude", "no pdf", "no_full_text", "adjudicator", 0.9),
        )
        await db.commit()

        screened, excluded, sought, not_retrieved, assessed, reasons = await repo.get_prisma_screening_counts(
            "wf-prisma"
        )
        assert screened == 3
        assert excluded == 0
        assert sought == 3
        assert not_retrieved == 1
        assert assessed == 2
        assert reasons == {}


@pytest.mark.asyncio
async def test_prisma_counts_prefer_canonical_cohort_fulltext_status(tmp_path) -> None:
    """Canonical cohort fulltext_status should drive sought/not_retrieved/assessed."""
    db_path = tmp_path / "prisma_counts_cohort.db"
    async with get_db(str(db_path)) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-prisma-cohort", "topic", "hash")
        await db.executemany(
            "INSERT INTO papers (paper_id, title, authors, source_database) VALUES (?, ?, ?, ?)",
            [
                ("p1", "t1", "[]", "openalex"),
                ("p2", "t2", "[]", "openalex"),
                ("p3", "t3", "[]", "openalex"),
            ],
        )
        await db.executemany(
            "INSERT INTO dual_screening_results (workflow_id, paper_id, stage, agreement, final_decision, adjudication_needed) VALUES (?, ?, ?, ?, ?, ?)",
            [
                ("wf-prisma-cohort", "p1", "title_abstract", 1, "include", 0),
                ("wf-prisma-cohort", "p2", "title_abstract", 1, "include", 0),
                ("wf-prisma-cohort", "p3", "title_abstract", 1, "include", 0),
            ],
        )
        await db.executemany(
            """
            INSERT INTO study_cohort_membership
                (workflow_id, paper_id, screening_status, fulltext_status, synthesis_eligibility, exclusion_reason_code, source_phase)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("wf-prisma-cohort", "p1", "included", "assessed", "pending", None, "phase_3_screening"),
                (
                    "wf-prisma-cohort",
                    "p2",
                    "excluded",
                    "not_retrieved",
                    "excluded_screening",
                    "no_full_text",
                    "phase_3_screening",
                ),
                (
                    "wf-prisma-cohort",
                    "p3",
                    "excluded",
                    "assessed",
                    "excluded_screening",
                    "screening_excluded",
                    "phase_3_screening",
                ),
            ],
        )
        await db.commit()

        screened, excluded, sought, not_retrieved, assessed, _reasons = await repo.get_prisma_screening_counts(
            "wf-prisma-cohort"
        )
        assert screened == 3
        assert excluded == 0
        assert sought == 3
        assert not_retrieved == 1
        assert assessed == 2


@pytest.mark.asyncio
async def test_save_grade_assessment_skips_placeholder_outcome_names(tmp_path) -> None:
    db_path = tmp_path / "grade_placeholder_guard.db"
    async with get_db(str(db_path)) as db:
        repo = WorkflowRepository(db)
        await repo.save_grade_assessment(
            "wf-grade",
            GRADEOutcomeAssessment(
                outcome_name="not reported",
                number_of_studies=2,
                study_designs="non_randomized",
                starting_certainty=GRADECertainty.LOW,
                risk_of_bias_downgrade=1,
                inconsistency_downgrade=0,
                indirectness_downgrade=0,
                imprecision_downgrade=0,
                publication_bias_downgrade=0,
                large_effect_upgrade=0,
                dose_response_upgrade=0,
                residual_confounding_upgrade=0,
                final_certainty=GRADECertainty.LOW,
                justification="placeholder should be filtered",
            ),
        )
        row = await (
            await db.execute("SELECT COUNT(*) FROM grade_assessments WHERE workflow_id = ?", ("wf-grade",))
        ).fetchone()
        assert row is not None
        assert int(row[0]) == 0


@pytest.mark.asyncio
async def test_delete_placeholder_grade_assessments_removes_stale_rows(tmp_path) -> None:
    db_path = tmp_path / "grade_placeholder_cleanup.db"
    async with get_db(str(db_path)) as db:
        repo = WorkflowRepository(db)
        await db.execute(
            """
            INSERT INTO grade_assessments (workflow_id, outcome_name, assessment_data, final_certainty)
            VALUES (?, ?, ?, ?)
            """,
            (
                "wf-grade",
                "not reported",
                '{"outcome_name":"not reported","number_of_studies":1,"study_designs":"non_randomized","starting_certainty":"low","risk_of_bias_downgrade":0,"inconsistency_downgrade":0,"indirectness_downgrade":0,"imprecision_downgrade":0,"publication_bias_downgrade":0,"large_effect_upgrade":0,"dose_response_upgrade":0,"residual_confounding_upgrade":0,"final_certainty":"low","justification":"placeholder","inconsistency_assessed":true,"indirectness_assessed":true}',
                "low",
            ),
        )
        await db.execute(
            """
            INSERT INTO grade_assessments (workflow_id, outcome_name, assessment_data, final_certainty)
            VALUES (?, ?, ?, ?)
            """,
            (
                "wf-grade",
                "dispensing accuracy",
                '{"outcome_name":"dispensing accuracy","number_of_studies":1,"study_designs":"non_randomized","starting_certainty":"low","risk_of_bias_downgrade":0,"inconsistency_downgrade":0,"indirectness_downgrade":0,"imprecision_downgrade":0,"publication_bias_downgrade":0,"large_effect_upgrade":0,"dose_response_upgrade":0,"residual_confounding_upgrade":0,"final_certainty":"low","justification":"valid","inconsistency_assessed":true,"indirectness_assessed":true}',
                "low",
            ),
        )
        await db.commit()
        removed = await repo.delete_placeholder_grade_assessments("wf-grade")
        assert removed == 1
        row = await (
            await db.execute("SELECT COUNT(*) FROM grade_assessments WHERE workflow_id = ?", ("wf-grade",))
        ).fetchone()
        assert row is not None
        assert int(row[0]) == 1


@pytest.mark.asyncio
async def test_failed_search_connectors_filters_by_workflow(tmp_path) -> None:
    db_path = tmp_path / "connector_failures.db"
    async with get_db(str(db_path)) as db:
        repo = WorkflowRepository(db)
        await repo.append_decision_log(
            DecisionLogEntry(
                workflow_id="wf-target",
                decision_type="search_connector_error",
                decision="error",
                rationale="OpenAlex: RuntimeError: quota exceeded",
                actor="search",
                phase="phase_2_search",
            )
        )
        await repo.append_decision_log(
            DecisionLogEntry(
                workflow_id="wf-other",
                decision_type="search_connector_error",
                decision="error",
                rationale="Scopus: RuntimeError: bad key",
                actor="search",
                phase="phase_2_search",
            )
        )
        out = await repo.get_failed_search_connectors("wf-target")
        assert out == ["OpenAlex"]


@pytest.mark.asyncio
async def test_save_section_draft_dual_writes_manuscript_tables(tmp_path) -> None:
    db_path = tmp_path / "manuscript_tables.db"
    async with get_db(str(db_path)) as db:
        repo = WorkflowRepository(db)
        draft = SectionDraft(
            workflow_id="wf-manu",
            section="methods",
            version=1,
            content="<!-- SECTION_BLOCK:information_sources -->\n### Information Sources\n\nText body.",
            claims_used=[],
            citations_used=[],
            word_count=6,
        )
        await repo.save_section_draft(draft)
        await repo.save_manuscript_section_from_draft(draft, section_order=2)
        sections = await repo.load_latest_manuscript_sections("wf-manu")
        assert len(sections) == 1
        assert sections[0].section_key == "methods"
        cur = await db.execute(
            "SELECT COUNT(*) FROM manuscript_blocks WHERE workflow_id=? AND section_key=?",
            ("wf-manu", "methods"),
        )
        row = await cur.fetchone()
        assert row is not None
        assert int(row[0]) >= 2


@pytest.mark.asyncio
async def test_save_manuscript_section_from_draft_is_idempotent_for_retries(tmp_path) -> None:
    db_path = tmp_path / "manuscript_retry.db"
    async with get_db(str(db_path)) as db:
        repo = WorkflowRepository(db)
        draft = SectionDraft(
            workflow_id="wf-retry",
            section="abstract",
            version=1,
            content="**Background:** Text. **Objectives:** Text. **Methods:** Text. **Results:** Text. **Conclusion:** Text.",
            claims_used=[],
            citations_used=[],
            word_count=10,
        )
        await repo.save_section_draft(draft)
        await repo.save_manuscript_section_from_draft(draft, section_order=0)
        await repo.save_manuscript_section_from_draft(draft, section_order=0)

        section_count = await (
            await db.execute("SELECT COUNT(*) FROM manuscript_sections WHERE workflow_id = ?", ("wf-retry",))
        ).fetchone()
        block_count = await (
            await db.execute("SELECT COUNT(*) FROM manuscript_blocks WHERE workflow_id = ?", ("wf-retry",))
        ).fetchone()

    assert int(section_count[0]) == 1
    assert int(block_count[0]) >= 1


@pytest.mark.asyncio
async def test_save_manuscript_assembly_validates_manifest_refs(tmp_path) -> None:
    db_path = tmp_path / "assembly_manifest.db"
    async with get_db(str(db_path)) as db:
        repo = WorkflowRepository(db)
        draft = SectionDraft(
            workflow_id="wf-asm",
            section="results",
            version=1,
            content="### Study Selection\n\nBody text.",
            claims_used=[],
            citations_used=[],
            word_count=4,
        )
        await repo.save_section_draft(draft)
        await repo.save_manuscript_section_from_draft(draft, section_order=0)
        await repo.save_manuscript_assembly(
            ManuscriptAssembly(
                workflow_id="wf-asm",
                assembly_id="latest",
                target_format="md",
                content="content",
                manifest_json='{"sections":[{"section_key":"results","version":1,"order":0}]}',
            )
        )
        got = await repo.load_latest_manuscript_assembly("wf-asm", "md")
        assert got is not None
        assert got.assembly_id == "latest"


@pytest.mark.asyncio
async def test_validate_manuscript_md_parity(tmp_path) -> None:
    db_path = tmp_path / "parity.db"
    async with get_db(str(db_path)) as db:
        repo = WorkflowRepository(db)
        draft = SectionDraft(
            workflow_id="wf-parity",
            section="discussion",
            version=1,
            content="## Discussion\n\nText [1].",
            claims_used=[],
            citations_used=[],
            word_count=4,
        )
        await repo.save_section_draft(draft)
        await repo.save_manuscript_section_from_draft(draft, section_order=0)
        md = "## Discussion\n\nText [1]."
        await repo.save_manuscript_assembly(
            ManuscriptAssembly(
                workflow_id="wf-parity",
                assembly_id="latest",
                target_format="md",
                content=md,
                manifest_json='{"sections":[{"section_key":"discussion","version":1,"order":0}]}',
            )
        )
        parity = await repo.validate_manuscript_md_parity("wf-parity", md)
        assert parity["has_assembly"] is True
        assert parity["citation_set_match"] is True


@pytest.mark.asyncio
async def test_generation_aware_writing_reads_use_active_generation(tmp_path) -> None:
    db_path = tmp_path / "writing_generation_reads.db"
    async with get_db(str(db_path)) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-gen", "topic", "hash")
        await repo.save_section_draft(
            SectionDraft(
                workflow_id="wf-gen",
                section="results",
                version=1,
                content="old results",
                claims_used=[],
                citations_used=[],
                word_count=2,
            )
        )
        await repo.save_writing_manifest(
            WritingManifestRecord(
                workflow_id="wf-gen",
                section_key="results",
                attempt_number=1,
                contract_status="warning",
            )
        )
        await repo.save_fallback_event(
            FallbackEventRecord(
                workflow_id="wf-gen",
                phase="phase_6_writing",
                module="writing.section_writer",
                fallback_type="deterministic_section_fallback",
                reason="section=results",
            )
        )
        await repo.bump_writing_generation("wf-gen")
        await db.execute(
            """
            INSERT INTO section_drafts (workflow_id, section, version, generation, content, claims_used, citations_used, word_count)
            VALUES (?, ?, ?, ?, ?, '[]', '[]', ?)
            """,
            ("wf-gen", "discussion", 1, 2, "new discussion", 2),
        )
        await db.execute(
            """
            INSERT INTO writing_manifests (
                workflow_id, section_key, attempt_number, generation, contract_status, contract_issues, fallback_used, retry_count, meta_json
            ) VALUES (?, ?, ?, ?, ?, '[]', 0, 0, '{}')
            """,
            ("wf-gen", "discussion", 1, 2, "passed"),
        )
        await db.execute(
            """
            INSERT INTO fallback_events (
                workflow_id, phase, module, fallback_type, reason, generation, details_json
            ) VALUES (?, ?, ?, ?, ?, ?, '{}')
            """,
            ("wf-gen", "phase_6_writing", "rag.retrieval", "empty_context", "section=discussion", 2),
        )
        await db.commit()

        assert await repo.get_completed_sections("wf-gen") == {"discussion"}
        manifests = await repo.get_writing_manifests("wf-gen")
        assert [m.section_key for m in manifests] == ["discussion"]
        assert await repo.count_fallback_events("wf-gen") == 1
