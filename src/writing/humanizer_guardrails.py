"""Deterministic text guardrails for safer humanization.

This module applies light, rule-based cleanup before/after LLM humanization.
Rules are intentionally conservative:
- Never touch citation keys in square brackets.
- Never mutate numeric/statistical tokens.
- Focus on repeated boilerplate and filler transitions.
"""

from __future__ import annotations

import re
from collections import Counter

_BRACKET_BLOCK_RE = re.compile(r"(\[[^\]]*\])")
_MULTISPACE_RE = re.compile(r"[ \t]{2,}")
_SPACE_BEFORE_PUNCT_RE = re.compile(r"\s+([,.;:!?])")
_NUMERIC_TOKEN_RE = re.compile(r"\b(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:%|mmHg|kg/m2|g/dL|mg/dL|mm|mIU/L)?\b")

# Generic filler patterns observed repeatedly in high-AI reports.
_FILLER_REPLACEMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bIt is important to note that\b,?\s*", re.IGNORECASE), ""),
    (re.compile(r"\bIt is worth noting that\b,?\s*", re.IGNORECASE), ""),
    (re.compile(r"\bIt should be noted that\b,?\s*", re.IGNORECASE), ""),
    (re.compile(r"\bThe findings indicate that\b,?\s*", re.IGNORECASE), ""),
    (re.compile(r"\bThe results indicate that\b,?\s*", re.IGNORECASE), ""),
    (re.compile(r"\bThis suggests that\b,?\s*", re.IGNORECASE), ""),
    (re.compile(r"\bIn conclusion,\s*", re.IGNORECASE), ""),
    (re.compile(r"\bOverall,\s*", re.IGNORECASE), ""),
)

# Keep category labels stable for CLI and tests.
TOP5_HEURISTIC_CATEGORIES: tuple[str, ...] = (
    "boilerplate_transition_overuse",
    "repetitive_sentence_openings",
    "inflated_hedging_filler",
    "redundant_policy_conclusion_templates",
    "unnatural_lexical_repetition",
)


def extract_numeric_tokens(text: str) -> list[str]:
    """Return numeric/statistical tokens in stable order."""
    return _NUMERIC_TOKEN_RE.findall(text)


def extract_citation_blocks(text: str) -> list[str]:
    """Return bracket blocks (citation keys and other bracketed refs)."""
    return _BRACKET_BLOCK_RE.findall(text)


def _clean_prose_chunk(chunk: str) -> str:
    """Apply conservative cleanup to prose chunks outside bracket blocks."""
    out = chunk
    for pattern, replacement in _FILLER_REPLACEMENTS:
        out = pattern.sub(replacement, out)

    # Remove obvious repeated bigrams/trigrams in the same sentence.
    # Example: "staggering rise ... staggering rise" -> single occurrence.
    out = re.sub(
        r"\b([A-Za-z]{3,}(?:\s+[A-Za-z]{3,}){1,3})\b(?:\s+[\w,.-]+){0,6}\s+\1\b",
        r"\1",
        out,
        flags=re.IGNORECASE,
    )

    out = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", out)
    out = _MULTISPACE_RE.sub(" ", out)
    return out


def apply_deterministic_guardrails(text: str) -> str:
    """Apply generic phrase-level guardrails without changing citations/numerics."""
    numeric_before = Counter(extract_numeric_tokens(text))
    citations_before = extract_citation_blocks(text)

    parts = _BRACKET_BLOCK_RE.split(text)
    rebuilt: list[str] = []
    for idx, part in enumerate(parts):
        if idx % 2 == 1:
            rebuilt.append(part)
        else:
            rebuilt.append(_clean_prose_chunk(part))
    out = "".join(rebuilt)
    out = _MULTISPACE_RE.sub(" ", out)

    # If deterministic pass changes protected content, revert.
    if Counter(extract_numeric_tokens(out)) != numeric_before:
        return text
    if extract_citation_blocks(out) != citations_before:
        return text
    return out


def count_guardrail_phrases(text: str) -> dict[str, int]:
    """Count recurring AI-like scaffolding phrases for diagnostics."""
    return {
        "filler_phrases": sum(len(pattern.findall(text)) for pattern, _ in _FILLER_REPLACEMENTS),
        "repeated_ngrams": len(
            re.findall(
                r"\b([A-Za-z]{3,}(?:\s+[A-Za-z]{3,}){1,3})\b(?:\s+[\w,.-]+){0,6}\s+\1\b",
                text,
                flags=re.IGNORECASE,
            )
        ),
    }
