"""PRISMA flow disclosure checks grounded in PRISMACounts plus tolerant prose patterns."""

from __future__ import annotations

import re

from src.models.additional import PRISMACounts


def _int_word_boundary(md_text: str, n: int) -> bool:
    return re.search(rf"\b{n}\b", md_text) is not None


def _reports_sought_narrative_present(low: str) -> bool:
    """True when prose describes full-text retrieval flow without requiring one template."""
    patterns = (
        r"\breports?\s+sought\b",
        r"\bsought\s+for\s+full",
        r"full[-\s]?text\s+retrieval",
        r"reports?\s+(?:were\s+|was\s+)?(?:\w+\s+){0,3}?sought\s+for(?:\s+full[-\s]?text)?\s+retrieval",
        r"\b(?:\d+\s+)?reports?\s+for\s+full[-\s]?text\s+retrieval\b",
        r"sought\s+full[-\s]?text\s+retrieval\s+for\s+(?:the\s+remaining\s+)?\d+\s+reports?",
        r"advanced\s+to\s+full[-\s]?text\s+retrieval",
        r"forwarded\s+for\s+full[-\s]?text\s+retrieval",
    )
    return any(re.search(p, low) is not None for p in patterns)


def _not_retrieved_narrative_present(low: str) -> bool:
    return (
        re.search(r"reports?\s+(?:were\s+|was\s+)?not\s+retrieved", low) is not None
        or re.search(r"(?:reports?\s+)?could\s+not\s+be\s+retrieved", low) is not None
        or re.search(r"reports?\s+remained\s+irretrievable", low) is not None
        or re.search(r"of\s+which\s+\d+\s+could\s+not\s+be\s+retrieved", low) is not None
    )


def _methodological_prisma_gaps(low: str) -> list[str]:
    """Disclosures not represented in PRISMACounts (process and registration)."""
    missing: list[str] = []
    if (
        ("independent reviewer" not in low)
        and ("independent reviewers" not in low)
        and ("independent dual review" not in low)
        and ("two independent reviewers" not in low)
    ):
        missing.append("selection_process_independent_reviewers")
    if "protocol registration" not in low and "registered" not in low:
        missing.append("protocol_registration_disclosure")
    if "risk of bias" not in low and "rob " not in low and "robins-i" not in low:
        missing.append("risk_of_bias_disclosure")
    return missing


def _legacy_flow_prisma_gaps(md_text: str) -> list[str]:
    """Fallback flow checks when DB counts are not yet reliable (early/empty runs)."""
    low = md_text.lower()
    missing: list[str] = []
    if _reports_sought_narrative_present(low):
        pass
    else:
        missing.append("study_selection_reports_sought_sentence")
    if _not_retrieved_narrative_present(low):
        pass
    else:
        missing.append("study_selection_not_retrieved_disclosure")
    return missing


def _db_flow_prisma_gaps(md_text: str, prisma: PRISMACounts) -> list[str]:
    """Flow checks when PRISMA counts are trusted."""
    low = md_text.lower()
    missing: list[str] = []
    if prisma.reports_sought > 0:
        if not _int_word_boundary(md_text, prisma.reports_sought) and not _reports_sought_narrative_present(low):
            missing.append("study_selection_reports_sought_sentence")
    if prisma.reports_not_retrieved > 0:
        if not _int_word_boundary(md_text, prisma.reports_not_retrieved) and not _not_retrieved_narrative_present(low):
            missing.append("study_selection_not_retrieved_disclosure")
    return missing


def prisma_disclosure_gaps(
    md_text: str,
    prisma: PRISMACounts,
    *,
    use_db_flow_checks: bool,
) -> list[str]:
    """Return missing PRISMA disclosure slot ids for PRISMA_STATEMENT_MISSING aggregation."""
    gaps: list[str] = []
    low = md_text.lower()
    gaps.extend(_methodological_prisma_gaps(low))
    if use_db_flow_checks:
        gaps.extend(_db_flow_prisma_gaps(md_text, prisma))
    else:
        gaps.extend(_legacy_flow_prisma_gaps(md_text))
    return gaps


def should_use_db_prisma_flow_checks(prisma: PRISMACounts) -> bool:
    """True when repository-derived counts are coherent enough to gate prose."""
    return bool(
        prisma.arithmetic_valid
        and (
            prisma.reports_sought > 0
            or prisma.reports_not_retrieved > 0
            or prisma.records_screened > 0
        )
    )
