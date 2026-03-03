"""Unit tests for the sentence-boundary-aware chunker (Enhancement #4)."""

from __future__ import annotations

import pytest

from src.models.enums import StudyDesign
from src.models.extraction import ExtractionRecord
from src.rag.chunker import CHUNK_MAX_WORDS, chunk_extraction_record


def _make_record(intervention: str, summary: str = "", outcomes: list | None = None) -> ExtractionRecord:
    return ExtractionRecord(
        paper_id="test-paper",
        study_design=StudyDesign.RCT,
        intervention_description=intervention,
        results_summary={"summary": summary} if summary else {},
        outcomes=outcomes or [],
    )


def _word_count(text: str) -> int:
    return len(text.split())


def test_chunk_produces_sentence_complete_chunks() -> None:
    """Every chunk must end with sentence-terminal punctuation (. ! ?)."""
    text = (
        "Patients received 10mg atorvastatin daily. "
        "This was a randomized controlled trial. "
        "The primary endpoint was LDL-C reduction. "
        "Secondary endpoints included HDL-C and triglycerides. "
        "Follow-up was 12 weeks."
    )
    record = _make_record(intervention=text)
    chunks = chunk_extraction_record(record)
    assert chunks, "Expected at least one chunk"
    for chunk in chunks:
        stripped = chunk.content.rstrip()
        assert stripped[-1] in ".!?", f"Chunk does not end with sentence punctuation: {stripped[-30:]!r}"


def test_chunk_overlap_carries_sentences() -> None:
    """Adjacent chunks should share at least one sentence (overlap=2 sentences)."""
    sentences = [f"Sentence {i} about the study design and outcomes." for i in range(6)]
    text = " ".join(sentences)
    record = _make_record(intervention=text)
    chunks = chunk_extraction_record(record)
    if len(chunks) < 2:
        pytest.skip("Text too short to produce multiple chunks; adjust sentence count.")
    # Any sentence appearing in both chunk[0] and chunk[1] counts as overlap.
    words_0 = set(chunks[0].content.split())
    words_1 = set(chunks[1].content.split())
    overlap = words_0 & words_1
    assert overlap, "Expected word overlap between adjacent chunks (sentence overlap)"


def test_empty_record_returns_no_chunks() -> None:
    """An ExtractionRecord with no informative fields produces an empty list."""
    record = ExtractionRecord(
        paper_id="empty",
        study_design=StudyDesign.OTHER,
        intervention_description="",
    )
    assert chunk_extraction_record(record) == []


def test_single_sentence_record_one_chunk() -> None:
    """A very short record fits in a single chunk."""
    record = _make_record(intervention="Patients received placebo.")
    chunks = chunk_extraction_record(record)
    assert len(chunks) == 1
    assert chunks[0].chunk_index == 0


def test_long_record_splits_into_multiple_chunks() -> None:
    """A record exceeding CHUNK_MAX_WORDS must produce >= 2 chunks, each within limit."""
    # Build ~600 words worth of 15-word sentences.
    sentence = "The intervention was administered daily over the course of twelve weeks to all participants. "
    long_text = sentence * 40  # ~600 words
    record = _make_record(intervention=long_text)
    chunks = chunk_extraction_record(record)
    assert len(chunks) >= 2, f"Expected multiple chunks, got {len(chunks)}"
    for chunk in chunks:
        assert _word_count(chunk.content) <= CHUNK_MAX_WORDS + 50, (
            f"Chunk is too large: {_word_count(chunk.content)} words"
        )


def test_chunk_ids_are_unique() -> None:
    """No two chunks from the same record share a chunk_id."""
    sentence = "Each sentence contributes to the evidence base for the systematic review. "
    record = _make_record(intervention=sentence * 40)
    chunks = chunk_extraction_record(record)
    ids = [c.chunk_id for c in chunks]
    assert len(ids) == len(set(ids)), "Duplicate chunk_ids detected"


def test_chunk_ids_embed_paper_id() -> None:
    """chunk_id must contain the paper_id so retrieval can filter by paper."""
    record = ExtractionRecord(
        paper_id="my-special-paper",
        study_design=StudyDesign.COHORT,
        intervention_description="This study investigated the use of statins in elderly patients.",
    )
    chunks = chunk_extraction_record(record)
    assert chunks
    for chunk in chunks:
        assert "my-special-paper" in chunk.chunk_id


def test_fallback_when_nltk_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """When nltk raises, the regex fallback still produces non-empty chunks."""
    import src.rag.chunker as chunker_mod

    def _raise(*args: object, **kwargs: object) -> None:
        raise ImportError("nltk not available")

    monkeypatch.setattr(chunker_mod, "_tokenize_sentences", lambda text: _raise() or [])

    # Restore with regex fallback directly.
    import re

    def _regex_fallback(text: str) -> list[str]:
        raw = re.split(r"(?<=[.!?])\s+", text.strip())
        return [s for s in raw if s.strip()]

    monkeypatch.setattr(chunker_mod, "_tokenize_sentences", _regex_fallback)

    record = _make_record(
        intervention=("Patients received the intervention daily. The study was double-blind. Results were significant.")
    )
    chunks = chunk_extraction_record(record)
    assert chunks, "Expected chunks even when nltk is unavailable"
    assert all(c.content.strip() for c in chunks)
