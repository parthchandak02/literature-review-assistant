"""Sentence-boundary-aware chunking of ExtractionRecord content for embedding.

Splits paper text into coherent sentence-window chunks so that no sentence
is cut mid-way. Each chunk targets ~400 tokens (measured in words) with a
2-sentence overlap between adjacent chunks to preserve context.

Falls back to the old word-window strategy if nltk is unavailable.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from src.models import ExtractionRecord

logger = logging.getLogger(__name__)

CHUNK_MAX_WORDS = 400
OVERLAP_SENTENCES = 2


@dataclass
class TextChunk:
    """A single chunk produced from an ExtractionRecord."""

    chunk_id: str
    paper_id: str
    chunk_index: int
    content: str


def _tokenize_sentences(text: str) -> list[str]:
    """Split text into sentences using nltk, with a simple fallback.

    Auto-downloads the punkt_tab tokenizer data on first use if missing.
    """
    try:
        import nltk
        from nltk.tokenize import sent_tokenize
        try:
            sentences = sent_tokenize(text)
        except LookupError:
            nltk.download("punkt_tab", quiet=True)
            nltk.download("punkt", quiet=True)
            sentences = sent_tokenize(text)
        if sentences:
            return sentences
    except Exception:
        pass
    # Fallback: split on ". ", "! ", "? " boundaries.
    raw = re.split(r"(?<=[.!?])\s+", text.strip())
    return [s for s in raw if s.strip()]


def _word_count(text: str) -> int:
    return len(re.findall(r"\S+", text))


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


def _sentence_window_chunks(
    sentences: list[str],
    paper_id: str,
    max_words: int = CHUNK_MAX_WORDS,
    overlap: int = OVERLAP_SENTENCES,
) -> list[TextChunk]:
    """Group sentences into chunks that stay under max_words, with sentence overlap."""
    chunks: list[TextChunk] = []
    idx = 0
    i = 0
    n = len(sentences)

    while i < n:
        group: list[str] = []
        word_total = 0
        j = i
        while j < n:
            wc = _word_count(sentences[j])
            # Always include at least one sentence per chunk even if it's oversized.
            if group and word_total + wc > max_words:
                break
            group.append(sentences[j])
            word_total += wc
            j += 1

        content = " ".join(group).strip()
        if content:
            chunks.append(
                TextChunk(
                    chunk_id=f"{paper_id}_{idx}",
                    paper_id=paper_id,
                    chunk_index=idx,
                    content=content,
                )
            )
            idx += 1

        # Advance by (group_size - overlap) sentences, minimum 1.
        advance = max(1, len(group) - overlap)
        i += advance

    return chunks


def chunk_extraction_record(record: ExtractionRecord) -> list[TextChunk]:
    """Split one ExtractionRecord into sentence-boundary-aware overlapping chunks.

    Returns an empty list if there is no informative text to chunk.
    """
    text = _build_chunk_text(record)
    if not text.strip():
        return []

    sentences = _tokenize_sentences(text)
    if not sentences:
        return []

    chunks = _sentence_window_chunks(sentences, record.paper_id)
    logger.debug(
        "chunker: paper_id=%s produced %d chunks from %d sentences",
        record.paper_id, len(chunks), len(sentences),
    )
    return chunks


def chunk_table_outcomes(
    paper_id: str,
    outcomes: list[dict[str, str]],
    start_index: int = 0,
) -> list[TextChunk]:
    """Convert vision-extracted table outcome rows into embeddable text chunks.

    Each outcome row is rendered as a short structured string so it can be
    retrieved alongside normal text chunks during RAG. Table chunks use the
    naming convention "{paper_id}_table_{idx}" to distinguish them.

    Args:
        paper_id: Paper identifier (used in chunk_id prefix).
        outcomes: List of outcome dicts as produced by merge_outcomes() /
                  extract_tables_from_pdf(). Each dict may contain: name,
                  description, effect_size, se, n, p_value, ci_lower, ci_upper.
        start_index: Chunk index offset (use len(existing_chunks) to avoid
                     collisions when appending to already-chunked records).

    Returns:
        List of TextChunk objects ready for embedding.
    """
    chunks: list[TextChunk] = []
    for idx, outcome in enumerate(outcomes):
        name = outcome.get("name", "").strip()
        if not name:
            continue
        parts: list[str] = [f"[Table outcome] {name}"]
        desc = outcome.get("description", "").strip()
        if desc:
            parts.append(f"Description: {desc}")
        effect = outcome.get("effect_size", "").strip()
        if effect:
            parts.append(f"Effect size: {effect}")
        ci_low = outcome.get("ci_lower", "").strip()
        ci_high = outcome.get("ci_upper", "").strip()
        if ci_low and ci_high:
            parts.append(f"95% CI: [{ci_low}, {ci_high}]")
        p_val = outcome.get("p_value", "").strip()
        if p_val:
            parts.append(f"p-value: {p_val}")
        n_val = outcome.get("n", "").strip()
        if n_val:
            parts.append(f"N: {n_val}")
        content = " | ".join(parts)
        chunk_idx = start_index + idx
        chunks.append(
            TextChunk(
                chunk_id=f"{paper_id}_table_{chunk_idx}",
                paper_id=paper_id,
                chunk_index=chunk_idx,
                content=content,
            )
        )
    logger.debug(
        "chunk_table_outcomes: paper_id=%s produced %d table chunks from %d outcomes",
        paper_id, len(chunks), len(outcomes),
    )
    return chunks
