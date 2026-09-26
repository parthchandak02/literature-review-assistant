from __future__ import annotations

import json

import pytest

from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.extraction import jev_study_design
from src.extraction import study_classifier as study_classifier_module
from src.extraction.study_classifier import StudyClassifier
from src.llm.jev_client import JevAskResult
from src.llm.provider import LLMProvider
from src.models import CandidatePaper, SettingsConfig, StudyDesign
from src.models.config import JevConfig
from src.rag import jev_rerank
from src.rag.retriever import RetrievedChunk
from src.screening import batch_ranker as batch_ranker_module
from src.screening import jev_batch_ranker
from src.screening.batch_ranker import BatchLLMRanker
from tests.unit.test_batch_ranker import _envelope, _make_paper, _screening_config, _ScriptedBatchClient
from tests.unit.test_study_classifier import _review, _StubLLMClient


def _result(answers: dict, latency_ms: int = 90) -> JevAskResult:
    return JevAskResult(
        answers=answers, model="jev-1.13.0", usage={"input_tokens": 50, "output_tokens": 5}, latency_ms=latency_ms
    )


async def _jev_rows(db) -> list[tuple]:
    cur = await db.execute("SELECT surface, paper_id, choice, routed, details_json FROM jev_decisions ORDER BY id")
    return [tuple(r) for r in await cur.fetchall()]


@pytest.mark.asyncio
async def test_batch_pre_rank_shadow_returns_llm_scores(tmp_path, monkeypatch) -> None:
    async def _ask(**kwargs: object) -> JevAskResult:
        n = len(kwargs["questions"])  # type: ignore[arg-type]
        return _result({f"p_{i}": {"score": 0.0} for i in range(n)})

    monkeypatch.setattr(jev_batch_ranker, "ask_jev", _ask)
    monkeypatch.setattr(batch_ranker_module, "jev_key_available", lambda: True)
    settings = SettingsConfig(
        agents={"batch_screener": {"model": "google:gemini-test", "temperature": 0.1}},
        jev=JevConfig(batch_pre_rank="shadow"),
    )
    papers = [_make_paper("p1"), _make_paper("p2")]
    async with get_db(str(tmp_path / "rank.db")) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf", "topic", "hash")
        ranker = BatchLLMRanker(
            screening=_screening_config(threshold=0.5),
            model="google:gemini-test",
            temperature=0.1,
            research_question="rq",
            client=_ScriptedBatchClient(
                [_envelope([{"id": "p1", "score": 0.9, "reason": "r"}, {"id": "p2", "score": 0.8, "reason": "r"}])]
            ),
            provider=LLMProvider(settings, repo),
            workflow_id="wf",
        )
        scores = await ranker._score_batch(papers)
        assert scores == {"p1": 0.9, "p2": 0.8}
        rows = await _jev_rows(db)
        assert len(rows) == 1 and rows[0][0] == "batch_pre_rank" and rows[0][3] == "shadow"
        details = json.loads(rows[0][4])
        assert details["forward_agreement"] == 0.0
        assert details["jev_scores"] == {"p1": 0.0, "p2": 0.0}


@pytest.mark.asyncio
async def test_batch_pre_rank_scores_all_papers_in_chunks(monkeypatch) -> None:
    seen: list[int] = []

    async def _ask(**kwargs: object) -> JevAskResult:
        n = len(kwargs["questions"])  # type: ignore[arg-type]
        seen.append(n)
        return _result({f"p_{i}": {"score": 4.0} for i in range(n)})

    monkeypatch.setattr(jev_batch_ranker, "ask_jev", _ask)
    papers = [_make_paper(f"p{i}") for i in range(32)]
    scored = await jev_batch_ranker.jev_score_papers(
        papers=papers, research_question="rq", population="", intervention="", outcome="", jev=JevConfig()
    )
    assert sorted(seen) == [2, 15, 15]
    assert len(scored.scores) == 32 and set(scored.scores.values()) == {1.0}


@pytest.mark.asyncio
async def test_study_design_shadow_keeps_llm_design(tmp_path, monkeypatch) -> None:
    async def _ask(**kwargs: object) -> JevAskResult:
        return _result({"design": {"choice": "cohort", "confidence": 0.95}})

    monkeypatch.setattr(jev_study_design, "ask_jev", _ask)
    monkeypatch.setattr(study_classifier_module, "jev_key_available", lambda: True)
    settings = SettingsConfig(
        agents={"study_type_detection": {"model": "google:gemini-2.5-flash", "temperature": 0.2}},
        jev=JevConfig(study_design="shadow"),
    )
    async with get_db(str(tmp_path / "design.db")) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf1", "topic", "hash")
        classifier = StudyClassifier(
            provider=LLMProvider(settings, repo),
            repository=repo,
            review=_review(),
            llm_client=_StubLLMClient('{"study_design":"rct","confidence":0.92,"reasoning":"Randomized."}'),
            low_confidence_threshold=0.70,
        )
        paper = CandidatePaper(title="AI tutor trial", authors=["A"], source_database="openalex")
        assert await classifier.classify("wf1", paper) == StudyDesign.RCT
        rows = await _jev_rows(db)
        assert len(rows) == 1
        surface, _pid, choice, routed, details_json = rows[0]
        assert (surface, choice, routed) == ("study_design_classifier", "cohort", "shadow")
        assert json.loads(details_json)["llm_decision"] == "rct"
        cur = await db.execute("SELECT phase FROM cost_records WHERE phase LIKE 'jev_shadow_%'")
        assert [r[0] for r in await cur.fetchall()] == ["jev_shadow_phase_4_extraction_quality"]


@pytest.mark.asyncio
async def test_rerank_shadow_score_does_not_mutate_chunks(tmp_path, monkeypatch) -> None:
    async def _ask(**kwargs: object) -> JevAskResult:
        return _result({"c_0": {"score": 1.0}, "c_1": {"score": 4.0}})

    monkeypatch.setattr(jev_rerank, "ask_jev", _ask)
    chunks = [
        RetrievedChunk(chunk_id="a", paper_id="pa", chunk_index=0, content="x", score=0.3),
        RetrievedChunk(chunk_id="b", paper_id="pb", chunk_index=1, content="y", score=0.2),
    ]
    scored = await jev_rerank.jev_score_chunks("q", chunks, jev=JevConfig())
    assert scored.scores == [1.0, 4.0]
    assert [c.score for c in chunks] == [0.3, 0.2]
    async with get_db(str(tmp_path / "rerank.db")) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf", "topic", "hash")
        await jev_rerank.record_rerank_shadow(
            repo,
            jev=JevConfig(price_per_call_usd=0.01),
            workflow_id="wf",
            shadow=scored,
            input_ids=["a", "b"],
            llm_top_ids=["a"],
            top_k=1,
        )
        rows = await _jev_rows(db)
        details = json.loads(rows[0][4])
        assert details["jev_top_ids"] == ["b"]
        assert details["overlap_at_k"] == 0.0
        assert details["cost_usd"] == pytest.approx(0.01)
