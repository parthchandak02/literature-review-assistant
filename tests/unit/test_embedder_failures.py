"""embed_texts retries transient failures and never returns zero vectors."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from src.rag import embedder as embedder_mod
from src.rag.embedder import embed_texts, embedding_json_is_null, is_null_embedding


@dataclass
class _Result:
    embeddings: list[list[float]]


class _FlakyEmbedder:
    def __init__(self, failures: int, vector: list[float] | None = None) -> None:
        self.failures = failures
        self.calls = 0
        self.vector = vector if vector is not None else [0.1, 0.2, 0.3]

    async def embed_documents(self, batch: list[str]) -> _Result:
        self.calls += 1
        if self.calls <= self.failures:
            raise ConnectionError("transient")
        return _Result(embeddings=[list(self.vector) for _ in batch])


def _patch(monkeypatch: pytest.MonkeyPatch, fake: object) -> None:
    monkeypatch.setattr(embedder_mod, "get_embedder", lambda _model, _dim: fake)


@pytest.mark.asyncio
async def test_transient_failure_is_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FlakyEmbedder(failures=2)
    _patch(monkeypatch, fake)
    out = await embed_texts(["a", "b"], model="m", dim=3, max_attempts=3, retry_base_delay_s=0)
    assert out == [[0.1, 0.2, 0.3], [0.1, 0.2, 0.3]]
    assert fake.calls == 3


@pytest.mark.asyncio
async def test_persistent_failure_returns_none_not_zero_vectors(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FlakyEmbedder(failures=99)
    _patch(monkeypatch, fake)
    out = await embed_texts(["a", "b", "c"], batch_size=2, model="m", dim=3, max_attempts=2, retry_base_delay_s=0)
    assert out == [None, None, None]
    assert fake.calls == 4


@pytest.mark.asyncio
async def test_zero_vector_from_provider_is_treated_as_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, _FlakyEmbedder(failures=0, vector=[0.0, 0.0, 0.0]))
    out = await embed_texts(["a"], model="m", dim=3, retry_base_delay_s=0)
    assert out == [None]


def test_null_embedding_detection() -> None:
    assert is_null_embedding(None)
    assert is_null_embedding([])
    assert is_null_embedding([0.0, 0.0])
    assert not is_null_embedding([0.0, 0.5])
    assert embedding_json_is_null("[0.0, 0.0, 0.0]")
    assert embedding_json_is_null(None)
    assert embedding_json_is_null("not json")
    assert embedding_json_is_null('{"a": 1}')
    assert not embedding_json_is_null("[0.0, 0.1]")
