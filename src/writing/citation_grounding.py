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

_CITEKEY_RE = re.compile(r"\[([A-Za-z][A-Za-z0-9_\-']+\d{4}[a-z]?)\]")


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


def repair_hallucinated_citekeys(
    text: str,
    hallucinated: list[str],
    valid_citekeys: list[str],
) -> str:
    """Replace hallucinated citekeys with a placeholder note.

    This is a conservative repair: hallucinated citekeys are replaced with
    [CITATION_NEEDED] so human reviewers can identify and correct them,
    rather than silently substituting a potentially wrong paper.
    """
    if not hallucinated:
        return text

    result = text
    for key in hallucinated:
        result = result.replace(f"[{key}]", "[CITATION_NEEDED]")

    return result
