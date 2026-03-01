"""Token-aware chunking of ExtractionRecord content for embedding.

Splits paper text into overlapping chunks of ~512 words with 64-word
overlap so that each chunk fits comfortably within the embedding context
window while preserving sentence-boundary continuity.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.models import ExtractionRecord


CHUNK_SIZE_WORDS = 512
OVERLAP_WORDS = 64


@dataclass
class TextChunk:
    """A single chunk produced from an ExtractionRecord."""

    chunk_id: str
    paper_id: str
    chunk_index: int
    content: str


def _split_words(text: str) -> list[str]:
    return re.findall(r"\S+", text)


def _build_chunk_text(record: ExtractionRecord) -> str:
    """Assemble all informative fields of an ExtractionRecord into one text block."""
    parts: list[str] = []
    if record.intervention_description:
        parts.append(f"Intervention: {record.intervention_description}")
    if record.comparator_description:
        parts.append(f"Comparator: {record.comparator_description}")
    if record.participant_demographics:
        parts.append(f"Population: {record.participant_demographics}")
    if record.setting:
        parts.append(f"Setting: {record.setting}")
    summary = record.results_summary.get("summary", "")
    if summary:
        parts.append(f"Results: {summary}")
    for outcome in record.outcomes:
        name = outcome.get("name", "")
        desc = outcome.get("description", "")
        effect = outcome.get("effect_size", "")
        if name:
            entry = f"Outcome: {name}"
            if desc:
                entry += f" -- {desc}"
            if effect:
                entry += f" (effect: {effect})"
            parts.append(entry)
    return "\n".join(parts)


def chunk_extraction_record(record: ExtractionRecord) -> list[TextChunk]:
    """Split one ExtractionRecord into overlapping word-window chunks.

    Returns an empty list if there is no informative text to chunk.
    """
    text = _build_chunk_text(record)
    if not text.strip():
        return []

    words = _split_words(text)
    if not words:
        return []

    chunks: list[TextChunk] = []
    start = 0
    idx = 0
    while start < len(words):
        end = min(start + CHUNK_SIZE_WORDS, len(words))
        chunk_words = words[start:end]
        content = " ".join(chunk_words)
        chunk_id = f"{record.paper_id}_{idx}"
        chunks.append(
            TextChunk(
                chunk_id=chunk_id,
                paper_id=record.paper_id,
                chunk_index=idx,
                content=content,
            )
        )
        if end >= len(words):
            break
        start = end - OVERLAP_WORDS
        idx += 1

    return chunks
