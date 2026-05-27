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

from src.writing.citation_grounding import extract_bracket_blocks

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

# Conservative substitutions for recurring AI-assistant wording (meaning preserved).
_AI_LEXICON_REPLACEMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bdelve into\b", re.IGNORECASE), "examine"),
    (re.compile(r"\bdelving into\b", re.IGNORECASE), "examining"),
    (re.compile(r"\btapestry of\b", re.IGNORECASE), "range of"),
    (re.compile(r"\bunderscores the importance of\b", re.IGNORECASE), "emphasizes"),
    (re.compile(r"\bcrucial\b", re.IGNORECASE), "important"),
    (re.compile(r"\bpivotal\b", re.IGNORECASE), "key"),
    (re.compile(r"\bcomprehensive\b", re.IGNORECASE), "detailed"),
    (re.compile(r"\bmoreover\b", re.IGNORECASE), "and"),
    (re.compile(r"\bfurthermore\b", re.IGNORECASE), "and"),
    (re.compile(r"\bnevertheless\b", re.IGNORECASE), "but"),
    (re.compile(r"\bconsequently\b", re.IGNORECASE), "so"),
    (re.compile(r"\bleverage\b", re.IGNORECASE), "use"),
    (re.compile(r"\bfacilitate\b", re.IGNORECASE), "help"),
    (re.compile(r"\bseamless\b", re.IGNORECASE), "smooth"),
    (re.compile(r"\bholistic\b", re.IGNORECASE), "complete"),
    (re.compile(r"\butilize\b", re.IGNORECASE), "use"),
    (re.compile(r"\bnavigate\b", re.IGNORECASE), "handle"),
)

_BLACKLIST_SUBSTITUTIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bstate-of-the-art\b", re.IGNORECASE), "advanced"),
    (re.compile(r"\bcutting-edge\b", re.IGNORECASE), "advanced"),
    (re.compile(r"\bgroundbreaking\b", re.IGNORECASE), "notable"),
    (re.compile(r"\bworld-class\b", re.IGNORECASE), "high-quality"),
    (re.compile(r"\bunparalleled\b", re.IGNORECASE), "distinctive"),
    (re.compile(r"\bgame-changer\b", re.IGNORECASE), "major shift"),
    (re.compile(r"\btapestry\b", re.IGNORECASE), "range"),
    (re.compile(r"\bnexus\b", re.IGNORECASE), "connection"),
    (re.compile(r"\brevolutionary\b", re.IGNORECASE), "new"),
    (re.compile(r"\btransformative\b", re.IGNORECASE), "substantial"),
)

# ASCII hyphen-minus U+002D only; integer and decimal ranges (e.g. 1.12-1.63, 18-65).
_EN_DASH_NUMERIC_RANGE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*\u2013\s*(\d+(?:\.\d+)?)")
_SPACED_EN_DASH_RE = re.compile(r"\s+\u2013\s+")
_UNICODE_MINUS_BEFORE_DIGIT_RE = re.compile(r"\u2212(?=\d)")

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
    return [f"[{token}]" for token in extract_bracket_blocks(text)]


def _normalize_typography_dashes(chunk: str) -> str:
    """Replace Unicode dashes with ASCII-safe punctuation outside numeric edge cases.

    Order: em dash and sentence-level en dash first, numeric ranges, residual en dash,
    unicode minus adjacent to digits. Must stay ASCII-only for downstream _sanitize_prose.
    """
    out = chunk
    # Unicode minus before a digit (negative numbers, CI bounds).
    out = _UNICODE_MINUS_BEFORE_DIGIT_RE.sub("-", out)
    # Em dash (clause break): prefer comma-separated prose typical of IEEE manuscripts.
    out = out.replace("\u2014", ", ")
    # Numeric ranges with en dash (includes decimals such as 1.12-1.63).
    out = _EN_DASH_NUMERIC_RANGE_RE.sub(r"\1-\2", out)
    # Spaced en dash as aside (word - word): comma clause.
    out = _SPACED_EN_DASH_RE.sub(", ", out)
    # Remaining en dash (compounds): hyphen-minus.
    out = out.replace("\u2013", "-")
    # Any remaining unicode minus (non-numeric contexts).
    out = out.replace("\u2212", "-")
    # Tidy repeated commas from chained replacements.
    out = re.sub(r",\s*,+", ", ", out)
    out = _MULTISPACE_RE.sub(" ", out)
    return out


def _clean_prose_chunk(chunk: str) -> str:
    """Apply conservative cleanup to prose chunks outside bracket blocks.

    Pipeline order: typography (dashes) -> filler phrases -> AI lexicon swaps ->
    intra-sentence repetition trim -> punctuation spacing.
    """
    out = _normalize_typography_dashes(chunk)
    for pattern, replacement in _FILLER_REPLACEMENTS:
        out = pattern.sub(replacement, out)
    for pattern, replacement in _AI_LEXICON_REPLACEMENTS:
        out = pattern.sub(replacement, out)

    # Remove obvious repeated bigrams/trigrams within individual sentences.
    # Applied per-sentence to avoid catastrophic regex backtracking on long texts.
    _sentences = re.split(r"(?<=[.!?])\s+", out)
    _deduped: list[str] = []
    for _sent in _sentences:
        if len(_sent) < 400:
            _sent = re.sub(
                r"\b([A-Za-z]{3,}(?:\s+[A-Za-z]{3,}){1,2})\b(?:\s+[\w,.-]+){0,4}\s+\1\b",
                r"\1",
                _sent,
                flags=re.IGNORECASE,
            )
        _deduped.append(_sent)
    out = " ".join(_deduped)

    out = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", out)
    out = _MULTISPACE_RE.sub(" ", out)
    return out


def apply_blacklist_substitutions(text: str) -> str:
    """Replace high-signal blacklist terms conservatively."""
    out = text
    for pattern, replacement in _BLACKLIST_SUBSTITUTIONS:
        out = pattern.sub(replacement, out)
    return out


def apply_deterministic_guardrails(text: str) -> str:
    """Apply generic phrase-level guardrails without changing citations/numerics."""
    numeric_before = Counter(extract_numeric_tokens(text))
    citations_before = extract_citation_blocks(text)

    parts = re.split(r"(\[[^\]]*\])", text)
    rebuilt: list[str] = []
    for idx, part in enumerate(parts):
        if idx % 2 == 1:
            rebuilt.append(part)
        else:
            rebuilt.append(_clean_prose_chunk(part))
    out = "".join(rebuilt)
    out = apply_blacklist_substitutions(out)
    out = _MULTISPACE_RE.sub(" ", out)

    # If deterministic pass changes protected content, revert.
    if Counter(extract_numeric_tokens(out)) != numeric_before:
        return text
    if extract_citation_blocks(out) != citations_before:
        return text
    return out


def count_unicode_dash_markers(text: str) -> int:
    """Count em/en dash and unicode minus occurrences (diagnostic; lower is better)."""
    return sum(text.count(ch) for ch in ("\u2014", "\u2013", "\u2212"))


def count_guardrail_phrases(text: str) -> dict[str, int]:
    """Count recurring AI-like scaffolding phrases for diagnostics."""
    return {
        "filler_phrases": sum(len(pattern.findall(text)) for pattern, _ in _FILLER_REPLACEMENTS),
        "ai_lexicon_hits": sum(len(pattern.findall(text)) for pattern, _ in _AI_LEXICON_REPLACEMENTS),
        "unicode_dash_markers": count_unicode_dash_markers(text),
        "repeated_ngrams": sum(
            len(
                re.findall(
                    r"\b([A-Za-z]{3,}(?:\s+[A-Za-z]{3,}){1,2})\b(?:\s+[\w,.-]+){0,4}\s+\1\b",
                    sent,
                    flags=re.IGNORECASE,
                )
            )
            for sent in re.split(r"(?<=[.!?])\s+", text)
            if len(sent) < 400
        ),
    }
