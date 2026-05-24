from __future__ import annotations

from pathlib import Path

import pytest

from src.db.database import get_db
from src.db.repositories import CitationRepository, WorkflowRepository
from src.manuscript.contracts import run_manuscript_contracts
from src.manuscript.readiness import compute_readiness_scorecard
from src.manuscript.reviewer import select_audit_profiles
from src.models import (
    CitationEntryRecord,
    DomainExpertConfig,
    FallbackEventRecord,
    ManuscriptAuditResult,
    ReviewConfig,
    ReviewType,
    SettingsConfig,
)


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


async def _seed_citation(db_path: Path) -> None:
    async with get_db(str(db_path)) as db:
        await CitationRepository(db).register_citation(
            CitationEntryRecord(
                citekey="Smith2024",
                title="Reference study",
                authors=["Smith"],
                resolved=True,
            )
        )


async def _seed_manuscript_audit(
    db_path: Path,
    workflow_id: str,
    *,
    passed: bool,
    gate_blocked: bool,
    gate_action: str,
    gate_failure_reasons: list[str] | None = None,
) -> None:
    async with get_db(str(db_path)) as db:
        repo = WorkflowRepository(db)
        await repo.save_manuscript_audit(
            ManuscriptAuditResult(
                audit_run_id=f"audit-{workflow_id}",
                workflow_id=workflow_id,
                mode="strict",
                verdict="accept" if passed else "major_revisions",
                passed=passed,
                selected_profiles=["general_systematic_review"],
                summary="ok" if passed else "needs revision",
                total_findings=0 if passed else 2,
                major_count=0 if passed else 1,
                minor_count=0 if passed else 1,
                note_count=0,
                blocking_count=0 if passed else 1,
                total_cost_usd=0.0,
            ),
            findings=[],
            gate_blocked=gate_blocked,
            gate_mode="advisory" if gate_action == "advisory_only" else "strict",
            gate_action=gate_action,
            gate_failure_reasons=gate_failure_reasons or [],
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
    await _seed_citation(db_path)

    scorecard = await compute_readiness_scorecard(
        db_path=str(db_path),
        workflow_id="wf-ready",
        manuscript_md_path=str(manuscript_md),
        manuscript_tex_path=str(manuscript_tex),
        contract_mode="observe",
    )
    assert scorecard.fallback_event_count == 1
    assert scorecard.audit_ready is False
    assert scorecard.submission_ready is False
    assert scorecard.ready is False
    assert scorecard.citation_lineage_valid is True
    assert any(check.name == "fallback_events" for check in scorecard.checks)
    assert any(check.name == "manuscript_audit" and not check.ok for check in scorecard.checks)


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
    await _seed_citation(db_path)

    scorecard = await compute_readiness_scorecard(
        db_path=str(db_path),
        workflow_id="wf-ready-tex",
        manuscript_md_path=str(manuscript_md),
        manuscript_tex_path=str(manuscript_tex),
        contract_mode="observe",
    )

    assert scorecard.workflow_id == "wf-ready-tex"
    assert scorecard.citation_lineage_valid is True
    assert any(check.name == "manuscript_contracts" for check in scorecard.checks)


@pytest.mark.asyncio
async def test_readiness_blocks_invalid_citation_lineage(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime_readiness_lineage.db"
    manuscript_md = tmp_path / "doc_manuscript.md"
    manuscript_tex = tmp_path / "doc_manuscript.tex"
    _write_minimal_manuscript(manuscript_md, manuscript_tex)
    await _seed_citation(db_path)

    async with get_db(str(db_path)) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-ready-lineage", "topic", "hash")
        await repo.save_checkpoint("wf-ready-lineage", "finalize", 1)

    manuscript_md.write_text(
        manuscript_md.read_text(encoding="utf-8").replace("[1] Ref", "[2] Ref"),
        encoding="utf-8",
    )
    scorecard = await compute_readiness_scorecard(
        db_path=str(db_path),
        workflow_id="wf-ready-lineage",
        manuscript_md_path=str(manuscript_md),
        manuscript_tex_path=str(manuscript_tex),
        contract_mode="strict",
    )
    assert scorecard.citation_lineage_valid is False
    assert scorecard.ready is False
    assert any(check.name == "citation_lineage" and not check.ok for check in scorecard.checks)


@pytest.mark.asyncio
async def test_readiness_marks_audit_ready_when_latest_audit_passed(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime_readiness_audit_pass.db"
    manuscript_md = tmp_path / "doc_manuscript.md"
    manuscript_tex = tmp_path / "doc_manuscript.tex"
    _write_minimal_manuscript(manuscript_md, manuscript_tex)

    async with get_db(str(db_path)) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-ready-audit-pass", "topic", "hash")
        await repo.save_checkpoint("wf-ready-audit-pass", "finalize", 1)
    await _seed_citation(db_path)
    await _seed_manuscript_audit(
        db_path,
        "wf-ready-audit-pass",
        passed=True,
        gate_blocked=False,
        gate_action="pass",
    )

    scorecard = await compute_readiness_scorecard(
        db_path=str(db_path),
        workflow_id="wf-ready-audit-pass",
        manuscript_md_path=str(manuscript_md),
        manuscript_tex_path=str(manuscript_tex),
        contract_mode="observe",
    )

    assert scorecard.contract_ready is True
    assert scorecard.audit_ready is True
    assert scorecard.submission_ready == scorecard.ready
    assert any(check.name == "manuscript_audit" and check.ok for check in scorecard.checks)


@pytest.mark.asyncio
async def test_readiness_blocks_submission_when_audit_is_advisory_only(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime_readiness_advisory_audit.db"
    manuscript_md = tmp_path / "doc_manuscript.md"
    manuscript_tex = tmp_path / "doc_manuscript.tex"
    _write_minimal_manuscript(manuscript_md, manuscript_tex)

    async with get_db(str(db_path)) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-ready-audit-advisory", "topic", "hash")
        await repo.save_checkpoint("wf-ready-audit-advisory", "finalize", 1)
    await _seed_citation(db_path)
    await _seed_manuscript_audit(
        db_path,
        "wf-ready-audit-advisory",
        passed=False,
        gate_blocked=True,
        gate_action="advisory_only",
        gate_failure_reasons=["audit gate failed in mode=strict (verdict=major_revisions, blocking=1)"],
    )

    scorecard = await compute_readiness_scorecard(
        db_path=str(db_path),
        workflow_id="wf-ready-audit-advisory",
        manuscript_md_path=str(manuscript_md),
        manuscript_tex_path=str(manuscript_tex),
        contract_mode="observe",
    )

    assert scorecard.audit_ready is False
    assert scorecard.submission_ready is False
    assert scorecard.ready is False
    assert any("manuscript audit blocked readiness" in reason for reason in scorecard.blocking_reasons)


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
        pico={
            "population": "students",
            "intervention": "AI tutor",
            "comparison": "standard teaching",
            "outcome": "learning gain",
        },
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
        pico={
            "population": "students",
            "intervention": "AI tutor",
            "comparison": "standard teaching",
            "outcome": "learning gain",
        },
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
        agents={"writing": {"model": "google:gemini-2.5-flash-lite", "temperature": 0.1}},
        manuscript_audit={"profile_activation": "domain_matched", "max_profiles_per_run": 3},
    )
    selection = select_audit_profiles(review, settings)
    assert "implementation_science" in selection.selected_profiles
