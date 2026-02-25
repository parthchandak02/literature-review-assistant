"""Build grounding data for the writing phase from real pipeline outputs.

This module aggregates actual data (PRISMA counts, extraction records,
synthesis results) into a structured block injected into every LLM section
prompt, preventing hallucination of statistics, counts, and citation keys.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel

from src.models import CandidatePaper, ExtractionRecord
from src.models.additional import PRISMACounts


def _normalize_label(raw: str) -> str:
    """Convert snake_case or enum value strings to natural prose labels.

    Applied to every field that originates from an enum or stored identifier
    before it enters the grounding block, so the LLM never sees underscores
    in descriptive text.
    """
    return raw.replace("_", " ").strip() if raw else raw


class StudySummary(BaseModel):
    """Compact per-study summary for the writing prompt."""

    paper_id: str
    title: str
    year: Optional[int]
    study_design: str
    participant_count: Optional[int]
    key_finding: str


class WritingGroundingData(BaseModel):
    """Factual data block derived from pipeline phases 1-5.

    Injected verbatim into every LLM writing prompt so the model cannot
    hallucinate counts, statistics, or citation keys.
    """

    # Search
    databases_searched: List[str]
    other_methods_searched: List[str]
    search_date: str

    # PRISMA counts
    total_identified: int
    duplicates_removed: int
    total_screened: int
    fulltext_assessed: int
    total_included: int
    fulltext_excluded: int  # derived: fulltext_assessed - total_included
    excluded_fulltext_reasons: Dict[str, int]

    # Study characteristics
    study_design_counts: Dict[str, int]
    total_participants: Optional[int]
    year_range: Optional[str]

    # Synthesis
    meta_analysis_feasible: bool
    synthesis_direction: str
    n_studies_synthesized: int
    narrative_text: str
    key_themes: List[str]

    # Per-study summaries (for results section)
    study_summaries: List[StudySummary]

    # Citation keys (the ONLY keys the LLM is allowed to use)
    valid_citekeys: List[str]

    # Inter-rater reliability (from dual-reviewer screening phase)
    cohens_kappa: Optional[float] = None
    kappa_stage: Optional[str] = None

    # Participant count provenance
    n_studies_reporting_count: int = 0
    n_total_studies: int = 0

    # Sensitivity analysis (leave-one-out + subgroup) -- only present when meta-analysis ran
    sensitivity_results: List[str] = []


def build_writing_grounding(
    prisma_counts: PRISMACounts,
    extraction_records: List[ExtractionRecord],
    included_papers: List[CandidatePaper],
    narrative: Optional[dict],
    citation_catalog: str = "",
    cohens_kappa: Optional[float] = None,
    kappa_stage: Optional[str] = None,
    sensitivity_results: Optional[List[str]] = None,
) -> WritingGroundingData:
    """Aggregate real pipeline outputs into a WritingGroundingData instance."""

    # Bibliographic databases actually used (non-zero counts from databases_records)
    _OTHER_METHOD_NAMES = frozenset({"perplexity_web", "perplexity_search", "perplexity"})
    active_dbs = sorted(
        db
        for db, cnt in prisma_counts.databases_records.items()
        if cnt > 0 and db not in _OTHER_METHOD_NAMES
    )
    # Other methods (grey lit, AI discovery tools -- not bibliographic databases)
    active_other = sorted(
        src
        for src, cnt in prisma_counts.other_sources_records.items()
        if cnt > 0
    )
    # Any perplexity records that ended up in databases_records (should be rare)
    active_other = sorted(set(active_other) | {
        db for db in prisma_counts.databases_records
        if db in _OTHER_METHOD_NAMES and prisma_counts.databases_records.get(db, 0) > 0
    })

    # Study design breakdown -- normalize enum value to readable label at source
    design_counts: Dict[str, int] = {}
    for rec in extraction_records:
        key = _normalize_label(rec.study_design.value)
        design_counts[key] = design_counts.get(key, 0) + 1

    # Participant total (only from studies that actually reported N)
    participant_counts = [
        rec.participant_count
        for rec in extraction_records
        if rec.participant_count is not None and rec.participant_count > 0
    ]
    total_participants: Optional[int] = (
        sum(participant_counts) if participant_counts else None
    )
    n_studies_reporting_count = len(participant_counts)
    n_total_studies = len(extraction_records)

    # Year range from included papers
    years = [p.year for p in included_papers if p.year is not None]
    year_range: Optional[str] = (
        f"{min(years)}-{max(years)}" if years else None
    )

    # Synthesis direction from narrative JSON or defaults
    meta_feasible = False
    direction = "mixed"
    n_synth = len(extraction_records)
    narr_text = f"Narrative synthesis of {n_synth} studies."
    themes: List[str] = []

    _GENERIC_GROUPINGS = frozenset({"primary_outcome", "secondary_outcome"})

    if narrative:
        feasibility = narrative.get("feasibility", {})
        raw_feasible = bool(feasibility.get("feasible", False))
        groupings = feasibility.get("groupings", [])
        # Only treat as feasible when groupings contain real outcome names,
        # not just the generic "primary_outcome" / "secondary_outcome" fallbacks.
        generic_only = not groupings or all(
            g in _GENERIC_GROUPINGS for g in groupings
        )
        meta_feasible = raw_feasible and not generic_only
        narr_obj = narrative.get("narrative", {})
        direction = _normalize_label(narr_obj.get("effect_direction_summary", direction))
        n_synth = narr_obj.get("n_studies", n_synth)
        narr_text = narr_obj.get("narrative_text", narr_text)
        themes = narr_obj.get("key_themes", [])

    # Per-study summaries
    paper_map = {p.paper_id: p for p in included_papers}
    study_summaries: List[StudySummary] = []
    for rec in extraction_records:
        paper = paper_map.get(rec.paper_id)
        title = paper.title or rec.paper_id if paper else rec.paper_id
        year = paper.year if paper else None
        key_finding = (rec.results_summary.get("summary") or "").strip()
        if not key_finding:
            key_finding = rec.intervention_description[:200]
        study_summaries.append(
            StudySummary(
                paper_id=rec.paper_id,
                title=title[:120],
                year=year,
                study_design=_normalize_label(rec.study_design.value),
                participant_count=rec.participant_count,
                key_finding=key_finding[:300],
            )
        )

    # Extract valid citekeys from the citation catalog
    valid_citekeys: List[str] = []
    for line in citation_catalog.splitlines():
        line = line.strip()
        if line.startswith("[") and "]" in line:
            key = line[1 : line.index("]")]
            if key:
                valid_citekeys.append(key)

    total_included_count = (
        prisma_counts.studies_included_qualitative
        + prisma_counts.studies_included_quantitative
    )
    fulltext_excluded_count = max(
        0, prisma_counts.reports_assessed - total_included_count
    )

    return WritingGroundingData(
        databases_searched=active_dbs,
        other_methods_searched=active_other,
        search_date=str(datetime.now().year),
        total_identified=prisma_counts.total_identified_databases
        + prisma_counts.total_identified_other,
        duplicates_removed=prisma_counts.duplicates_removed,
        total_screened=prisma_counts.records_screened,
        fulltext_assessed=prisma_counts.reports_assessed,
        total_included=total_included_count,
        fulltext_excluded=fulltext_excluded_count,
        excluded_fulltext_reasons=prisma_counts.reports_excluded_with_reasons,
        study_design_counts=design_counts,
        total_participants=total_participants,
        year_range=year_range,
        meta_analysis_feasible=meta_feasible,
        synthesis_direction=direction,
        n_studies_synthesized=n_synth,
        narrative_text=narr_text,
        key_themes=themes,
        study_summaries=study_summaries,
        valid_citekeys=valid_citekeys,
        cohens_kappa=cohens_kappa,
        kappa_stage=kappa_stage,
        n_studies_reporting_count=n_studies_reporting_count,
        n_total_studies=n_total_studies,
        sensitivity_results=sensitivity_results or [],
    )


def format_grounding_block(data: WritingGroundingData) -> str:
    """Render grounding data as a labeled text block for prompt injection.

    The LLM is instructed to use these numbers verbatim and is forbidden
    from inventing any statistic or count outside this block.
    """
    lines = [
        "FACTUAL DATA BLOCK - You MUST use these exact numbers verbatim.",
        "Do NOT invent or fabricate any counts, statistics, or study characteristics",
        "that are not present in this block or the citation catalog below.",
        "---",
        f"Bibliographic databases searched: {', '.join(data.databases_searched) if data.databases_searched else 'see search appendix'}",
        f"Other methods (NOT databases - list separately as supplementary search): {', '.join(data.other_methods_searched) if data.other_methods_searched else 'none'}",
        "IMPORTANT: Do NOT list 'perplexity_web' or AI search tools as bibliographic databases. List them only under 'Other Methods' per PRISMA 2020 item 7.",
        f"Search date: {data.search_date}",
        f"Records identified: {data.total_identified}",
        f"Duplicates removed: {data.duplicates_removed}",
        f"Records screened (title/abstract): {data.total_screened}",
        f"Full-text assessed: {data.fulltext_assessed}",
        f"Full-text articles excluded: {data.fulltext_excluded}",
        f"Studies included: {data.total_included}",
    ]

    if data.excluded_fulltext_reasons:
        reasons_str = "; ".join(
            f"{_normalize_label(k)} ({v})"
            for k, v in data.excluded_fulltext_reasons.items()
        )
        lines.append(
            f"Primary exclusion reasons (categories may overlap): {reasons_str}"
        )

    if data.study_design_counts:
        # Keys are already normalized by build_writing_grounding
        design_str = ", ".join(
            f"{k}: {v}" for k, v in data.study_design_counts.items()
        )
        lines.append(f"Study designs: {design_str}")
    else:
        lines.append("Study designs: all non-randomized (observational/quasi-experimental)")

    if data.total_participants is not None:
        reporting_str = ""
        if data.n_total_studies > 0:
            reporting_str = (
                f" (from {data.n_studies_reporting_count} of "
                f"{data.n_total_studies} studies reporting N)"
            )
        lines.append(f"Total participants reported: {data.total_participants}{reporting_str}")
        if data.n_studies_reporting_count < data.n_total_studies:
            lines.append(
                "CAUTION: participant total is based on a subset of studies; "
                "do NOT state this as a definitive total without qualification."
            )
    else:
        lines.append("Total participants: not consistently reported across studies")

    if data.year_range:
        lines.append(f"Publication year range: {data.year_range}")

    lines.append(
        f"Meta-analysis: {'feasible' if data.meta_analysis_feasible else 'NOT feasible - narrative synthesis only'}"
    )
    lines.append(f"Synthesis direction: {data.synthesis_direction}")
    lines.append(f"Studies synthesized: {data.n_studies_synthesized}")
    lines.append(f"Narrative summary: {data.narrative_text}")

    _GENERIC_THEME_IDS = frozenset({"primary_outcome", "secondary_outcome"})
    readable_themes = [
        t.replace("_", " ")
        for t in data.key_themes
        if t not in _GENERIC_THEME_IDS and t.strip()
    ]
    if readable_themes:
        lines.append(f"Key outcome themes: {', '.join(readable_themes)}")

    if data.study_summaries:
        lines.append("")
        lines.append("INCLUDED STUDIES (use these for specific study references):")
        for i, s in enumerate(data.study_summaries, 1):
            parts = [f"{i}. {s.title}"]
            if s.year:
                parts[0] += f" ({s.year})"
            parts[0] += f" [{s.study_design}]"
            if s.participant_count:
                parts[0] += f", n={s.participant_count}"
            if s.key_finding:
                parts.append(f"   Finding: {s.key_finding}")
            lines.extend(parts)

    if data.cohens_kappa is not None:
        kappa_str = f"{data.cohens_kappa:.3f}"
        stage_str = f" ({data.kappa_stage} stage)" if data.kappa_stage else ""
        lines.append(f"Inter-rater reliability (Cohen's kappa): {kappa_str}{stage_str}")
        lines.append(
            "(Note: kappa is computed only for papers where both AI reviewers independently "
            "evaluated the study; fast-path single-reviewer decisions are excluded.)"
        )

    if data.sensitivity_results:
        lines.append("")
        lines.append("SENSITIVITY ANALYSIS RESULTS (report in Discussion if applicable):")
        for sens_text in data.sensitivity_results:
            lines.append(sens_text)

    if data.valid_citekeys:
        lines.append("")
        lines.append(
            "VALID CITATION KEYS - use ONLY these keys in square brackets, e.g. [Smith2023]:"
        )
        lines.append(", ".join(data.valid_citekeys))

    lines.append("---")
    return "\n".join(lines)
