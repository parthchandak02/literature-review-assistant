from __future__ import annotations

import json

import pytest

from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.llm.provider import LLMProvider
from src.models import (
    CandidatePaper,
    DomainExpertConfig,
    ExclusionReason,
    ReviewConfig,
    ReviewerType,
    ReviewType,
    ScreeningDecisionType,
    SettingsConfig,
)
from src.models.config import ScreeningConfig
from src.screening.dual_screener import DualReviewerScreener, ReviewerSpec, ScreeningLLMClient
from src.screening.prompts import reviewer_a_prompt


class _ScriptedClient(ScreeningLLMClient):
    def __init__(self, responses: list[dict[str, object]]):
        self._responses = responses

    async def complete_json(
        self,
        prompt: str,
        *,
        agent_name: str,
        model: str,
        temperature: float,
    ) -> str:
        _ = (prompt, agent_name, model, temperature)
        payload = self._responses.pop(0)
        return json.dumps(payload)


class _SchemaAwareBatchClient:
    """Scripted client that exposes batch-array usage method for dual_screener."""

    def __init__(self, responses: list[object]):
        self._responses = responses
        self.array_schema_calls = 0
        self.last_item_schema: dict[str, object] | None = None

    async def complete_json_array_with_usage(
        self,
        prompt: str,
        *,
        agent_name: str,
        model: str,
        temperature: float,
        item_schema: dict[str, object],
    ) -> tuple[str, int, int, int, int]:
        _ = (prompt, agent_name, model, temperature)
        self.array_schema_calls += 1
        self.last_item_schema = item_schema
        payload = self._responses.pop(0)
        return (json.dumps(payload), 10, 10, 0, 0)

    async def complete_json_with_usage(
        self,
        prompt: str,
        *,
        agent_name: str,
        model: str,
        temperature: float,
    ) -> tuple[str, int, int, int, int]:
        _ = (prompt, agent_name, model, temperature)
        payload = self._responses.pop(0)
        return (json.dumps(payload), 10, 10, 0, 0)

    async def complete_json(
        self,
        prompt: str,
        *,
        agent_name: str,
        model: str,
        temperature: float,
    ) -> str:
        _ = (prompt, agent_name, model, temperature)
        payload = self._responses.pop(0)
        return json.dumps(payload)


def _review() -> ReviewConfig:
    return ReviewConfig(
        research_question="rq",
        review_type=ReviewType.SYSTEMATIC,
        pico={
            "population": "students",
            "intervention": "ai tutor",
            "comparison": "standard",
            "outcome": "learning",
        },
        keywords=["ai tutor"],
        domain="education",
        scope="health education",
        domain_expert=DomainExpertConfig(
            expert_role="Education evidence reviewer",
            canonical_terms=["AI tutor", "learning gain"],
            related_terms=["intelligent tutoring system"],
            excluded_terms=["clinical endpoint"],
        ),
        inclusion_criteria=["include if related"],
        exclusion_criteria=["exclude if unrelated"],
        date_range_start=2015,
        date_range_end=2026,
        target_databases=["openalex"],
    )


def test_screening_prompt_includes_domain_brief_and_terms() -> None:
    paper = CandidatePaper(title="Tutor study", authors=["A"], source_database="openalex", abstract="Test abstract")
    prompt = reviewer_a_prompt(_review(), paper, "title_abstract")
    assert "Domain brief:" in prompt
    assert "AI tutor" in prompt
    assert "clinical endpoint" in prompt


def _settings() -> SettingsConfig:
    return SettingsConfig(
        agents={
            "screening_reviewer_a": {"model": "google-gla:gemini-2.5-flash-lite", "temperature": 0.1},
            "screening_reviewer_b": {"model": "google-gla:gemini-2.5-flash-lite", "temperature": 0.3},
            "screening_adjudicator": {"model": "google-gla:gemini-2.5-pro", "temperature": 0.2},
        },
        # Match production settings.yaml (insufficient_content_min_words=0 disables
        # the stub-abstract heuristic so test papers with short abstracts reach the LLM).
        screening=ScreeningConfig(insufficient_content_min_words=0),
    )


@pytest.mark.asyncio
async def test_dual_screener_adjudicates_disagreement(tmp_path) -> None:
    paper = CandidatePaper(title="A", authors=["X"], source_database="openalex", abstract="text")
    # Reviewer A confidence must be below both thresholds (include=0.85, exclude=0.80)
    # so the fast-path does not trigger and adjudication is exercised.
    responses = [
        {"decision": "include", "confidence": 0.7, "reasoning": "A includes"},
        {"decision": "exclude", "confidence": 0.8, "reasoning": "B excludes", "exclusion_reason": "wrong_population"},
        {"decision": "include", "confidence": 0.7, "reasoning": "adjudicator include"},
    ]
    async with get_db(str(tmp_path / "screening.db")) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-screen", "topic", "hash")
        provider = LLMProvider(_settings(), repo)
        screener = DualReviewerScreener(
            repository=repo,
            provider=provider,
            review=_review(),
            settings=_settings(),
            llm_client=_ScriptedClient(responses),
        )
        final = await screener.screen_title_abstract("wf-screen", paper)
        assert final.decision == ScreeningDecisionType.INCLUDE
        cursor = await db.execute("SELECT COUNT(*) FROM screening_decisions WHERE workflow_id = ?", ("wf-screen",))
        row = await cursor.fetchone()
        assert int(row[0]) == 3
        cursor = await db.execute(
            "SELECT agreement, final_decision, adjudication_needed FROM dual_screening_results WHERE workflow_id = ?",
            ("wf-screen",),
        )
        dual_row = await cursor.fetchone()
        assert int(dual_row[0]) == 0
        assert str(dual_row[1]) == "include"
        assert int(dual_row[2]) == 1


@pytest.mark.asyncio
async def test_fulltext_exclusion_requires_reason(tmp_path) -> None:
    paper = CandidatePaper(title="B", authors=["Y"], source_database="openalex", abstract="conference abstract")
    responses = [
        {"decision": "exclude", "confidence": 0.91, "reasoning": "exclude no reason"},
        {"decision": "exclude", "confidence": 0.92, "reasoning": "exclude no reason"},
    ]
    async with get_db(str(tmp_path / "screening_fulltext.db")) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-fulltext", "topic", "hash")
        provider = LLMProvider(_settings(), repo)
        screener = DualReviewerScreener(
            repository=repo,
            provider=provider,
            review=_review(),
            settings=_settings(),
            llm_client=_ScriptedClient(responses),
        )
        final = await screener.screen_full_text("wf-fulltext", paper, "full text content")
        assert final.decision == ScreeningDecisionType.EXCLUDE
        assert final.exclusion_reason == ExclusionReason.OTHER


# ---------------------------------------------------------------------------
# Helpers shared by batch-mode tests
# ---------------------------------------------------------------------------


def _batch_settings(batch_size: int = 5) -> SettingsConfig:
    """Settings with reviewer_batch_size > 0 to activate batch mode."""
    return SettingsConfig(
        agents={
            "screening_reviewer_a": {"model": "google-gla:gemini-2.5-flash-lite", "temperature": 0.1},
            "screening_reviewer_b": {"model": "google-gla:gemini-2.5-flash-lite", "temperature": 0.3},
            "screening_adjudicator": {"model": "google-gla:gemini-2.5-pro", "temperature": 0.2},
        },
        screening=ScreeningConfig(
            reviewer_batch_size=batch_size,
            insufficient_content_min_words=0,
        ),
    )


def _paper(pid: str, title: str = "", abstract: str = "test abstract") -> CandidatePaper:
    return CandidatePaper(
        paper_id=pid,
        title=title or f"Study {pid}",
        authors=["Author, A."],
        source_database="openalex",
        abstract=abstract,
    )


def _batch_item(pid: str, decision: str, confidence: float, reason: str = "ok") -> dict:
    return {
        "paper_id": pid,
        "decision": decision,
        "confidence": confidence,
        "short_reason": reason,
        "reasoning": reason,
        "exclusion_reason": None,
    }


def test_batch_prompt_contains_explicit_allowed_ids_constraint() -> None:
    papers = [_paper("p1"), _paper("p2"), _paper("p3")]
    screener = DualReviewerScreener(
        repository=None,  # type: ignore[arg-type]
        provider=None,  # type: ignore[arg-type]
        review=_review(),
        settings=_batch_settings(batch_size=10),
        llm_client=_ScriptedClient([]),
    )
    prompt = screener._build_batch_prompt(
        papers=papers,
        stage="title_abstract",
        full_texts={},
        spec=ReviewerSpec(agent_name="screening_reviewer_a", reviewer_type=ReviewerType.REVIEWER_A),
    )
    assert "CONSTRAINT: Return decisions ONLY for the exact paper_id values listed below." in prompt
    assert "Allowed paper_ids:" in prompt
    assert "p1, p2, p3" in prompt


# ---------------------------------------------------------------------------
# Test 1: All papers pass fast-path via Reviewer A -- no Reviewer B calls
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_batch_reviewer_all_high_confidence(tmp_path) -> None:
    """3 papers, all A confidence above include threshold -> 0 Reviewer B calls."""
    papers = [_paper("p1"), _paper("p2"), _paper("p3")]
    # One batch call for Reviewer A returning 3 items; no Reviewer B calls at all.
    batch_a_response = [
        _batch_item("p1", "include", 0.95),
        _batch_item("p2", "include", 0.90),
        _batch_item("p3", "include", 0.88),
    ]
    responses: list[object] = [batch_a_response]  # only 1 LLM call expected
    async with get_db(str(tmp_path / "batch_all_conf.db")) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-batch-all", "topic", "hash")
        provider = LLMProvider(_batch_settings(batch_size=10), repo)
        screener = DualReviewerScreener(
            repository=repo,
            provider=provider,
            review=_review(),
            settings=_batch_settings(batch_size=10),
            llm_client=_ScriptedClient(responses),
        )
        results = await screener.screen_batch(
            workflow_id="wf-batch-all",
            stage="title_abstract",
            papers=papers,
        )
        assert len(results) == 3
        assert all(r.decision == ScreeningDecisionType.INCLUDE for r in results)
        # No Reviewer B rows: all went through fast-path.
        cur = await db.execute(
            "SELECT COUNT(*) FROM screening_decisions WHERE reviewer_type = 'reviewer_b'",
        )
        row = await cur.fetchone()
        assert int(row[0]) == 0
        # All dual_screening_results should show agreement=True.
        cur = await db.execute(
            "SELECT SUM(agreement) FROM dual_screening_results WHERE workflow_id = 'wf-batch-all'",
        )
        row = await cur.fetchone()
        assert int(row[0]) == 3


# ---------------------------------------------------------------------------
# Test 2: Mixed confidence -- one uncertain paper needs Reviewer B + adjudication
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_batch_reviewer_mixed_confidence(tmp_path) -> None:
    """3 papers: 2 high-conf include (A only), 1 uncertain include (A+B agree -> no adjudication)."""
    papers = [_paper("p1"), _paper("p2"), _paper("p3")]
    # A batch: p1 and p2 high-conf, p3 uncertain.
    batch_a = [
        _batch_item("p1", "include", 0.95),
        _batch_item("p2", "include", 0.91),
        _batch_item("p3", "include", 0.60),  # below include threshold -> needs B
    ]
    # B batch: only p3 is sent; B agrees -> no adjudication.
    batch_b = [
        _batch_item("p3", "include", 0.80),
    ]
    responses: list[object] = [batch_a, batch_b]
    async with get_db(str(tmp_path / "batch_mixed.db")) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-batch-mixed", "topic", "hash")
        provider = LLMProvider(_batch_settings(batch_size=10), repo)
        screener = DualReviewerScreener(
            repository=repo,
            provider=provider,
            review=_review(),
            settings=_batch_settings(batch_size=10),
            llm_client=_ScriptedClient(responses),
        )
        results = await screener.screen_batch(
            workflow_id="wf-batch-mixed",
            stage="title_abstract",
            papers=papers,
        )
        assert len(results) == 3
        assert all(r.decision == ScreeningDecisionType.INCLUDE for r in results)
        # p3 had Reviewer B: one reviewer_b row.
        cur = await db.execute(
            "SELECT COUNT(*) FROM screening_decisions WHERE reviewer_type = 'reviewer_b'",
        )
        row = await cur.fetchone()
        assert int(row[0]) == 1
        # No adjudication needed (A and B agreed on p3).
        cur = await db.execute(
            "SELECT SUM(adjudication_needed) FROM dual_screening_results WHERE workflow_id = 'wf-batch-mixed'",
        )
        row = await cur.fetchone()
        assert int(row[0]) == 0


# ---------------------------------------------------------------------------
# Test 3: Missing paper in batch response -> individual fallback call
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_batch_reviewer_missing_paper_fallback(tmp_path) -> None:
    """A returns only 2 of 3 paper_ids. Missing paper falls back to individual _run_reviewer."""
    papers = [_paper("p1"), _paper("p2"), _paper("pmissing")]
    # Batch A omits pmissing.
    batch_a_partial = [
        _batch_item("p1", "include", 0.95),
        _batch_item("p2", "include", 0.92),
    ]
    # Fallback individual call for pmissing (Reviewer A format: single dict).
    fallback_a = {
        "decision": "exclude",
        "confidence": 0.88,
        "reasoning": "out of scope",
        "exclusion_reason": "wrong_population",
    }
    responses: list[object] = [batch_a_partial, fallback_a]
    async with get_db(str(tmp_path / "batch_missing.db")) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-batch-missing", "topic", "hash")
        provider = LLMProvider(_batch_settings(batch_size=10), repo)
        screener = DualReviewerScreener(
            repository=repo,
            provider=provider,
            review=_review(),
            settings=_batch_settings(batch_size=10),
            llm_client=_ScriptedClient(responses),
        )
        results = await screener.screen_batch(
            workflow_id="wf-batch-missing",
            stage="title_abstract",
            papers=papers,
        )
        assert len(results) == 3
        decisions = {r.paper_id: r.decision for r in results}
        assert decisions["p1"] == ScreeningDecisionType.INCLUDE
        assert decisions["p2"] == ScreeningDecisionType.INCLUDE
        assert decisions["pmissing"] == ScreeningDecisionType.EXCLUDE
        # pmissing was individually screened: its row must exist in screening_decisions.
        cur = await db.execute(
            "SELECT COUNT(*) FROM screening_decisions WHERE paper_id = 'pmissing'",
        )
        row = await cur.fetchone()
        assert int(row[0]) >= 1
        # Parse coverage diagnostic should record parsed 2/3 with one fallback.
        cur = await db.execute(
            """
            SELECT COUNT(*)
            FROM decision_log
            WHERE decision_type = 'screening_batch_parse_coverage'
              AND decision = 'parsed_2_of_3'
            """
        )
        row = await cur.fetchone()
        assert int(row[0]) == 1


# ---------------------------------------------------------------------------
# Test 4: Out-of-chunk paper IDs are ignored and trigger fallback + mismatch log
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_batch_reviewer_out_of_chunk_ids_ignored(tmp_path) -> None:
    """Batch parser must ignore IDs not present in the current chunk."""
    papers = [_paper("p1"), _paper("p2"), _paper("p3")]
    batch_a_with_wrong_id = [
        _batch_item("p1", "include", 0.95),
        _batch_item("not_in_chunk", "include", 0.95),
    ]
    fallback = {"decision": "include", "confidence": 0.9, "reasoning": "fallback include"}
    responses: list[object] = [batch_a_with_wrong_id, fallback, fallback]
    async with get_db(str(tmp_path / "batch_out_of_chunk.db")) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-batch-out-of-chunk", "topic", "hash")
        provider = LLMProvider(_batch_settings(batch_size=10), repo)
        screener = DualReviewerScreener(
            repository=repo,
            provider=provider,
            review=_review(),
            settings=_batch_settings(batch_size=10),
            llm_client=_ScriptedClient(responses),
        )
        results = await screener.screen_batch(
            workflow_id="wf-batch-out-of-chunk",
            stage="title_abstract",
            papers=papers,
        )
        assert len(results) == 3
        assert {r.paper_id for r in results} == {"p1", "p2", "p3"}
        # p2 and p3 should have fallen back to individual reviewer calls.
        cur = await db.execute(
            """
            SELECT COUNT(*)
            FROM decision_log
            WHERE decision_type = 'screening_batch_parse_coverage'
              AND decision = 'parsed_1_of_3'
            """
        )
        row = await cur.fetchone()
        assert int(row[0]) == 1
        cur = await db.execute(
            """
            SELECT COUNT(*)
            FROM decision_log
            WHERE decision_type = 'screening_batch_id_mismatch'
              AND decision = 'ignored_1_out_of_chunk_ids'
            """
        )
        row = await cur.fetchone()
        assert int(row[0]) == 1


# ---------------------------------------------------------------------------
# Test 5: JSON parse failure -> all papers fall back to individual calls
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_batch_reviewer_json_parse_failure_fallback(tmp_path) -> None:
    """If batch A response is malformed JSON, all 3 papers fall back to individual calls."""
    papers = [_paper("p1"), _paper("p2"), _paper("p3")]
    # First response is garbage; then 3 individual fallback responses follow.
    individual = {"decision": "include", "confidence": 0.90, "reasoning": "fallback ok"}
    responses: list[object] = [
        "this is not json at all",  # batch A fails -> 3 individual fallbacks
        individual,
        individual,
        individual,
    ]
    async with get_db(str(tmp_path / "batch_parse_fail.db")) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-batch-parse", "topic", "hash")
        provider = LLMProvider(_batch_settings(batch_size=10), repo)
        screener = DualReviewerScreener(
            repository=repo,
            provider=provider,
            review=_review(),
            settings=_batch_settings(batch_size=10),
            llm_client=_ScriptedClient(responses),
        )
        results = await screener.screen_batch(
            workflow_id="wf-batch-parse",
            stage="title_abstract",
            papers=papers,
        )
        # All 3 papers must still get a decision (via individual fallback).
        assert len(results) == 3
        assert all(r.decision == ScreeningDecisionType.INCLUDE for r in results)


# ---------------------------------------------------------------------------
# Test 6: Multiple chunks -- 7 papers with batch_size=3 -> ceil(7/3)=3 batch calls for A
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_batch_reviewer_multiple_chunks(tmp_path) -> None:
    """7 papers, batch_size=3 -> 3 A-batch calls (3+3+1). All high-conf -> no B calls."""
    papers = [_paper(f"p{i}") for i in range(1, 8)]
    # 3 chunks: [p1,p2,p3], [p4,p5,p6], [p7]
    chunk1 = [_batch_item(f"p{i}", "include", 0.95) for i in range(1, 4)]
    chunk2 = [_batch_item(f"p{i}", "include", 0.90) for i in range(4, 7)]
    chunk3 = [_batch_item("p7", "include", 0.88)]
    responses: list[object] = [chunk1, chunk2, chunk3]
    async with get_db(str(tmp_path / "batch_chunks.db")) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-batch-chunks", "topic", "hash")
        provider = LLMProvider(_batch_settings(batch_size=3), repo)
        screener = DualReviewerScreener(
            repository=repo,
            provider=provider,
            review=_review(),
            settings=_batch_settings(batch_size=3),
            llm_client=_ScriptedClient(responses),
        )
        results = await screener.screen_batch(
            workflow_id="wf-batch-chunks",
            stage="title_abstract",
            papers=papers,
        )
        assert len(results) == 7
        assert all(r.decision == ScreeningDecisionType.INCLUDE for r in results)
        # All 3 responses should have been consumed (scripted client is now empty).
        assert len(screener.llm_client._responses) == 0  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Test 7: reviewer_batch_size=0 -> per-paper mode, same DB rows as existing tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_batch_reviewer_disabled_when_zero(tmp_path) -> None:
    """reviewer_batch_size=0 -> existing per-paper path; screener produces identical DB rows."""
    paper = _paper("p1", abstract="relevant study")
    # Per-paper: Reviewer A high-conf include -> fast-path, 1 LLM call only.
    responses = [
        {"decision": "include", "confidence": 0.92, "reasoning": "relevant"},
    ]
    async with get_db(str(tmp_path / "batch_disabled.db")) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-batch-zero", "topic", "hash")
        provider = LLMProvider(_settings(), repo)
        screener = DualReviewerScreener(
            repository=repo,
            provider=provider,
            review=_review(),
            settings=_settings(),  # reviewer_batch_size=0 by default
            llm_client=_ScriptedClient(responses),
        )
        results = await screener.screen_batch(
            workflow_id="wf-batch-zero",
            stage="title_abstract",
            papers=[paper],
        )
        assert len(results) == 1
        assert results[0].decision == ScreeningDecisionType.INCLUDE
        cur = await db.execute("SELECT COUNT(*) FROM dual_screening_results WHERE workflow_id = 'wf-batch-zero'")
        row = await cur.fetchone()
        assert int(row[0]) == 1


# ---------------------------------------------------------------------------
# Test 8: on_progress fires exactly once per paper even in batch mode
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_batch_reviewer_progress_fires_per_paper(tmp_path) -> None:
    """on_progress callback must fire N times for N papers, even when using batch LLM calls."""
    papers = [_paper(f"p{i}") for i in range(1, 6)]  # 5 papers
    batch_a = [_batch_item(f"p{i}", "include", 0.95) for i in range(1, 6)]
    responses: list[object] = [batch_a]
    progress_calls: list[tuple[str, int, int]] = []

    async with get_db(str(tmp_path / "batch_progress.db")) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-batch-progress", "topic", "hash")
        provider = LLMProvider(_batch_settings(batch_size=10), repo)
        screener = DualReviewerScreener(
            repository=repo,
            provider=provider,
            review=_review(),
            settings=_batch_settings(batch_size=10),
            llm_client=_ScriptedClient(responses),
            on_progress=lambda phase, cur, total: progress_calls.append((phase, cur, total)),
        )
        results = await screener.screen_batch(
            workflow_id="wf-batch-progress",
            stage="title_abstract",
            papers=papers,
        )
        assert len(results) == 5
        # on_progress must have fired exactly 5 times (once per paper).
        assert len(progress_calls) == 5
        # Progress counter must be monotonically increasing.
        counters = [call[1] for call in progress_calls]
        assert counters == list(range(1, 6))
        # Total reported in every call must equal 5.
        assert all(call[2] == 5 for call in progress_calls)


@pytest.mark.asyncio
async def test_batch_reviewer_uses_array_schema_method_when_available(tmp_path) -> None:
    """Batch path should call complete_json_array_with_usage with item schema."""
    papers = [_paper("p1"), _paper("p2"), _paper("p3")]
    responses: list[object] = [
        [
            _batch_item("p1", "include", 0.95),
            _batch_item("p2", "include", 0.92),
            _batch_item("p3", "include", 0.90),
        ]
    ]
    client = _SchemaAwareBatchClient(responses)
    async with get_db(str(tmp_path / "batch_array_schema.db")) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-batch-array-schema", "topic", "hash")
        provider = LLMProvider(_batch_settings(batch_size=10), repo)
        screener = DualReviewerScreener(
            repository=repo,
            provider=provider,
            review=_review(),
            settings=_batch_settings(batch_size=10),
            llm_client=client,
        )
        results = await screener.screen_batch(
            workflow_id="wf-batch-array-schema",
            stage="title_abstract",
            papers=papers,
        )
        assert len(results) == 3
        assert client.array_schema_calls == 1
        assert client.last_item_schema is not None
        props = client.last_item_schema.get("properties", {})
        assert isinstance(props, dict)
        assert "paper_id" in props
        assert "decision" in props
        paper_id_schema = props.get("paper_id", {})
        assert isinstance(paper_id_schema, dict)
        assert paper_id_schema.get("enum") == ["p1", "p2", "p3"]


@pytest.mark.asyncio
async def test_batch_reviewer_parses_id_alias_and_missing_optional_fields(tmp_path) -> None:
    """Batch parser should tolerate id alias and missing confidence/reasoning."""
    papers = [_paper("p1"), _paper("p2")]
    # p1 uses id alias and omits confidence/reasoning; p2 uses standard fields.
    variant_batch = [
        {
            "id": "p1",
            "decision": "include",
            "score": 0.95,
            "reason": "alias id accepted",
        },
        {
            "paper_id": "p2",
            "decision": "exclude",
            "confidence": 0.9,
            "reasoning": "out of scope",
            "exclusion_reason": "wrong_population",
        },
    ]
    responses: list[object] = [variant_batch]
    async with get_db(str(tmp_path / "batch_variant_parse.db")) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-batch-variant", "topic", "hash")
        provider = LLMProvider(_batch_settings(batch_size=10), repo)
        screener = DualReviewerScreener(
            repository=repo,
            provider=provider,
            review=_review(),
            settings=_batch_settings(batch_size=10),
            llm_client=_ScriptedClient(responses),
        )
        results = await screener.screen_batch(
            workflow_id="wf-batch-variant",
            stage="title_abstract",
            papers=papers,
        )
        assert len(results) == 2
        decision_map = {r.paper_id: r.decision for r in results}
        assert decision_map["p1"] == ScreeningDecisionType.INCLUDE
        assert decision_map["p2"] == ScreeningDecisionType.EXCLUDE
        # No parse degradation entry should be emitted when both entries parse.
        cur = await db.execute(
            """
            SELECT COUNT(*)
            FROM decision_log
            WHERE decision_type = 'screening_batch_parse_coverage'
            """
        )
        row = await cur.fetchone()
        assert int(row[0]) == 0


@pytest.mark.asyncio
async def test_batch_reviewer_parses_wrapped_decisions_object(tmp_path) -> None:
    """Batch parser accepts object-wrapped responses with a decisions array."""
    papers = [_paper("p1"), _paper("p2")]
    wrapped_payload = {
        "decisions": [
            _batch_item("p1", "include", 0.93, reason="in scope"),
            _batch_item("p2", "exclude", 0.89, reason="out of scope"),
        ]
    }
    responses: list[object] = [wrapped_payload]
    async with get_db(str(tmp_path / "batch_wrapped_object.db")) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-batch-wrapped", "topic", "hash")
        provider = LLMProvider(_batch_settings(batch_size=10), repo)
        screener = DualReviewerScreener(
            repository=repo,
            provider=provider,
            review=_review(),
            settings=_batch_settings(batch_size=10),
            llm_client=_ScriptedClient(responses),
        )
        results = await screener.screen_batch(
            workflow_id="wf-batch-wrapped",
            stage="title_abstract",
            papers=papers,
        )
        assert len(results) == 2
        decision_map = {r.paper_id: r.decision for r in results}
        assert decision_map["p1"] == ScreeningDecisionType.INCLUDE
        assert decision_map["p2"] == ScreeningDecisionType.EXCLUDE
        cur = await db.execute(
            """
            SELECT COUNT(*)
            FROM decision_log
            WHERE decision_type = 'screening_batch_parse_coverage'
            """
        )
        row = await cur.fetchone()
        assert int(row[0]) == 0


@pytest.mark.asyncio
async def test_batch_reviewer_maps_index_style_ids_to_chunk_members(tmp_path) -> None:
    """Batch parser maps index aliases like [1]/index_2 back to paper ids."""
    papers = [_paper("p1"), _paper("p2")]
    # Simulates model drift that references chunk positions instead of paper ids.
    index_alias_batch = [
        {
            "id": "[1]",
            "decision": "include",
            "confidence": 0.93,
            "reasoning": "first item relevant",
        },
        {
            "id": "index_2",
            "decision": "exclude",
            "confidence": 0.89,
            "reasoning": "second item out of scope",
            "exclusion_reason": "wrong_population",
        },
    ]
    responses: list[object] = [index_alias_batch]
    async with get_db(str(tmp_path / "batch_index_alias.db")) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-batch-index-alias", "topic", "hash")
        provider = LLMProvider(_batch_settings(batch_size=10), repo)
        screener = DualReviewerScreener(
            repository=repo,
            provider=provider,
            review=_review(),
            settings=_batch_settings(batch_size=10),
            llm_client=_ScriptedClient(responses),
        )
        results = await screener.screen_batch(
            workflow_id="wf-batch-index-alias",
            stage="title_abstract",
            papers=papers,
        )
        assert len(results) == 2
        decision_map = {r.paper_id: r.decision for r in results}
        assert decision_map["p1"] == ScreeningDecisionType.INCLUDE
        assert decision_map["p2"] == ScreeningDecisionType.EXCLUDE

        cur = await db.execute(
            """
            SELECT COUNT(*)
            FROM decision_log
            WHERE decision_type = 'screening_batch_parse_coverage'
            """
        )
        row = await cur.fetchone()
        assert int(row[0]) == 0
