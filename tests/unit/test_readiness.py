from __future__ import annotations

from pathlib import Path

import pytest

from src.db.database import get_db
from src.db.repositories import CitationRepository, WorkflowRepository
from src.manuscript.contracts import run_manuscript_contracts
from src.manuscript.readiness import compute_readiness_scorecard
from src.manuscript.reviewer import select_audit_profiles
from src.models import DomainExpertConfig, FallbackEventRecord, ReviewConfig, ReviewType, SettingsConfig


def _write_minimal_manuscript(md_path: Path, tex_path: Path) -> None:
    md_path.write_text(
        "\n".join(
            [
                "## Abstract",
                "**Background:** text",
                "**Objectives:** obj",
                "**Methods:** meth",
                "**Results:** res",
                "**Conclusions:** conc",
                "## Introduction",
                "Intro.",
                "## Methods",
                "Methods.",
                "## Results",
                "Results.",
                "## Discussion",
                "Discussion.",
                "## Conclusion",
                "Conclusion.",
                "## References",
                "[1] Ref",
            ]
        ),
        encoding="utf-8",
    )
    tex_path.write_text(
        "\\section{Abstract}\n\\section{Introduction}\n\\section{Methods}\n\\section{Results}\n"
        "\\section{Discussion}\n\\section{Conclusion}\n\\section{References}\n",
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_contract_detects_deterministic_section_fallback(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime_contract_fallback.db"
    manuscript_md = tmp_path / "doc_manuscript.md"
    manuscript_tex = tmp_path / "doc_manuscript.tex"
    _write_minimal_manuscript(manuscript_md, manuscript_tex)

    async with get_db(str(db_path)) as db:
        repo = WorkflowRepository(db)
        cite_repo = CitationRepository(db)
        await repo.create_workflow("wf-fallback", "topic", "hash")
        await repo.save_fallback_event(
            FallbackEventRecord(
                workflow_id="wf-fallback",
                phase="phase_6_writing",
                module="writing.section_writer",
                fallback_type="deterministic_section_fallback",
                reason="section=results",
            )
        )
        result = await run_manuscript_contracts(
            repository=repo,
            citation_repository=cite_repo,
            workflow_id="wf-fallback",
            manuscript_md_path=str(manuscript_md),
            manuscript_tex_path=str(manuscript_tex),
            mode="strict",
        )

    assert any(v.code == "SECTION_DETERMINISTIC_FALLBACK" for v in result.violations)


@pytest.mark.asyncio
async def test_readiness_reports_fallback_event_count(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime_readiness.db"
    manuscript_md = tmp_path / "doc_manuscript.md"
    manuscript_tex = tmp_path / "doc_manuscript.tex"
    _write_minimal_manuscript(manuscript_md, manuscript_tex)

    async with get_db(str(db_path)) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-ready", "topic", "hash")
        await repo.save_checkpoint("wf-ready", "finalize", 1)
        await repo.save_fallback_event(
            FallbackEventRecord(
                workflow_id="wf-ready",
                phase="phase_6_writing",
                module="rag.retrieval",
                fallback_type="empty_retrieval_context",
                reason="section=discussion",
            )
        )

    scorecard = await compute_readiness_scorecard(
        db_path=str(db_path),
        workflow_id="wf-ready",
        manuscript_md_path=str(manuscript_md),
        manuscript_tex_path=str(manuscript_tex),
        contract_mode="observe",
    )
    assert scorecard.fallback_event_count == 1
    assert scorecard.ready is False
    assert any(check.name == "fallback_events" for check in scorecard.checks)


@pytest.mark.asyncio
async def test_readiness_handles_tex_heading_parity_without_name_error(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime_readiness_tex.db"
    manuscript_md = tmp_path / "doc_manuscript.md"
    manuscript_tex = tmp_path / "doc_manuscript.tex"
    _write_minimal_manuscript(manuscript_md, manuscript_tex)

    async with get_db(str(db_path)) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-ready-tex", "topic", "hash")
        await repo.save_checkpoint("wf-ready-tex", "finalize", 1)

    scorecard = await compute_readiness_scorecard(
        db_path=str(db_path),
        workflow_id="wf-ready-tex",
        manuscript_md_path=str(manuscript_md),
        manuscript_tex_path=str(manuscript_tex),
        contract_mode="observe",
    )

    assert scorecard.workflow_id == "wf-ready-tex"
    assert any(check.name == "manuscript_contracts" for check in scorecard.checks)


@pytest.mark.asyncio
async def test_contract_ignores_citation_ended_tail_paragraphs(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime_contract_tail.db"
    manuscript_md = tmp_path / "doc_manuscript.md"
    manuscript_tex = tmp_path / "doc_manuscript.tex"
    manuscript_md.write_text(
        "\n".join(
            [
                "## Abstract",
                "**Background:** text",
                "**Objectives:** obj",
                "**Methods:** meth",
                "**Results:** res",
                "**Conclusions:** conc",
                "## Introduction",
                "Intro paragraph.",
                "## Methods",
                "Methods paragraph.",
                "## Results",
                "First results paragraph with adequate detail, grounded evidence, and enough methodological context to exceed the substantive threshold cleanly. [1]",
                "",
                "Second results paragraph with adequate detail, grounded evidence, and enough methodological context to exceed the substantive threshold cleanly. [2]",
                "## Discussion",
                "First discussion paragraph with adequate detail, grounded evidence, and enough methodological context to exceed the substantive threshold cleanly. [1]",
                "",
                "Second discussion paragraph with adequate detail, grounded evidence, and enough methodological context to exceed the substantive threshold cleanly. [2]",
                "## Conclusion",
                "Conclusion paragraph.",
                "## References",
                "[1] Ref one",
                "[2] Ref two",
            ]
        ),
        encoding="utf-8",
    )
    manuscript_tex.write_text(
        "\\section{Abstract}\n\\section{Introduction}\n\\section{Methods}\n\\section{Results}\n"
        "\\section{Discussion}\n\\section{Conclusion}\n\\section{References}\n",
        encoding="utf-8",
    )

    async with get_db(str(db_path)) as db:
        repo = WorkflowRepository(db)
        cite_repo = CitationRepository(db)
        await repo.create_workflow("wf-tail", "topic", "hash")
        result = await run_manuscript_contracts(
            repository=repo,
            citation_repository=cite_repo,
            workflow_id="wf-tail",
            manuscript_md_path=str(manuscript_md),
            manuscript_tex_path=str(manuscript_tex),
            mode="strict",
        )

    assert not any(v.code == "SECTION_CONTENT_INCOMPLETE" for v in result.violations)


@pytest.mark.asyncio
async def test_contract_ignores_stale_generation_fallback_events(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime_contract_generation.db"
    manuscript_md = tmp_path / "doc_manuscript.md"
    manuscript_tex = tmp_path / "doc_manuscript.tex"
    _write_minimal_manuscript(manuscript_md, manuscript_tex)

    async with get_db(str(db_path)) as db:
        repo = WorkflowRepository(db)
        cite_repo = CitationRepository(db)
        await repo.create_workflow("wf-stale-fallback", "topic", "hash")
        await repo.save_fallback_event(
            FallbackEventRecord(
                workflow_id="wf-stale-fallback",
                phase="phase_6_writing",
                module="writing.section_writer",
                fallback_type="deterministic_section_fallback",
                reason="section=results",
            )
        )
        await repo.bump_writing_generation("wf-stale-fallback")
        result = await run_manuscript_contracts(
            repository=repo,
            citation_repository=cite_repo,
            workflow_id="wf-stale-fallback",
            manuscript_md_path=str(manuscript_md),
            manuscript_tex_path=str(manuscript_tex),
            mode="strict",
        )

    assert not any(v.code == "SECTION_DETERMINISTIC_FALLBACK" for v in result.violations)


@pytest.mark.asyncio
async def test_contract_flags_domain_scope_drift_terms(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime_contract_domain.db"
    manuscript_md = tmp_path / "doc_manuscript.md"
    manuscript_tex = tmp_path / "doc_manuscript.tex"
    _write_minimal_manuscript(manuscript_md, manuscript_tex)
    manuscript_md.write_text(
        manuscript_md.read_text(encoding="utf-8").replace("Discussion.", "Discussion with clinical endpoint framing."),
        encoding="utf-8",
    )

    review = ReviewConfig(
        research_question="How do AI tutors affect learning gain?",
        review_type=ReviewType.SYSTEMATIC,
        pico={"population": "students", "intervention": "AI tutor", "comparison": "standard teaching", "outcome": "learning gain"},
        keywords=["AI tutor", "learning gain"],
        domain="education",
        scope="Education interventions and learner outcomes.",
        domain_expert=DomainExpertConfig(
            canonical_terms=["AI tutor", "learning gain"],
            excluded_terms=["clinical endpoint"],
        ),
        inclusion_criteria=["Empirical studies."],
        exclusion_criteria=["Opinion pieces."],
        date_range_start=2015,
        date_range_end=2026,
        target_databases=["openalex"],
    )

    async with get_db(str(db_path)) as db:
        repo = WorkflowRepository(db)
        cite_repo = CitationRepository(db)
        await repo.create_workflow("wf-domain-contract", "topic", "hash")
        result = await run_manuscript_contracts(
            repository=repo,
            citation_repository=cite_repo,
            workflow_id="wf-domain-contract",
            manuscript_md_path=str(manuscript_md),
            manuscript_tex_path=str(manuscript_tex),
            mode="observe",
            review_config=review,
        )

    assert any(v.code == "DOMAIN_SCOPE_DRIFT" for v in result.violations)


def test_audit_profile_selection_uses_domain_brief() -> None:
    review = ReviewConfig(
        research_question="What implementation barriers affect school AI tutor adoption?",
        review_type=ReviewType.SYSTEMATIC,
        pico={"population": "students", "intervention": "AI tutor", "comparison": "standard teaching", "outcome": "learning gain"},
        keywords=["AI tutor", "barriers"],
        domain="education",
        scope="Education implementation review.",
        domain_expert=DomainExpertConfig(
            related_terms=["implementation barrier", "facilitator"],
            methodological_focus=["implementation fidelity"],
        ),
        inclusion_criteria=["Empirical studies."],
        exclusion_criteria=["Opinion pieces."],
        date_range_start=2015,
        date_range_end=2026,
        target_databases=["openalex"],
    )
    settings = SettingsConfig(
        agents={"writing": {"model": "google-gla:gemini-2.5-flash-lite", "temperature": 0.1}},
        manuscript_audit={"profile_activation": "domain_matched", "max_profiles_per_run": 3},
    )
    selection = select_audit_profiles(review, settings)
    assert "implementation_science" in selection.selected_profiles
