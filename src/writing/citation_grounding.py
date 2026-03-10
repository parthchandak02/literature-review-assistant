"""Post-draft citation grounding verification.

After the LLM writes a manuscript section, this module verifies that every
citekey used in the text corresponds to a known paper in the citation catalog.
Hallucinated citekeys are flagged and logged so they can be surfaced to the
user or auto-corrected by the reconciliation pass.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# Accepted citation token patterns in brackets:
# - canonical AuthorYear keys: [Smith2023], [DeVries2021a]
# - placeholder fallback keys: [Ref141], [Paper_ab12cd]
_CITEKEY_RE = re.compile(r"\[((?:[A-Za-z][A-Za-z0-9_\-']+\d{4}[a-z]?|Ref\d+|Paper_[A-Za-z0-9_\-]+))\]")
_PLACEHOLDER_CITEKEY_RE = re.compile(r"^(Ref\d+|Paper_[A-Za-z0-9_\-]+)$")


def extract_used_citekeys(text: str) -> list[str]:
    """Extract all citekeys in [AuthorYear] format used in a text."""
    return list(dict.fromkeys(_CITEKEY_RE.findall(text)))


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

    year_candidates = [k for k in valid_citekeys if k.endswith(year_str) or year_str in k]
    if not year_candidates:
        return None

    # Try substring match on the author token portion
    for cand in year_candidates:
        cand_author = re.sub(r"\d+", "", cand).lower()
        if author_token in cand_author or cand_author in author_token:
            return cand

    # Try first 3 chars of author as prefix (handles "castelao" vs "CastelaoLopez")
    prefix = author_token[:3]
    prefix_matches = [k for k in year_candidates if re.sub(r"\d+", "", k).lower().startswith(prefix)]
    if len(prefix_matches) == 1:
        return prefix_matches[0]

    # Last resort: if only one candidate exists for the year, accept it
    # (avoids [CITATION_NEEDED] when the LLM abbreviates an author name
    # not ambiguously -- e.g. "Prev2020" -> only "PreviousSR2020" has year 2020).
    if len(year_candidates) == 1:
        return year_candidates[0]

    return None


def repair_hallucinated_citekeys(
    text: str,
    hallucinated: list[str],
    valid_citekeys: list[str],
) -> str:
    """Replace hallucinated citekeys with fuzzy-matched valid keys or safe prose.

    For each hallucinated key, attempt fuzzy matching using author+year tokens:
    - If a unique match is found in valid_citekeys, substitute it and log the repair.
    - Otherwise replace with "(citation unavailable)" to avoid unresolved
      bracket placeholders leaking into final manuscript/LaTeX output.
    All occurrences of each hallucinated key in the text are replaced (not just the first).
    """
    if not hallucinated:
        return text

    result = text
    for key in hallucinated:
        matched = _fuzzy_match_citekey(key, valid_citekeys)
        replacement = f"[{matched}]" if matched else "(citation unavailable)"
        if matched:
            logger.info(
                "Fuzzy-matched hallucinated citekey [%s] -> [%s]",
                key,
                matched,
            )
        result = re.sub(re.escape(f"[{key}]"), replacement, result)

    return result
