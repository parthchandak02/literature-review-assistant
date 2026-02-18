"""PRISMA 2020 checklist validator: 27 items vs manuscript."""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class PrismaItemResult:
    """Result for one PRISMA item."""

    item_id: str
    section: str
    description: str
    status: str  # REPORTED | PARTIAL | MISSING
    rationale: str = ""


@dataclass
class PrismaValidationResult:
    """Result of PRISMA checklist validation."""

    items: list[PrismaItemResult] = field(default_factory=list)
    reported_count: int = 0
    partial_count: int = 0
    missing_count: int = 0
    passed: bool = False  # True if >= 24/27 reported


PRISMA_ITEMS = [
    ("1", "Title", "Identify report as systematic review", ["systematic review", "meta-analysis", "meta analysis"]),
    ("2a", "Abstract", "Structured abstract", ["objective", "methods", "results", "conclusion"]),
    ("2b", "Abstract", "Structured abstract", ["objective", "methods", "results", "conclusion"]),
    ("3", "Introduction", "Rationale", ["rationale", "justification", "need", "gap"]),
    ("4", "Introduction", "Objectives", ["objective", "aim", "purpose", "research question"]),
    ("5", "Methods", "Eligibility criteria", ["eligibility", "inclusion", "exclusion", "pico", "pico"]),
    ("6", "Methods", "Information sources", ["database", "search", "medline", "pubmed", "embase", "sources"]),
    ("7", "Methods", "Search strategy", ["search strategy", "search string", "boolean"]),
    ("8", "Methods", "Selection process", ["screening", "reviewer", "dual", "independent", "selection"]),
    ("9", "Methods", "Data collection", ["data extraction", "data collection", "extraction form"]),
    ("10", "Methods", "Data items", ["data items", "extracted", "outcome", "characteristics"]),
    ("11", "Methods", "Risk of bias", ["risk of bias", "rob", "quality assessment", "bias"]),
    ("12", "Methods", "Effect measures", ["effect", "smd", "odds ratio", "mean difference"]),
    ("13a", "Results", "Study selection", ["prisma", "flow", "identified", "screened", "included"]),
    ("13b", "Results", "Study characteristics", ["characteristics", "study design", "participant"]),
    ("13c", "Results", "Risk of bias", ["risk of bias", "bias", "quality"]),
    ("13d", "Results", "Results of syntheses", ["meta-analysis", "forest", "pooled", "synthesis"]),
    ("14", "Results", "Additional analyses", ["sensitivity", "subgroup", "heterogeneity"]),
    ("15", "Discussion", "Discussion", ["discussion", "finding", "interpretation"]),
    ("16", "Discussion", "Limitations", ["limitation", "strength", "weakness"]),
    ("17", "Discussion", "Interpretation", ["implication", "conclusion", "interpretation"]),
    ("18", "Other", "Funding", ["funding", "support", "grant"]),
    ("19", "Other", "Registration", ["prospero", "registration", "protocol"]),
    ("20", "Results", "Certainty of evidence", ["grade", "certainty", "evidence"]),
    ("21", "Methods", "Synthesis methods", ["meta-analysis", "narrative", "synthesis", "pooling"]),
    ("22", "Results", "Study selection count", ["identified", "screened", "included", "excluded"]),
    ("23", "Discussion", "Comparison with prior work", ["comparison", "prior", "previous", "literature"]),
    ("24", "Discussion", "Implications", ["implication", "practice", "research", "policy"]),
    ("25", "Other", "Conflict of interest", ["conflict", "competing", "interest", "disclosure"]),
    ("26", "Abstract", "Funding in abstract", ["funding", "support"]),
    ("27", "Abstract", "Registration in abstract", ["prospero", "registration", "crd"]),
]


def _check_item(text_lower: str, keywords: list[str]) -> tuple[str, str]:
    """Check if keywords appear. Returns (status, rationale)."""
    found = [k for k in keywords if k in text_lower]
    if len(found) >= 2 or (len(found) == 1 and len(keywords) <= 2):
        return "REPORTED", f"Found: {', '.join(found)}"
    if found:
        return "PARTIAL", f"Partial: {', '.join(found)}"
    return "MISSING", "Not found"


def validate_prisma(tex_content: str | None, md_content: str | None = None) -> PrismaValidationResult:
    """Validate manuscript against PRISMA 2020 checklist.

    Uses tex_content if provided, else md_content. Checks for presence of
    key terms corresponding to each of the 27 items.
    """
    text = (tex_content or md_content or "").lower()
    if not text:
        return PrismaValidationResult(
            items=[],
            reported_count=0,
            partial_count=0,
            missing_count=0,
            passed=False,
        )

    items: list[PrismaItemResult] = []
    for item_id, section, description, keywords in PRISMA_ITEMS:
        status, rationale = _check_item(text, keywords)
        items.append(
            PrismaItemResult(
                item_id=item_id,
                section=section,
                description=description,
                status=status,
                rationale=rationale,
            )
        )

    reported = sum(1 for i in items if i.status == "REPORTED")
    partial = sum(1 for i in items if i.status == "PARTIAL")
    missing = sum(1 for i in items if i.status == "MISSING")

    return PrismaValidationResult(
        items=items,
        reported_count=reported,
        partial_count=partial,
        missing_count=missing,
        passed=reported >= 24,
    )
