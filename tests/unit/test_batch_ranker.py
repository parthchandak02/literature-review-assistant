"""Unit tests for src/screening/batch_ranker.py.

All tests use a scripted mock client -- zero real LLM calls.
Pattern mirrors _ScriptedClient in test_screening.py.
"""

from __future__ import annotations

import json

import pytest

from src.models.config import ScreeningConfig
from src.models.enums import ExclusionReason, ScreeningDecisionType
from src.models.papers import CandidatePaper, SourceCategory
from src.screening.batch_ranker import BatchLLMRanker

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _ScriptedBatchClient:
    """Returns pre-scripted JSON strings, in order, for each complete_batch call."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)

    async def complete_batch(self, prompt: str, *, model: str, temperature: float) -> str:
        _ = (prompt, model, temperature)
        return self._responses.pop(0)


class _ErrorBatchClient:
    """Raises an exception on every call (tests the graceful fallback path)."""

    async def complete_batch(self, prompt: str, *, model: str, temperature: float) -> str:
        raise RuntimeError("simulated LLM failure")


def _make_paper(paper_id: str, title: str = "", abstract: str = "test abstract") -> CandidatePaper:
    return CandidatePaper(
        paper_id=paper_id,
        title=title or f"Study {paper_id}",
        authors=["Author, A."],
        source_database="pubmed",
        source_category=SourceCategory.DATABASE,
        abstract=abstract,
    )


def _screening_config(
    *,
    threshold: float = 0.5,
    batch_size: int = 5,
    enabled: bool = True,
) -> ScreeningConfig:
    return ScreeningConfig(
        batch_screen_enabled=enabled,
        batch_screen_size=batch_size,
        batch_screen_threshold=threshold,
    )


def _make_ranker(
    papers: list[CandidatePaper],
    responses: list[str],
    threshold: float = 0.5,
    batch_size: int = 100,
) -> BatchLLMRanker:
    return BatchLLMRanker(
        screening=_screening_config(threshold=threshold, batch_size=batch_size),
        model="google-gla:gemini-test",
        temperature=0.1,
        research_question="What is the effect of the intervention on the primary outcome?",
        population="adult participants",
        intervention="structured intervention",
        outcome="primary outcome measure",
        client=_ScriptedBatchClient(responses),
    )


# ---------------------------------------------------------------------------
# Test: normal case -- mixed scores, correct split
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rank_and_split_normal_case() -> None:
    """Papers above threshold forwarded; below threshold excluded."""
    papers = [_make_paper(f"p{i}") for i in range(1, 6)]  # 5 papers

    response_items = [
        {"id": "p1", "score": 0.9, "reason": "clearly relevant"},
        {"id": "p2", "score": 0.2, "reason": "different domain, unrelated"},
        {"id": "p3", "score": 0.6, "reason": "adjacent topic"},
        {"id": "p4", "score": 0.1, "reason": "unrelated domain"},
        {"id": "p5", "score": 0.8, "reason": "direct match"},
    ]
    client = _ScriptedBatchClient([json.dumps(response_items)])
    ranker = BatchLLMRanker(
        screening=_screening_config(threshold=0.5, batch_size=10),
        model="test-model",
        temperature=0.1,
        research_question="RQ",
        population="pop",
        intervention="robot",
        outcome="accuracy",
        client=client,
    )

    forwarded, excluded = await ranker.rank_and_split(papers)

    assert len(forwarded) == 3  # p1 (0.9), p3 (0.6), p5 (0.8)
    assert len(excluded) == 2  # p2 (0.2), p4 (0.1)
    forwarded_ids = {p.paper_id for p in forwarded}
    assert forwarded_ids == {"p1", "p3", "p5"}
    excluded_ids = {d.paper_id for d in excluded}
    assert excluded_ids == {"p2", "p4"}
    for d in excluded:
        assert d.decision == ScreeningDecisionType.EXCLUDE
        assert d.exclusion_reason == ExclusionReason.BATCH_SCREENED_LOW


# ---------------------------------------------------------------------------
# Test: all papers above threshold -> all forwarded
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rank_and_split_all_above_threshold() -> None:
    """All papers score above threshold -> zero exclusions."""
    papers = [_make_paper(f"p{i}") for i in range(1, 4)]
    response_items = [
        {"id": "p1", "score": 0.9, "reason": "relevant"},
        {"id": "p2", "score": 0.7, "reason": "relevant"},
        {"id": "p3", "score": 0.6, "reason": "relevant"},
    ]
    ranker = _make_ranker(papers, [json.dumps(response_items)], threshold=0.5)
    forwarded, excluded = await ranker.rank_and_split(papers)

    assert len(forwarded) == 3
    assert len(excluded) == 0


# ---------------------------------------------------------------------------
# Test: all papers below threshold -> all excluded (no hard fail)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rank_and_split_all_below_threshold() -> None:
    """All papers score below threshold -> all excluded, no exception raised."""
    papers = [_make_paper(f"p{i}") for i in range(1, 4)]
    response_items = [
        {"id": "p1", "score": 0.1, "reason": "irrelevant"},
        {"id": "p2", "score": 0.2, "reason": "irrelevant"},
        {"id": "p3", "score": 0.3, "reason": "irrelevant"},
    ]
    ranker = _make_ranker(papers, [json.dumps(response_items)], threshold=0.5)
    forwarded, excluded = await ranker.rank_and_split(papers)

    assert len(forwarded) == 0
    assert len(excluded) == 3


# ---------------------------------------------------------------------------
# Test: LLM call failure -> safe fallback (all forwarded)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rank_and_split_llm_failure_fallback() -> None:
    """If the LLM call raises, all papers are forwarded (no silent data loss)."""
    papers = [_make_paper(f"p{i}") for i in range(1, 6)]
    ranker = BatchLLMRanker(
        screening=_screening_config(threshold=0.5, batch_size=10),
        model="test-model",
        temperature=0.1,
        research_question="RQ",
        population="pop",
        intervention="robot",
        outcome="accuracy",
        client=_ErrorBatchClient(),
    )
    forwarded, excluded = await ranker.rank_and_split(papers)

    assert len(forwarded) == 5
    assert len(excluded) == 0


# ---------------------------------------------------------------------------
# Test: JSON parse failure -> safe fallback (all forwarded)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rank_and_split_json_parse_failure_fallback() -> None:
    """If LLM returns malformed JSON, all papers are forwarded."""
    papers = [_make_paper(f"p{i}") for i in range(1, 4)]
    ranker = _make_ranker(papers, ["this is not json at all"], threshold=0.5)
    forwarded, excluded = await ranker.rank_and_split(papers)

    assert len(forwarded) == 3
    assert len(excluded) == 0


# ---------------------------------------------------------------------------
# Test: JSON in markdown fences is correctly parsed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rank_and_split_markdown_fences_stripped() -> None:
    """LLM wraps JSON in ```json ... ``` fences -- should still parse correctly."""
    papers = [_make_paper("p1"), _make_paper("p2")]
    items = [
        {"id": "p1", "score": 0.8, "reason": "good"},
        {"id": "p2", "score": 0.1, "reason": "bad"},
    ]
    fenced = "```json\n" + json.dumps(items) + "\n```"
    ranker = _make_ranker(papers, [fenced], threshold=0.5)
    forwarded, excluded = await ranker.rank_and_split(papers)

    assert len(forwarded) == 1
    assert forwarded[0].paper_id == "p1"
    assert len(excluded) == 1
    assert excluded[0].paper_id == "p2"


# ---------------------------------------------------------------------------
# Test: missing paper in response -> gets score 1.0 (safe fallback)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rank_and_split_missing_paper_gets_safe_score() -> None:
    """Paper not mentioned in LLM response is given score 1.0 and forwarded."""
    papers = [_make_paper("p1"), _make_paper("p2"), _make_paper("p3")]
    # LLM only returns p1 and p3, omits p2
    response_items = [
        {"id": "p1", "score": 0.2, "reason": "irrelevant"},
        {"id": "p3", "score": 0.9, "reason": "relevant"},
    ]
    ranker = _make_ranker(papers, [json.dumps(response_items)], threshold=0.5)
    forwarded, excluded = await ranker.rank_and_split(papers)

    forwarded_ids = {p.paper_id for p in forwarded}
    # p2 (missing) and p3 (0.9) should both be forwarded; p1 (0.2) excluded
    assert "p2" in forwarded_ids
    assert "p3" in forwarded_ids
    assert len(excluded) == 1
    assert excluded[0].paper_id == "p1"


# ---------------------------------------------------------------------------
# Test: batching -- 10 papers with batch_size=3 -> 4 LLM calls
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rank_and_split_multiple_batches() -> None:
    """10 papers, batch_size=4 -> ceil(10/4)=3 LLM calls; all responses consumed."""
    papers = [_make_paper(f"p{i}") for i in range(1, 11)]

    # Build 3 batch responses (4+4+2)
    batches = [papers[0:4], papers[4:8], papers[8:10]]
    responses = []
    for batch in batches:
        items = [{"id": p.paper_id, "score": 0.8, "reason": "ok"} for p in batch]
        responses.append(json.dumps(items))

    ranker = _make_ranker(papers, responses, threshold=0.5, batch_size=4)
    forwarded, excluded = await ranker.rank_and_split(papers)

    assert len(forwarded) == 10
    assert len(excluded) == 0


# ---------------------------------------------------------------------------
# Test: empty input
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rank_and_split_empty_input() -> None:
    """Empty paper list returns empty lists without calling the LLM."""
    ranker = _make_ranker([], [], threshold=0.5)
    forwarded, excluded = await ranker.rank_and_split([])

    assert forwarded == []
    assert excluded == []


# ---------------------------------------------------------------------------
# Test: scores exactly at threshold are forwarded (>= not >)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rank_and_split_threshold_boundary() -> None:
    """score == threshold should forward (>= comparison, not >)."""
    papers = [_make_paper("p1"), _make_paper("p2")]
    response_items = [
        {"id": "p1", "score": 0.5, "reason": "exactly at threshold"},
        {"id": "p2", "score": 0.49, "reason": "just below threshold"},
    ]
    ranker = _make_ranker(papers, [json.dumps(response_items)], threshold=0.5)
    forwarded, excluded = await ranker.rank_and_split(papers)

    assert len(forwarded) == 1
    assert forwarded[0].paper_id == "p1"
    assert len(excluded) == 1
    assert excluded[0].paper_id == "p2"
