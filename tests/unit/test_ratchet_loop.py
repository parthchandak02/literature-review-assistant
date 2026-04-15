from __future__ import annotations

import json

import pytest

from src.citation.ledger import CitationLedger
from src.db.database import get_db
from src.db.repositories import CitationRepository, WorkflowRepository
from src.models import AgentConfig, ReviewConfig, ReviewType, SectionQualityScore, SettingsConfig
from src.models.writing import SectionBlock, StructuredSectionDraft
from src.writing.context_builder import WritingGroundingData
from src.writing.orchestration import write_section_with_validation
from src.writing.section_writer import SectionWriteMetadata


def _review() -> ReviewConfig:
    return ReviewConfig(
        research_question="Does spaced repetition improve exam performance?",
        review_type=ReviewType.SYSTEMATIC,
        pico={
            "population": "university students",
            "intervention": "spaced repetition flashcards",
            "comparison": "usual study methods",
            "outcome": "exam performance",
        },
        keywords=["spaced repetition", "flashcards", "exam performance"],
        domain="education",
        scope="systematic review scope",
        inclusion_criteria=["primary empirical studies"],
        exclusion_criteria=["secondary reviews"],
        date_range_start=2020,
        date_range_end=2026,
        target_databases=["openalex"],
    )


def _settings(*, max_iterations: int = 2, cost_cap: float = 0.15) -> SettingsConfig:
    return SettingsConfig(
        agents={"writing": AgentConfig(model="google-gla:gemini-2.5-flash", temperature=0.1)},
        writing={
            "ratchet_max_iterations": max_iterations,
            "ratchet_cost_cap_per_section": cost_cap,
            "ratchet_outline_enabled": True,
            "abstract_trim_floor_words": 80,
        },
    )


def _grounding() -> WritingGroundingData:
    return WritingGroundingData(
        databases_searched=["OpenAlex"],
        other_methods_searched=[],
        search_date="2026-04-08",
        total_identified=10,
        duplicates_removed=1,
        total_screened=9,
        fulltext_assessed=3,
        total_included=3,
        fulltext_excluded=0,
        excluded_fulltext_reasons={},
        study_design_counts={"randomized controlled trial": 2},
        total_participants=120,
        year_range="2020-2024",
        meta_analysis_feasible=False,
        synthesis_direction="mixed",
        n_studies_synthesized=3,
        narrative_text="Narrative synthesis only.",
        key_themes=["engagement"],
        study_summaries=[],
        valid_citekeys=["Smith2024"],
        included_study_citekeys=["Smith2024"],
        fulltext_sought=3,
        fulltext_not_retrieved=0,
    )


def _intro_draft(text: str) -> StructuredSectionDraft:
    return StructuredSectionDraft(
        section_key="introduction",
        blocks=[SectionBlock(block_type="paragraph", text=text)],
    )


def _abstract_draft() -> StructuredSectionDraft:
    return StructuredSectionDraft(
        section_key="abstract",
        blocks=[
            SectionBlock(block_type="paragraph", text="**Background:** Short background."),
            SectionBlock(block_type="paragraph", text="**Objectives:** Short objective."),
            SectionBlock(block_type="paragraph", text="**Methods:** Short methods."),
            SectionBlock(block_type="paragraph", text="**Results:** Short results."),
            SectionBlock(block_type="paragraph", text="**Conclusions:** Short conclusion."),
            SectionBlock(block_type="paragraph", text="**Keywords:** spaced repetition, exams."),
        ],
    )


async def _citation_validation_stub(self, section: str, content: str):
    _ = (self, section, content)

    class _Result:
        unresolved_citations: list[str] = []
        unresolved_claims: list[str] = []

    return _Result()


def _patch_writer(monkeypatch, responses: list[tuple[StructuredSectionDraft, float]]):
    calls = {"count": 0}

    async def _fake_write(self, section: str, context: str, word_limit=None, agent_name: str = "writing"):
        _ = (self, section, context, word_limit, agent_name)
        calls["count"] += 1
        draft, cost_usd = responses[calls["count"] - 1]
        return draft, SectionWriteMetadata(
            model="google-gla:gemini-2.5-flash",
            tokens_in=10,
            tokens_out=20,
            cost_usd=cost_usd,
            latency_ms=5,
        )

    monkeypatch.setattr(
        "src.writing.section_writer.SectionWriter.write_section_structured_async",
        _fake_write,
    )

    async def _no_claims(*args, **kwargs):
        _ = (args, kwargs)
        return 0

    monkeypatch.setattr(
        "src.writing.orchestration.extract_and_register_claims",
        _no_claims,
    )
    monkeypatch.setattr(CitationLedger, "validate_section", _citation_validation_stub)
    monkeypatch.setattr(
        "src.writing.orchestration._validate_structured_section_draft",
        lambda section, draft, valid_citekeys: (draft, []),
    )
    monkeypatch.setattr(
        "src.writing.orchestration._apply_structured_grounding_patches",
        lambda section, draft, grounding, review, settings, valid_citekeys: draft,
    )
    monkeypatch.setattr("src.writing.orchestration._section_completeness_issues", lambda *args, **kwargs: [])
    monkeypatch.setattr("src.writing.orchestration._post_render_completeness_issues", lambda *args, **kwargs: [])
    monkeypatch.setattr("src.writing.orchestration._rendered_citation_integrity_issues", lambda *args, **kwargs: [])
    monkeypatch.setattr("src.writing.orchestration._grounding_integrity_issues", lambda *args, **kwargs: [])
    monkeypatch.setattr("src.writing.orchestration._topic_anchor_issues", lambda *args, **kwargs: [])
    return calls


@pytest.mark.asyncio
async def test_ratchet_loop_keeps_second_iteration_when_score_improves(tmp_path, monkeypatch) -> None:
    calls = _patch_writer(
        monkeypatch,
        [(_intro_draft("First draft."), 0.01), (_intro_draft("Improved draft."), 0.01)],
    )
    monkeypatch.setattr(
        "src.writing.orchestration.compute_section_quality_score",
        lambda **kwargs: (
            SectionQualityScore(hard_issue_count=0 if "Improved" in kwargs["rendered"] else 1),
            ["improved"] if "Improved" in kwargs["rendered"] else ["baseline"],
        ),
    )

    async with get_db(str(tmp_path / "ratchet_improve.db")) as db:
        await WorkflowRepository(db).create_workflow("wf-improve", "topic", "hash")
        result = await write_section_with_validation(
            section="introduction",
            context="context",
            workflow_id="wf-improve",
            review=_review(),
            settings=_settings(),
            citation_repo=CitationRepository(db),
        )

    meta = json.loads(result.ratchet_meta_json)
    assert result.content_markdown == "Improved draft."
    assert calls["count"] == 2
    assert meta["ratchet_winner"] == 2


@pytest.mark.asyncio
async def test_ratchet_loop_keeps_first_iteration_on_regression(tmp_path, monkeypatch) -> None:
    calls = _patch_writer(
        monkeypatch,
        [(_intro_draft("Best draft."), 0.01), (_intro_draft("Worse draft."), 0.01)],
    )
    monkeypatch.setattr(
        "src.writing.orchestration.compute_section_quality_score",
        lambda **kwargs: (
            SectionQualityScore(hard_issue_count=0 if "Best" in kwargs["rendered"] else 1),
            ["best"] if "Best" in kwargs["rendered"] else ["worse"],
        ),
    )

    async with get_db(str(tmp_path / "ratchet_regress.db")) as db:
        await WorkflowRepository(db).create_workflow("wf-regress", "topic", "hash")
        result = await write_section_with_validation(
            section="introduction",
            context="context",
            workflow_id="wf-regress",
            review=_review(),
            settings=_settings(),
            citation_repo=CitationRepository(db),
        )

    meta = json.loads(result.ratchet_meta_json)
    assert result.content_markdown == "Best draft."
    assert calls["count"] == 2
    assert meta["ratchet_winner"] == 1


@pytest.mark.asyncio
async def test_ratchet_loop_stops_after_duplicate_fingerprint(tmp_path, monkeypatch) -> None:
    calls = _patch_writer(
        monkeypatch,
        [(_intro_draft("Same draft."), 0.01), (_intro_draft("Same draft."), 0.01)],
    )
    monkeypatch.setattr(
        "src.writing.orchestration.compute_section_quality_score",
        lambda **kwargs: (SectionQualityScore(hard_issue_count=0), ["same"]),
    )

    async with get_db(str(tmp_path / "ratchet_same.db")) as db:
        await WorkflowRepository(db).create_workflow("wf-same", "topic", "hash")
        result = await write_section_with_validation(
            section="introduction",
            context="context",
            workflow_id="wf-same",
            review=_review(),
            settings=_settings(),
            citation_repo=CitationRepository(db),
        )

    meta = json.loads(result.ratchet_meta_json)
    assert result.content_markdown == "Same draft."
    assert calls["count"] == 2
    assert meta["ratchet_iterations"] == 2


@pytest.mark.asyncio
async def test_ratchet_loop_stops_after_first_iteration_when_cost_cap_exceeded(tmp_path, monkeypatch) -> None:
    calls = _patch_writer(
        monkeypatch,
        [(_intro_draft("Expensive draft."), 0.02)],
    )
    monkeypatch.setattr(
        "src.writing.orchestration.compute_section_quality_score",
        lambda **kwargs: (SectionQualityScore(hard_issue_count=0), ["ok"]),
    )

    async with get_db(str(tmp_path / "ratchet_cost.db")) as db:
        await WorkflowRepository(db).create_workflow("wf-cost", "topic", "hash")
        result = await write_section_with_validation(
            section="introduction",
            context="context",
            workflow_id="wf-cost",
            review=_review(),
            settings=_settings(cost_cap=0.01),
            citation_repo=CitationRepository(db),
        )

    meta = json.loads(result.ratchet_meta_json)
    assert result.content_markdown == "Expensive draft."
    assert calls["count"] == 1
    assert meta["ratchet_iterations"] == 1


@pytest.mark.asyncio
async def test_ratchet_loop_stops_after_first_iteration_when_fallback_used(tmp_path, monkeypatch) -> None:
    calls = _patch_writer(monkeypatch, [(_abstract_draft(), 0.01)])
    monkeypatch.setattr(
        "src.writing.orchestration.compute_section_quality_score",
        lambda **kwargs: (SectionQualityScore(hard_issue_count=0), ["ok"]),
    )

    async with get_db(str(tmp_path / "ratchet_fallback.db")) as db:
        await WorkflowRepository(db).create_workflow("wf-fallback", "topic", "hash")
        result = await write_section_with_validation(
            section="abstract",
            context="context",
            workflow_id="wf-fallback",
            review=_review(),
            settings=_settings(),
            citation_repo=CitationRepository(db),
            grounding=_grounding(),
        )

    meta = json.loads(result.ratchet_meta_json)
    assert result.used_deterministic_fallback is True
    assert calls["count"] == 1
    assert meta["ratchet_iterations"] == 1
