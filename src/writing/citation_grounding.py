"""Post-draft citation grounding verification.

The normal writing path should keep citekeys in structured citation fields,
not inline prose. This module therefore serves two roles:
1. Verify rendered manuscript text against the known citation catalog.
2. Provide narrow legacy cleanup helpers for older text-first drafts.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# Canonical bracket parser shared by writing, validation, and export checks.
_BRACKET_BLOCK_RE = re.compile(r"\[([^\[\]\n]{1,120})\]")

# Accepted citation token patterns in brackets:
# - canonical AuthorYear keys: [Smith2023], [DeVries2021a]
# - placeholder fallback keys: [Ref141], [Paper_ab12cd]
_CITEKEY_RE = re.compile(r"\[((?:[A-Za-z][A-Za-z0-9_\-']+\d{4}[a-z]?|Ref\d+|Paper_[A-Za-z0-9_\-]+))\]")
_NUMERIC_CITATION_RE = re.compile(r"^\d+$")
_PLACEHOLDER_CITEKEY_RE = re.compile(r"^(Ref\d+|Paper_[A-Za-z0-9_\-]+)$")
_UUID_LIKE_BRACKET_RE = re.compile(r"\[(?:[0-9a-f]{7,}(?:-[0-9a-f]{2,})+)\]", re.IGNORECASE)
_TEMPLATE_BRACKET_RE = re.compile(
    r"\[(?:INTERVENTION|OUTCOME|OUTCOME MEASURE|POPULATION|COMPARATOR)\]",
    re.IGNORECASE,
)


def extract_bracket_blocks(text: str) -> list[str]:
    """Return bracket contents in stable order without classifying them."""
    return list(dict.fromkeys(_BRACKET_BLOCK_RE.findall(str(text or ""))))


def extract_used_citekeys(text: str) -> list[str]:
    """Extract all citekeys in [AuthorYear] format used in a text."""
    return list(dict.fromkeys(_CITEKEY_RE.findall(text)))


def extract_numeric_citation_refs(text: str) -> list[str]:
    """Extract numeric bracket citations like [1] in stable order."""
    return [
        token
        for token in extract_bracket_blocks(text)
        if _NUMERIC_CITATION_RE.fullmatch(token.strip())
    ]


def extract_and_strip_inline_citekeys(text: str) -> tuple[str, list[str]]:
    """Remove inline citekey tokens from prose and return the extracted keys.

    Structured section drafts should carry citekeys in ``block.citations`` rather
    than embedding ``[AuthorYear]`` tokens directly inside block text. This helper
    normalizes prose back to citation-free text while exposing contract violations
    to the caller.
    """
    raw = str(text or "")
    extracted = extract_used_citekeys(raw)
    cleaned = _CITEKEY_RE.sub("", raw)
    cleaned = _UUID_LIKE_BRACKET_RE.sub("", cleaned)
    cleaned = _TEMPLATE_BRACKET_RE.sub("", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\(\s*[;,]?\s*\)", "", cleaned)
    cleaned = re.sub(r"\[\s*,\s*\]", "", cleaned)
    cleaned = re.sub(r"\s+([,.;:])", r"\1", cleaned)
    return cleaned.strip(), extracted


def verify_citation_grounding(
    section_text: str,
    valid_citekeys: list[str],
    section_name: str = "unknown",
) -> tuple[list[str], list[str]]:
    """Verify that all citekeys in section_text are in valid_citekeys.

    Returns:
        (verified_keys, hallucinated_keys) -- both as lists.
        hallucinated_keys contains citekeys present in the text but not in
        valid_citekeys. These are likely LLM hallucinations.
    """
    used = extract_used_citekeys(section_text)
    valid_set = set(valid_citekeys)
    hallucinated = [k for k in used if k not in valid_set]
    verified = [k for k in used if k in valid_set]

    if hallucinated:
        logger.warning(
            "Citation grounding: section=%s hallucinated_citekeys=%s",
            section_name,
            hallucinated,
        )

    return verified, hallucinated


def _fuzzy_match_citekey(
    unknown: str,
    valid_citekeys: list[str],
) -> str | None:
    """Attempt to match an unknown citekey to a valid one using author+year heuristics.

    Strategy:
    1. Extract the year token (last 4-digit sequence in the key).
    2. Extract the author token (alphabetic prefix before the year).
    3. Find valid citekeys whose year matches and whose author token is a
       case-insensitive substring of the valid citekey (or vice-versa).
    4. Return the best single match when confidence is high; None otherwise.
    """
    # Placeholder keys are internal/generated identifiers and do not carry
    # reliable author-year semantics for fuzzy matching.
    if _PLACEHOLDER_CITEKEY_RE.fullmatch(unknown):
        return None

    _year_m = re.search(r"(\d{4})", unknown)
    if not _year_m:
        return None
    year_str = _year_m.group(1)
    author_token = unknown[: _year_m.start()].lower()
    if len(author_token) < 2:
        return None

    # Restrict matching to year-anchored keys only.
    year_candidates = [k for k in valid_citekeys if re.search(rf"{year_str}[a-z]?$", k, flags=re.IGNORECASE)]
    if not year_candidates:
        return None

    # Strict confidence gate: require a >=4-char author prefix and a unique match.
    prefix = re.sub(r"[^a-z]", "", author_token)[:4]
    if len(prefix) < 4:
        return None
    prefix_matches = [k for k in year_candidates if re.sub(r"\d+", "", k).lower().startswith(prefix)]
    if len(prefix_matches) == 1:
        return prefix_matches[0]

    return None


def repair_hallucinated_citekeys(
    text: str,
    hallucinated: list[str],
    valid_citekeys: list[str],
) -> str:
    """Legacy safety-net for text-first drafts with unresolved citekeys.

    For each hallucinated key, attempt fuzzy matching using author+year tokens:
    - If a unique match is found in valid_citekeys, substitute it and log the repair.
    - Otherwise replace the unresolved bracket token with a visible placeholder so
      manuscript contracts can flag the degraded citation state.
    All occurrences of each hallucinated key in the text are replaced (not just the first).

    Normal section generation should not depend on this function.
    """
    result = text
    if hallucinated:
        for key in hallucinated:
            matched = _fuzzy_match_citekey(key, valid_citekeys)
            replacement = f"[{matched}]" if matched else "(citation unavailable)"
            if matched:
                logger.info(
                    "Fuzzy-matched hallucinated citekey [%s] -> [%s]",
                    key,
                    matched,
                )
            else:
                logger.warning("Unresolved hallucinated citekey [%s] replaced with visible placeholder", key)
            result = re.sub(re.escape(f"[{key}]"), replacement, result)

    # Cleanup punctuation/spacing artifacts after dropping unresolved tokens
    # and after removing known non-citation bracket artifacts.
    result = _UUID_LIKE_BRACKET_RE.sub("", result)
    result = _TEMPLATE_BRACKET_RE.sub("", result)
    result = re.sub(r"[ \t]{2,}", " ", result)
    result = re.sub(r"\(\s*[;,]?\s*\)", "", result)
    result = re.sub(r"\[\s*,\s*\]", "", result)
    result = re.sub(r"\s+([,.;:])", r"\1", result)
    return result
