from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.llm.jev_client import JevAskResult
from src.models import SettingsConfig
from src.models.config import JevConfig
from src.rag import jev_rerank, reranker
from src.rag.retriever import RetrievedChunk

_MODEL = "google:gemini-2.5-flash-lite"


def _chunks(n: int = 3) -> list[RetrievedChunk]:
    return [
        RetrievedChunk(
            chunk_id=f"c{i}",
            paper_id=f"p{i}",
            chunk_index=i,
            content=f"chunk text {i}\nwith newline",
            score=0.5,
        )
        for i in range(n)
    ]


def _patch_jev_settings(monkeypatch: pytest.MonkeyPatch, mode: str) -> None:
    cfg = SettingsConfig(agents={}, jev=JevConfig(enabled=(mode != "off"), rag_rerank=mode))
    monkeypatch.setattr("src.config.loader.load_configs", lambda settings_path="config/settings.yaml": (None, cfg))
    monkeypatch.setattr(reranker, "jev_mode", lambda settings, surface: mode)


class _StubChatClient:
    def __init__(self, response: str | Exception) -> None:
        self.response = response
        self.prompts: list[str] = []

    async def complete_with_usage(
        self,
        prompt: str,
        *,
        model: str,
        temperature: float = 0.0,
    ) -> tuple[str, int, int, int, int]:
        _ = (model, temperature)
        self.prompts.append(prompt)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response, 120, 18, 0, 0


@pytest.mark.asyncio
async def test_rerank_chunks_short_circuits_empty_or_singleton(monkeypatch: pytest.MonkeyPatch) -> None:
    def _unexpected_client() -> None:
        raise AssertionError("get_chat_client should not be called for <= 1 chunk")

    monkeypatch.setattr(reranker, "get_chat_client", _unexpected_client)

    assert await reranker.rerank_chunks("test query", [], top_k=5, model=_MODEL) == []
    single = _chunks(1)
    assert await reranker.rerank_chunks("test query", single, top_k=5, model=_MODEL) == single


@pytest.mark.asyncio
async def test_llm_rerank_parses_wrapped_json_deduplicates_and_backfills_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Response includes prose, out-of-range/non-int entries, duplicate index 2, and omits index 1.
    client = _StubChatClient('Ranking result:\n[2, "bad", 99, -1, 2, 0]\nDone.')
    monkeypatch.setattr(reranker, "get_chat_client", lambda: client)

    ranked = await reranker.rerank_chunks(
        "clinical outcome query",
        _chunks(3),
        top_k=3,
        model=_MODEL,
        repository=None,
        workflow_id="",
    )

    assert [c.chunk_id for c in ranked] == ["c2", "c0", "c1"]
    assert [c.score for c in ranked] == [pytest.approx(1.0), pytest.approx(0.95), pytest.approx(0.90)]
    assert len(client.prompts) == 1
    assert "\nwith newline" not in client.prompts[0].split("Below are")[1]


@pytest.mark.asyncio
async def test_llm_rerank_logs_cost_record_when_repository_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _StubChatClient("[1, 0]")
    monkeypatch.setattr(reranker, "get_chat_client", lambda: client)
    _patch_jev_settings(monkeypatch, "off")

    repo = AsyncMock()
    ranked = await reranker.rerank_chunks(
        "query",
        _chunks(2),
        top_k=1,
        model=_MODEL,
        repository=repo,
        workflow_id="wf-cost",
    )

    assert [c.chunk_id for c in ranked] == ["c1"]
    assert ranked[0].score == pytest.approx(1.0)
    repo.save_cost_record.assert_awaited_once()
    record = repo.save_cost_record.await_args.args[0]
    assert record.workflow_id == "wf-cost"
    assert record.phase == "phase_6_rerank"
    assert record.tokens_in == 120
    assert record.tokens_out == 18


@pytest.mark.asyncio
async def test_llm_rerank_failure_falls_back_to_original_order_and_records_fallback_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _StubChatClient("no array in this output")
    monkeypatch.setattr(reranker, "get_chat_client", lambda: client)
    _patch_jev_settings(monkeypatch, "off")

    repo = AsyncMock()
    ranked = await reranker.rerank_chunks(
        "query",
        _chunks(3),
        top_k=2,
        model=_MODEL,
        repository=repo,
        workflow_id="wf-fallback",
    )

    assert [c.chunk_id for c in ranked] == ["c0", "c1"]
    assert [c.score for c in ranked] == [0.5, 0.5]
    repo.save_fallback_event.assert_awaited_once()
    event = repo.save_fallback_event.await_args.args[0]
    assert event.workflow_id == "wf-fallback"
    assert event.phase == "phase_6_rerank"
    assert event.module == "rag.reranker"
    assert event.fallback_type == "rrf_order"
    assert "No JSON array found" in event.reason


@pytest.mark.asyncio
async def test_rerank_chunks_live_jev_mode_uses_jev_and_falls_back_when_jev_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_jev_settings(monkeypatch, "live")

    jev_result = [RetrievedChunk(chunk_id="c1", paper_id="p1", chunk_index=1, content="best", score=1.0)]
    jev_mock = AsyncMock(return_value=jev_result)
    monkeypatch.setattr(jev_rerank, "jev_rerank_chunks", jev_mock)

    repo = AsyncMock()
    out = await reranker.rerank_chunks("query", _chunks(2), top_k=1, repository=repo, workflow_id="wf-jev-live")
    assert out == jev_result
    jev_mock.assert_awaited_once()

    # When Jev returns None, rerank_chunks must fall back to the LLM reranker.
    jev_mock.reset_mock()
    jev_mock.return_value = None
    client = _StubChatClient("[1, 0]")
    monkeypatch.setattr(reranker, "get_chat_client", lambda: client)

    fallback_out = await reranker.rerank_chunks(
        "query", _chunks(2), top_k=1, repository=repo, workflow_id="wf-jev-live"
    )
    assert [c.chunk_id for c in fallback_out] == ["c1"]
    assert len(client.prompts) == 1


@pytest.mark.asyncio
async def test_rerank_chunks_shadow_mode_runs_llm_and_records_shadow_when_key_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_jev_settings(monkeypatch, "shadow")
    monkeypatch.setattr(reranker, "jev_key_available", lambda: True)

    client = _StubChatClient("[1, 0]")
    monkeypatch.setattr(reranker, "get_chat_client", lambda: client)

    shadow_scores = jev_rerank.JevChunkScores(
        chunk_ids=["c0", "c1"],
        scores=[4.0, 1.0],
        result=JevAskResult(answers={"c_0": {"score": 4.0}, "c_1": {"score": 1.0}}, model="jev-test"),
    )
    score_mock = AsyncMock(return_value=shadow_scores)
    record_mock = AsyncMock()
    monkeypatch.setattr(jev_rerank, "jev_score_chunks", score_mock)
    monkeypatch.setattr(jev_rerank, "record_rerank_shadow", record_mock)

    repo = AsyncMock()
    out = await reranker.rerank_chunks("query", _chunks(2), top_k=2, repository=repo, workflow_id="wf-shadow")

    assert [c.chunk_id for c in out] == ["c1", "c0"]
    score_mock.assert_awaited_once()
    record_mock.assert_awaited_once()
    kwargs = record_mock.await_args.kwargs
    assert kwargs["input_ids"] == ["c0", "c1"]
    assert kwargs["llm_top_ids"] == ["c1", "c0"]
    assert kwargs["top_k"] == 2

    # When jev_key_available() is False, shadow mode downgrades to "off".
    score_mock.reset_mock()
    record_mock.reset_mock()
    monkeypatch.setattr(reranker, "jev_key_available", lambda: False)
    out_no_key = await reranker.rerank_chunks("query", _chunks(2), top_k=2, repository=repo, workflow_id="wf-shadow")
    assert [c.chunk_id for c in out_no_key] == ["c1", "c0"]
    score_mock.assert_not_awaited()
    record_mock.assert_not_awaited()
