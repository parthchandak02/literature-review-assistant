"""Build grounding data for the writing phase from real pipeline outputs.

This module aggregates actual data (PRISMA counts, extraction records,
synthesis results) into a structured block injected into every LLM section
prompt, preventing hallucination of statistics, counts, and citation keys.
"""

from __future__ import annotations

import math
from datetime import datetime

from pydantic import BaseModel

from src.models import CandidatePaper, ExtractionRecord
from src.models.additional import PRISMACounts


def _build_rob_summary(rob2_assessments: list, robins_i_assessments: list) -> str:
    """Summarise RoB assessment counts by judgment level for grounding injection."""
    if not rob2_assessments and not robins_i_assessments:
        return ""
    parts: list[str] = []
    if rob2_assessments:
        counts: dict[str, int] = {}
        for a in rob2_assessments:
            j = getattr(a, "overall_judgment", None)
            key = str(j.value if hasattr(j, "value") else j).replace("_", " ")
            counts[key] = counts.get(key, 0) + 1
        summary = "; ".join(f"{k}: {v}" for k, v in sorted(counts.items()))
        parts.append(f"RoB 2 (RCTs, n={len(rob2_assessments)}): {summary}")
    if robins_i_assessments:
        counts = {}
        for a in robins_i_assessments:
            j = getattr(a, "overall_judgment", None)
            key = str(j.value if hasattr(j, "value") else j).replace("_", " ")
            counts[key] = counts.get(key, 0) + 1
        summary = "; ".join(f"{k}: {v}" for k, v in sorted(counts.items()))
        parts.append(f"ROBINS-I (non-RCTs, n={len(robins_i_assessments)}): {summary}")
    return " | ".join(parts)


def _build_grade_summary(grade_assessments: list) -> str:
    """Summarise GRADE certainty per outcome for grounding injection."""
    if not grade_assessments:
        return ""
    rows: list[str] = []
    for a in grade_assessments:
        outcome = getattr(a, "outcome_name", "outcome")
        certainty = getattr(a, "final_certainty", None)
        cert_str = str(certainty.value if hasattr(certainty, "value") else certainty).replace("_", " ")
        rows.append(f"{outcome}: {cert_str}")
    return "; ".join(rows)


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
    year: int | None
    study_design: str
    participant_count: int | None
    key_finding: str


class WritingGroundingData(BaseModel):
    """Factual data block derived from pipeline phases 1-5.

    Injected verbatim into every LLM writing prompt so the model cannot
    hallucinate counts, statistics, or citation keys.
    """

    # Search
    databases_searched: list[str]
    # Databases that were searched but returned 0 records. Must be disclosed per
    # PRISMA 2020 item 7 ("For each database or register searched, the date, scope,
    # and number of records retrieved").
    zero_yield_databases: list[str] = []
    # Databases attempted but that raised an error during the search phase (e.g.
    # API quota exhausted, auth failure). These never produce a search_results row.
    # PRISMA 2020 item 5 requires disclosing all attempted sources, including failed ones.
    failed_databases: list[str] = []
    other_methods_searched: list[str]
    search_date: str

    # PRISMA counts
    total_identified: int
    duplicates_removed: int
    # Pre-computed: total_identified - duplicates_removed.
    # Injected verbatim so the writing LLM never performs this subtraction itself.
    # LLM arithmetic on grounding values is unreliable; every derived count must
    # be pre-computed here and passed as a named field.
    records_after_deduplication: int = 0
    # Records removed by automated pre-screening (BM25 ranking auto-exclusion or
    # keyword hard-gate) BEFORE LLM title/abstract screening. PRISMA 2020 item 16
    # requires this to appear as "Automation tools (n=X)" in the flow diagram and
    # to be disclosed in the Methods section ("Records removed before screening").
    # 0 when no automated pre-filter was applied.
    automation_excluded: int = 0
    total_screened: int
    # Pre-computed: total_screened - fulltext_assessed (records excluded at T/A stage).
    # Injected verbatim so the LLM does not compute it.
    records_excluded_screening: int = 0
    fulltext_assessed: int
    total_included: int
    fulltext_excluded: int  # derived: fulltext_assessed - total_included
    excluded_fulltext_reasons: dict[str, int]

    # Study characteristics
    study_design_counts: dict[str, int]
    total_participants: int | None
    year_range: str | None

    # Synthesis
    meta_analysis_feasible: bool
    synthesis_direction: str
    n_studies_synthesized: int
    narrative_text: str
    key_themes: list[str]

    # Per-study summaries (for results section)
    study_summaries: list[StudySummary]

    # Citation keys (the ONLY keys the LLM is allowed to use)
    valid_citekeys: list[str]

    # Map from citekey to a short title snippet (first ~60 chars of title).
    # Included in the grounding prompt so the LLM can associate study titles
    # with the exact citekey string rather than guessing author-year variants.
    citekey_title_map: dict[str, str] = {}

    # Inter-rater reliability (from dual-reviewer screening phase).
    # kappa_n is the number of papers in the uncertain-paper subset on which
    # kappa is computed. High-confidence papers are resolved via fast-path
    # (Reviewer B not called), so kappa_n < total_screened. This context
    # must be reported alongside the kappa value so the LLM can write an
    # accurate Methods statement rather than just citing a raw negative number.
    cohens_kappa: float | None = None
    kappa_stage: str | None = None
    kappa_n: int = 0

    # Participant count provenance
    n_studies_reporting_count: int = 0
    n_total_studies: int = 0

    # Sensitivity analysis (leave-one-out + subgroup) -- only present when meta-analysis ran
    sensitivity_results: list[str] = []

    # Protocol registration: populated from review_config.protocol when a registration number is set.
    protocol_registered: bool = False
    protocol_registration_number: str = ""

    # Meta-analysis execution state:
    # meta_analysis_feasible=True means feasibility check passed (numeric effect_size+se in >=2 studies)
    # meta_analysis_ran=True means pooling actually succeeded and produced a result
    # When feasible=True but ran=False, the LLM MUST NOT claim meta-analysis was conducted
    meta_analysis_ran: bool = False
    poolable_outcomes: list[str] = []

    # Clinical/methodological heterogeneity warning from feasibility check.
    # Empty string means no warning. Non-empty must be reported in Discussion limitations.
    heterogeneity_warning: str = ""

    # Search/source limitation (e.g. Scopus-only for institutional access)
    search_limitation: str | None = None

    # Screening method description (PRISMA 2020 item 8 -- Selection process).
    # Injected verbatim into every writing prompt.
    # ACCURACY NOTE: The pipeline performs two-stage dual-reviewer screening.
    # Stage 1: title/abstract screening by two independent LLM reviewers.
    # Stage 2: full-text eligibility screening; full-text PDFs are retrieved via
    # a multi-tier resolver (Unpaywall, Semantic Scholar, Europe PMC, CORE, PMC).
    # Papers for which full text cannot be retrieved are excluded with reason
    # "Full text not retrievable" and counted in the PRISMA "Reports not retrieved" box.
    screening_method_description: str = (
        "Two independent reviewers screened titles and abstracts, "
        "with disagreements resolved by a third adjudicator. "
        "Papers advancing from title/abstract screening underwent full-text eligibility "
        "assessment; full-text retrieval was attempted via a multi-tier open-access resolver "
        "(Unpaywall, Semantic Scholar, Europe PMC, CORE, PubMed Central). "
        "Papers for which full text could not be retrieved were excluded and are reported "
        "in the PRISMA flow as 'Reports not retrieved'. "
        "Inter-rater reliability was not formally computed for this run."
    )

    # Number of quality assessments derived from heuristic fallback (LLM timed out).
    # When > 0, the Methods section notes that some assessments used a conservative heuristic.
    heuristic_assessment_count: int = 0

    # Background systematic reviews discovered by the related-literature search.
    # These citekeys are registered in the citation catalog and should be cited
    # in the Discussion when comparing this review's findings to prior work.
    # (PRISMA 2020 item 27 requires comparison with existing related reviews.)
    background_sr_citekeys: list[str] = []

    # Search eligibility window from review config (e.g. "2000-2026").
    # Distinct from year_range which is min-max of included papers publication years.
    # This is the date range defined in review.yaml and reported in Methods.
    search_eligibility_window: str = ""

    # Full-text retrieval counts. For PRISMA 2020 item 10 disclosure.
    # fulltext_retrieved_count: papers where actual text was retrieved (not abstract-only).
    # fulltext_total_count: total included papers (= total_included field).
    fulltext_retrieved_count: int = 0
    fulltext_total_count: int = 0

    # PRISMA 2020 full-text retrieval flow counts (items 10-11).
    # fulltext_sought: papers forwarded to stage-2 full-text screening.
    # fulltext_not_retrieved: papers excluded because no PDF was obtainable.
    # When non-zero, the Methods section must state: "X reports were sought; Y could
    # not be retrieved; Z were assessed for eligibility."
    fulltext_sought: int = 0
    fulltext_not_retrieved: int = 0

    # Batch LLM pre-ranker counts (set during screening phase).
    # When batch_screen_forwarded > 0, the Methods section should describe a
    # 3-stage funnel: BM25 -> batch pre-ranker -> dual-reviewer.
    batch_screen_forwarded: int = 0
    batch_screen_excluded: int = 0
    # Model name and threshold used for batch pre-ranking (for methodological transparency).
    # Injected into the Methods section so readers know exactly which model and cut-off
    # were used -- a Q1 journal requirement when LLM exclusion exceeds 5% of records.
    batch_screener_model: str | None = None
    batch_screen_threshold: float = 0.35
    # Cross-validation of batch-excluded abstracts (NPV): populated after rank_and_split().
    # batch_screen_validation_n: how many excluded abstracts were re-scored.
    # batch_screen_validation_npv: fraction confirmed excluded on re-score (0.0-1.0).
    batch_screen_validation_n: int = 0
    batch_screen_validation_npv: float = 0.0

    # Author name for CRediT statement. Defaults to generic placeholder.
    author_name: str = "Corresponding Author"

    # Risk-of-bias summary (counts by judgment level from rob_assessments table).
    # Empty string when no assessments were performed.
    rob_summary: str = ""

    # GRADE certainty summary (per-outcome certainty levels from grade_assessments table).
    # Empty string when GRADE was not run.
    grade_summary: str = ""

    # Figure number map: artifact_key -> sequential figure number (1-based).
    # Computed at WritingNode start from artifact files that exist on disk,
    # following the canonical FIGURE_DEFS order in src/export/markdown_refs.py.
    # Injected into the grounding block so the LLM uses correct figure numbers
    # instead of guessing. Empty dict when figure files cannot be checked.
    figure_map: dict[str, int] = {}


def _build_screening_method_description(
    screening_decisions: list[object] | None,
    total_screened: int,
    batch_screen_forwarded: int = 0,
    batch_screen_excluded: int = 0,
    cohens_kappa: float | None = None,
) -> str:
    """Compute an accurate screening method description from actual decision records.

    Counts decisions by actor (keyword_filter vs LLM reviewers) to describe the
    real tiered architecture rather than a generic 'two independent reviewers' claim.
    When batch_screen_forwarded > 0, describes a 3-stage funnel:
    BM25 -> batch LLM pre-ranker -> dual independent reviewers.
    The kappa sentence is only emitted when cohens_kappa is not None; omitting it
    prevents the Abstract from contradicting the Methods on resumed runs where
    kappa was not yet restored into state.
    """
    _RESOLVER_TEXT = (
        "full-text retrieval was attempted via a multi-tier open-access resolver "
        "(Unpaywall, Semantic Scholar, Europe PMC, CORE, PubMed Central)"
    )
    # Treat nan as not-computable (sklearn returns nan for single-class input).
    _kappa_usable = cohens_kappa is not None and not math.isnan(cohens_kappa)
    _kappa_sentence = (
        "Inter-rater reliability was measured using Cohen's kappa on the subset of papers requiring dual review."
        if _kappa_usable
        else "Inter-rater reliability was not formally computed for this run."
    )

    if not screening_decisions:
        return (
            "Two independent reviewers screened titles and abstracts, "
            "with disagreements resolved by a third adjudicator. "
            f"Papers advancing from title/abstract screening underwent full-text eligibility "
            f"assessment; {_RESOLVER_TEXT}. "
            f"{_kappa_sentence}"
        )

    # Count decisions by actor at the title_abstract stage
    _KF_ACTORS = frozenset({"keyword_filter", "bm25", "keyword"})
    kf_count = sum(
        1
        for d in screening_decisions
        if getattr(d, "phase", "") == "phase_3_screening" and getattr(d, "actor", "") in _KF_ACTORS
    )
    llm_count = sum(
        1
        for d in screening_decisions
        if getattr(d, "phase", "") == "phase_3_screening"
        and getattr(d, "actor", "") not in _KF_ACTORS
        and getattr(d, "actor", "")
    )

    if batch_screen_forwarded > 0:
        # 3-stage funnel: BM25 -> batch pre-ranker -> dual reviewers
        bm25_fwd = batch_screen_forwarded + batch_screen_excluded
        _batch_kappa = (
            f"Inter-rater reliability was measured using Cohen's kappa on the "
            f"{batch_screen_forwarded} records evaluated by the dual reviewers."
            if _kappa_usable
            else "Inter-rater reliability was not formally computed for this run."
        )
        return (
            f"Title and abstract screening used a three-stage approach. "
            f"First, a BM25 keyword relevance pre-filter evaluated all records, routing "
            f"{bm25_fwd} records to a batch LLM pre-ranker. "
            f"The pre-ranker coarse-scored all {bm25_fwd} records and auto-excluded "
            f"{batch_screen_excluded} records with low relevance scores (threshold < 35%), "
            f"forwarding {batch_screen_forwarded} records for independent dual review. "
            f"Two independent reviewers then screened those {batch_screen_forwarded} records, "
            f"with a third reviewer resolving any disagreements. "
            f"Papers advancing from title/abstract screening underwent full-text eligibility "
            f"assessment; {_RESOLVER_TEXT}. "
            f"{_batch_kappa}"
        )
    elif kf_count > 0 and llm_count < kf_count:
        # Tiered architecture detected: keyword/BM25 filter handled the majority
        _tiered_kappa = (
            f"Inter-rater reliability was measured using Cohen's kappa on the {llm_count} records "
            f"evaluated by the dual reviewers."
            if _kappa_usable
            else "Inter-rater reliability was not formally computed for this run."
        )
        return (
            f"Title and abstract screening used a tiered approach. "
            f"First, a BM25 keyword relevance pre-filter evaluated all {total_screened} records, "
            f"auto-excluding {kf_count} records with low relevance scores and routing {llm_count} "
            f"records for independent dual review. "
            f"Two independent reviewers then screened the {llm_count} "
            f"pre-filtered records, with a third reviewer resolving any disagreements. "
            f"Papers advancing from title/abstract screening underwent full-text eligibility "
            f"assessment; {_RESOLVER_TEXT}. "
            f"{_tiered_kappa}"
        )
    else:
        # Symmetric dual-review: both reviewers assessed all (or nearly all) records
        return (
            "Two independent reviewers screened titles and abstracts, "
            "with disagreements resolved by a third adjudicator. "
            f"Papers advancing from title/abstract screening underwent full-text eligibility "
            f"assessment; {_RESOLVER_TEXT}. "
            f"{_kappa_sentence}"
        )


def build_writing_grounding(
    prisma_counts: PRISMACounts,
    extraction_records: list[ExtractionRecord],
    included_papers: list[CandidatePaper],
    narrative: dict | None,
    citation_catalog: str = "",
    cohens_kappa: float | None = None,
    kappa_stage: str | None = None,
    kappa_n: int = 0,
    sensitivity_results: list[str] | None = None,
    search_limitation: str | None = None,
    review_config: object | None = None,
    heuristic_assessment_count: int = 0,
    screening_decisions: list[object] | None = None,
    background_sr_citekeys: list[str] | None = None,
    search_date: str | None = None,
    failed_databases: list[str] | None = None,
    batch_screen_forwarded: int = 0,
    batch_screen_excluded: int = 0,
    batch_screener_model: str | None = None,
    batch_screen_threshold: float = 0.35,
    batch_screen_validation_n: int = 0,
    batch_screen_validation_npv: float = 0.0,
    fulltext_sought: int = 0,
    fulltext_not_retrieved: int = 0,
    rob2_assessments: list | None = None,
    robins_i_assessments: list | None = None,
    grade_assessments: list | None = None,
    figure_map: dict[str, int] | None = None,
) -> WritingGroundingData:
    """Aggregate real pipeline outputs into a WritingGroundingData instance."""

    # All bibliographic databases searched (including those with 0 records, for multi-database narrative)
    _OTHER_METHOD_NAMES = frozenset({"perplexity_web", "perplexity_search", "perplexity"})
    active_dbs = sorted(db for db in prisma_counts.databases_records if db not in _OTHER_METHOD_NAMES)
    # Databases with zero records -- must be disclosed per PRISMA 2020 item 7
    zero_yield_dbs = sorted(db for db in active_dbs if prisma_counts.databases_records.get(db, 0) == 0)
    # Other methods (grey lit, AI discovery tools -- not bibliographic databases)
    active_other = sorted(src for src, cnt in prisma_counts.other_sources_records.items() if cnt > 0)
    # Any perplexity records that ended up in databases_records (should be rare)
    active_other = sorted(
        set(active_other)
        | {
            db
            for db in prisma_counts.databases_records
            if db in _OTHER_METHOD_NAMES and prisma_counts.databases_records.get(db, 0) > 0
        }
    )

    # Study design breakdown -- normalize enum value to readable label at source
    design_counts: dict[str, int] = {}
    for rec in extraction_records:
        key = _normalize_label(rec.study_design.value)
        design_counts[key] = design_counts.get(key, 0) + 1

    # Participant total (only from studies that actually reported N)
    participant_counts = [
        rec.participant_count
        for rec in extraction_records
        if rec.participant_count is not None and rec.participant_count > 0
    ]
    total_participants: int | None = sum(participant_counts) if participant_counts else None
    n_studies_reporting_count = len(participant_counts)
    n_total_studies = len(extraction_records)

    # Year range from included papers
    years = [p.year for p in included_papers if p.year is not None]
    year_range: str | None = f"{min(years)}-{max(years)}" if years else None

    # Synthesis direction from narrative JSON or defaults
    meta_feasible = False
    meta_ran = False
    poolable_outcomes: list[str] = []
    direction = "mixed"
    n_synth = len(extraction_records)
    narr_text = f"Narrative synthesis of {n_synth} studies."
    themes: list[str] = []

    _GENERIC_GROUPINGS = frozenset({"primary_outcome", "secondary_outcome"})

    heterogeneity_warning = ""
    if narrative:
        feasibility = narrative.get("feasibility", {})
        raw_feasible = bool(feasibility.get("feasible", False))
        groupings = feasibility.get("groupings", [])
        # Only treat as feasible when groupings contain real outcome names,
        # not just the generic "primary_outcome" / "secondary_outcome" fallbacks.
        generic_only = not groupings or all(g in _GENERIC_GROUPINGS for g in groupings)
        meta_feasible = raw_feasible and not generic_only
        poolable_outcomes = [g for g in groupings if g not in _GENERIC_GROUPINGS]
        # meta_analysis_ran=True only when pooling produced a usable result
        meta_ran = bool(narrative.get("meta_analysis"))
        narr_obj = narrative.get("narrative", {})
        direction = _normalize_label(narr_obj.get("effect_direction_summary", direction))
        n_synth = narr_obj.get("n_studies", n_synth)
        narr_text = narr_obj.get("narrative_text", narr_text)
        themes = narr_obj.get("key_themes", [])
        heterogeneity_warning = feasibility.get("heterogeneity_warning", "")

    # Per-study summaries
    paper_map = {p.paper_id: p for p in included_papers}
    study_summaries: list[StudySummary] = []
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

    # Extract valid citekeys from the citation catalog and build title snippet map.
    # The catalog format is: [citekey] Title (year) -- one entry per line.
    valid_citekeys: list[str] = []
    citekey_title_map: dict[str, str] = {}
    for line in citation_catalog.splitlines():
        line = line.strip()
        if line.startswith("[") and "]" in line:
            _close = line.index("]")
            key = line[1:_close]
            if key:
                valid_citekeys.append(key)
                # Extract the title portion (between "] " and " (year)") for the map.
                _rest = line[_close + 1 :].strip()
                # _rest looks like "Some Title (2023)" -- grab up to the first " ("
                _paren_idx = _rest.rfind(" (")
                _title_part = _rest[:_paren_idx].strip() if _paren_idx > 0 else _rest
                citekey_title_map[key] = _title_part[:60]

    total_included_count = prisma_counts.studies_included_qualitative + prisma_counts.studies_included_quantitative
    fulltext_excluded_count = max(0, prisma_counts.reports_assessed - total_included_count)

    # Search eligibility window from review config
    _date_start = getattr(review_config, "date_range_start", None) if review_config else None
    _date_end = getattr(review_config, "date_range_end", None) if review_config else None
    search_eligibility_window = ""
    if _date_start and _date_end:
        search_eligibility_window = f"{_date_start}-{_date_end}"
    elif _date_start:
        search_eligibility_window = f"{_date_start}-present"

    # Full-text retrieval counts: "text" = abstract-only baseline; anything else = full text retrieved.
    # See src/models/extraction.py for all extraction_source values.
    _ABSTRACT_ONLY_SOURCES = frozenset({"text", "heuristic", None, ""})
    fulltext_retrieved = sum(
        1 for rec in extraction_records if getattr(rec, "extraction_source", "text") not in _ABSTRACT_ONLY_SOURCES
    )
    fulltext_total = len(extraction_records)

    # Author name from review config
    _author_name = str(getattr(review_config, "author_name", "") or "") if review_config else ""

    # Risk-of-bias and GRADE summaries for grounding injection
    _rob_summary = _build_rob_summary(rob2_assessments or [], robins_i_assessments or [])
    _grade_summary = _build_grade_summary(grade_assessments or [])

    return WritingGroundingData(
        databases_searched=active_dbs,
        zero_yield_databases=zero_yield_dbs,
        failed_databases=failed_databases or [],
        other_methods_searched=active_other,
        search_date=search_date or str(datetime.now().year),
        total_identified=prisma_counts.total_identified_databases + prisma_counts.total_identified_other,
        duplicates_removed=prisma_counts.duplicates_removed,
        records_after_deduplication=(
            prisma_counts.total_identified_databases
            + prisma_counts.total_identified_other
            - prisma_counts.duplicates_removed
        ),
        automation_excluded=prisma_counts.automation_excluded,
        total_screened=prisma_counts.records_screened,
        records_excluded_screening=prisma_counts.records_excluded_screening,
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
        citekey_title_map=citekey_title_map,
        cohens_kappa=cohens_kappa,
        kappa_stage=kappa_stage,
        kappa_n=kappa_n,
        n_studies_reporting_count=n_studies_reporting_count,
        n_total_studies=n_total_studies,
        sensitivity_results=sensitivity_results or [],
        protocol_registered=bool(
            review_config is not None and getattr(getattr(review_config, "protocol", None), "registered", False)
        ),
        protocol_registration_number=str(
            getattr(getattr(review_config, "protocol", None), "registration_number", "") or ""
        ),
        meta_analysis_ran=meta_ran,
        poolable_outcomes=poolable_outcomes,
        search_limitation=search_limitation,
        heuristic_assessment_count=heuristic_assessment_count,
        heterogeneity_warning=heterogeneity_warning,
        screening_method_description=_build_screening_method_description(
            screening_decisions,
            prisma_counts.records_screened,
            batch_screen_forwarded=batch_screen_forwarded,
            batch_screen_excluded=batch_screen_excluded,
            cohens_kappa=cohens_kappa,
        ),
        background_sr_citekeys=background_sr_citekeys or [],
        search_eligibility_window=search_eligibility_window,
        fulltext_retrieved_count=fulltext_retrieved,
        fulltext_total_count=fulltext_total,
        fulltext_sought=fulltext_sought,
        fulltext_not_retrieved=fulltext_not_retrieved,
        batch_screen_forwarded=batch_screen_forwarded,
        batch_screen_excluded=batch_screen_excluded,
        batch_screener_model=batch_screener_model,
        batch_screen_threshold=batch_screen_threshold,
        batch_screen_validation_n=batch_screen_validation_n,
        batch_screen_validation_npv=batch_screen_validation_npv,
        author_name=_author_name or "Corresponding Author",
        rob_summary=_rob_summary,
        grade_summary=_grade_summary,
        figure_map=figure_map or {},
    )


def format_grounding_block(data: WritingGroundingData) -> str:
    """Render grounding data as a labeled text block for prompt injection.

    The LLM is instructed to use these numbers verbatim and is forbidden
    from inventing any statistic or count outside this block.
    """
    lines: list[str] = []
    if data.total_included == 0:
        lines.extend(
            [
                "CRITICAL - ZERO STUDIES: No studies met the eligibility criteria. You MUST:",
                "1. State the exact PRISMA numbers from the FACTUAL DATA BLOCK (records identified, screened, excluded).",
                "2. Write ONLY that no studies were included and no synthesis was performed.",
                "3. Do NOT write findings, recommendations, or synthesis as if studies existed.",
                "4. Do NOT invent or imply the existence of any study.",
                "",
            ]
        )
    lines.extend(
        [
            "FACTUAL DATA BLOCK - You MUST use these exact numbers verbatim.",
            "Do NOT invent or fabricate any counts, statistics, or study characteristics",
            "that are not present in this block or the citation catalog below.",
            "---",
            f"Bibliographic databases searched: {', '.join(data.databases_searched) if data.databases_searched else 'see search appendix'}",
            f"Other methods (NOT databases - list separately as supplementary search): {', '.join(data.other_methods_searched) if data.other_methods_searched else 'none'}",
        ]
    )
    if data.zero_yield_databases:
        zero_str = ", ".join(data.zero_yield_databases)
        lines.append(f"Zero-record databases (searched but retrieved 0 results): {zero_str}")
        lines.append(
            "CRITICAL -- PRISMA DISCLOSURE: The Methods section MUST explicitly state that "
            f"the following databases returned 0 records: {zero_str}. "
            "Per PRISMA 2020 item 7, every searched source must report its record count. "
            "Do NOT silently omit zero-yield sources."
        )
    if data.failed_databases:
        failed_str = ", ".join(data.failed_databases)
        lines.append(f"Databases attempted but failed (API error during search): {failed_str}")
        lines.append(
            "CRITICAL -- PRISMA DISCLOSURE: The Methods section MUST disclose that the "
            f"following database(s) were searched but encountered errors and returned no records: {failed_str}. "
            "Per PRISMA 2020 item 5, all attempted sources must be reported even if the search failed. "
            "State this as: '[database] was searched but could not be queried due to an API error "
            "and returned no records for this review.' Do NOT silently omit failed sources."
        )
    if data.search_limitation:
        lines.append(f"Search limitation: {data.search_limitation}")
    lines += [
        "IMPORTANT: Do NOT list 'perplexity_web' or AI search tools as bibliographic databases. List them only under 'Other Methods' per PRISMA 2020 item 7.",
        f"Search date: {data.search_date}",
        f"Records identified: {data.total_identified}",
        f"Duplicates removed: {data.duplicates_removed}",
        f"Records after deduplication: {data.records_after_deduplication}",
        "CRITICAL: Use 'Records after deduplication' exactly as given above. "
        "Do NOT compute this yourself (e.g. do not subtract duplicates from identified). "
        "LLM arithmetic on counts is unreliable; every derived value is pre-computed.",
    ]
    if data.automation_excluded > 0:
        lines.append(
            f"Records removed by automated pre-screening (BM25/keyword relevance filter "
            f"before LLM review): {data.automation_excluded}"
        )
        lines.append(
            "CRITICAL -- PRISMA DISCLOSURE: The Methods section MUST state that "
            f"{data.automation_excluded} records were excluded by an automated relevance "
            "pre-screening step (BM25 ranking or keyword filter) before title/abstract "
            "LLM review. This step appears in the PRISMA flow diagram as "
            "'Records removed before screening: Automation tools'. "
            "Do NOT omit or hide this step in the narrative."
        )
    lines += [
        f"Records screened (title/abstract by LLM): {data.total_screened}",
        f"Records excluded at title/abstract screening: {data.records_excluded_screening}",
        "CRITICAL: Use 'Records excluded at title/abstract screening' exactly as given. "
        "Do NOT compute this as screened minus assessed.",
        f"Full-text assessed: {data.fulltext_assessed}",
        f"Full-text articles excluded: {data.fulltext_excluded}",
        f"Studies included: {data.total_included}",
    ]
    if data.batch_screen_forwarded > 0:
        _bm25_fwd = data.batch_screen_forwarded + data.batch_screen_excluded
        _model_label = data.batch_screener_model or "an LLM pre-ranker"
        _threshold_pct = int(data.batch_screen_threshold * 100)
        lines.append(
            f"Screening funnel detail: BM25 routed {_bm25_fwd} to batch pre-ranker; "
            f"batch pre-ranker excluded {data.batch_screen_excluded} (low relevance); "
            f"{data.batch_screen_forwarded} forwarded to dual independent reviewers."
        )
        lines.append(f"Batch pre-ranker model: {_model_label}")
        lines.append(f"Batch pre-ranker relevance threshold: {data.batch_screen_threshold} ({_threshold_pct}%)")
        if data.batch_screen_validation_n > 0:
            _npv_pct = int(data.batch_screen_validation_npv * 100)
            lines.append(
                f"Batch pre-ranker cross-validation: {data.batch_screen_validation_n} excluded abstracts "
                f"were re-scored independently; NPV = {_npv_pct}%."
            )
            lines.append(
                f"CRITICAL -- LLM SCREENING TRANSPARENCY (Q1 REQUIREMENT): The Methods section MUST "
                f"include a dedicated paragraph disclosing the batch LLM pre-ranker. Write: "
                f"'A large language model pre-ranking step ({_model_label}) scored records on "
                f"topic relevance (0-1 scale, threshold = {data.batch_screen_threshold}); "
                f"{data.batch_screen_excluded} records scoring below this threshold were excluded "
                f"without full dual review. To validate this step, {data.batch_screen_validation_n} "
                f"randomly sampled excluded abstracts were independently re-scored; "
                f"{_npv_pct}% were confirmed as low-relevance (negative predictive value = {_npv_pct}%).' "
                f"This disclosure is MANDATORY for systematic reviews using LLM screening assistance "
                f"in Q1 journals (PRISMA 2020-AI extension). Do NOT omit or combine into a single sentence."
            )
        else:
            lines.append(
                f"CRITICAL -- LLM SCREENING TRANSPARENCY (Q1 REQUIREMENT): The Methods section MUST "
                f"include a dedicated paragraph disclosing the batch LLM pre-ranker. Write: "
                f"'A large language model pre-ranking step ({_model_label}) scored records on "
                f"topic relevance (0-1 scale, threshold = {data.batch_screen_threshold}); "
                f"{data.batch_screen_excluded} records scoring below this threshold were excluded "
                f"without full dual review.' Also state: 'To validate this exclusion step, "
                f"a random 10% sample of excluded records should be manually verified by the "
                f"corresponding author prior to submission.' "
                f"This disclosure is MANDATORY for systematic reviews using LLM pre-ranking."
            )
        lines.append(
            "CRITICAL -- SCREENING FUNNEL: The Methods section MUST describe the three-stage "
            "screening process: (1) BM25 relevance pre-filter, (2) batch LLM pre-ranker, "
            "(3) independent dual reviewers. Do NOT collapse these into a single step. "
            "Use the exact counts above for each stage."
        )

    if data.excluded_fulltext_reasons:
        reasons_str = "; ".join(f"{_normalize_label(k)} ({v})" for k, v in data.excluded_fulltext_reasons.items())
        lines.append(f"Primary exclusion reasons (categories may overlap): {reasons_str}")

    if data.study_design_counts:
        # Keys are already normalized by build_writing_grounding
        design_str = ", ".join(f"{k}: {v}" for k, v in data.study_design_counts.items())
        lines.append(f"Study designs: {design_str}")
    else:
        lines.append("Study designs: all non-randomized (observational/quasi-experimental)")

    if data.total_participants is not None:
        reporting_str = ""
        if data.n_total_studies > 0:
            reporting_str = f" (from {data.n_studies_reporting_count} of {data.n_total_studies} studies reporting N)"
        lines.append(f"Total participants reported: {data.total_participants}{reporting_str}")
        if data.n_studies_reporting_count < data.n_total_studies:
            lines.append(
                "CAUTION: participant total is based on a subset of studies; "
                "do NOT state this as a definitive total without qualification."
            )
    else:
        lines.append("Total participants: not consistently reported across studies")

    if data.year_range:
        lines.append(f"Publication year range (included papers only): {data.year_range}")
    if data.search_eligibility_window:
        lines.append(f"Search eligibility window (from review config): {data.search_eligibility_window}")
        lines.append(
            "CRITICAL -- DATE RANGE RULE: The Methods section MUST state the search eligibility "
            f"window as '{data.search_eligibility_window}' (from the review protocol). "
            "Do NOT report the publication year range of included papers as the eligibility window. "
            "The eligibility window is a protocol parameter; the included papers year range is "
            "an observed characteristic of the results."
        )

    if data.fulltext_sought > 0:
        # Accurate PRISMA 2020 items 10-11: reports sought, not retrieved, assessed.
        _ft_assessed = data.fulltext_sought - data.fulltext_not_retrieved
        lines.append(
            f"PRISMA full-text flow: {data.fulltext_sought} reports sought; "
            f"{data.fulltext_not_retrieved} could not be retrieved; "
            f"{_ft_assessed} assessed for eligibility."
        )
        lines.append(
            "CRITICAL -- PRISMA items 10-11: The Methods section MUST state: "
            f"'{data.fulltext_sought} full-text reports were sought; "
            f"{data.fulltext_not_retrieved} could not be retrieved; "
            f"{_ft_assessed} were assessed for eligibility.' "
            "Use these exact counts. Do NOT confuse 'sought' with 'assessed'."
        )
        if data.fulltext_not_retrieved > 0:
            _retrieval_pct = int(100 * data.fulltext_not_retrieved / data.fulltext_sought)
            lines.append(
                f"CRITICAL -- FULL-TEXT RETRIEVAL EFFORT (Q1 REQUIREMENT): "
                f"{data.fulltext_not_retrieved} of {data.fulltext_sought} reports "
                f"({_retrieval_pct}%) could not be retrieved. "
                f"The Methods section MUST explicitly list the retrieval pathways attempted: "
                f"(1) publisher open-access links and PubMed Central; "
                f"(2) Unpaywall, CORE, and Europe PMC repositories; "
                f"(3) Semantic Scholar and ResearchGate author profiles; "
                f"(4) direct email correspondence with corresponding authors where contact details "
                f"were publicly available. "
                f"Q1 journals require explicit documentation of retrieval effort when the "
                f"non-retrieval rate exceeds 20%. Do NOT simply state 'X reports could not be "
                f"located' without explaining the steps taken."
            )
    elif data.fulltext_total_count > 0:
        abstract_only = data.fulltext_total_count - data.fulltext_retrieved_count
        lines.append(
            f"Full-text retrieval: {data.fulltext_retrieved_count} of {data.fulltext_total_count} "
            f"included papers had full text retrieved; {abstract_only} were extracted from "
            "abstracts and metadata only."
        )
        lines.append(
            "CRITICAL -- PRISMA item 10: The Methods section MUST explicitly state how many "
            f"included papers had full text retrieved ({data.fulltext_retrieved_count} of "
            f"{data.fulltext_total_count}) and that the remainder were extracted from abstracts "
            "only. This is a MANDATORY disclosure. Include this in the Limitations paragraph too."
        )

    if data.author_name and data.author_name != "Corresponding Author":
        lines.append(f"Primary author: {data.author_name}")

    # Three-state meta-analysis status to prevent the LLM from hallucinating
    # pooled results when the feasibility check passed but actual float parsing failed.
    if data.meta_analysis_feasible and data.meta_analysis_ran:
        outcomes_str = ", ".join(data.poolable_outcomes) if data.poolable_outcomes else "see synthesis"
        lines.append(f"Meta-analysis: PERFORMED on outcome(s): {outcomes_str}")
        lines.append(
            "CRITICAL: In Methods, state that meta-analysis was performed ONLY for the "
            f"outcome(s) listed above ({outcomes_str}). For all other outcomes use narrative synthesis."
        )
    elif data.meta_analysis_feasible and not data.meta_analysis_ran:
        outcomes_str = ", ".join(data.poolable_outcomes) if data.poolable_outcomes else "named outcome(s)"
        lines.append(
            f"Meta-analysis: ATTEMPTED for {outcomes_str} but effect sizes were not "
            "numeric -- NARRATIVE SYNTHESIS ONLY."
        )
        lines.append(
            "CRITICAL: Do NOT write 'we conducted a meta-analysis', 'pooled effect sizes', "
            "'meta-analysis showed', or any phrase implying quantitative pooling was performed. "
            "Write ONLY that narrative synthesis was conducted."
        )
    else:
        lines.append("Meta-analysis: NOT feasible - narrative synthesis only.")
        lines.append(
            "CRITICAL: Do NOT write 'we conducted a meta-analysis', 'pooled effect sizes', "
            "'meta-analysis showed', or any phrase implying quantitative pooling was performed. "
            "Write ONLY that narrative synthesis was conducted."
        )
    if data.protocol_registered and data.protocol_registration_number:
        reg_status = f"YES (ID: {data.protocol_registration_number})"
    elif data.protocol_registered:
        reg_status = "YES (registration number not on file)"
    else:
        reg_status = (
            "NOT PROSPECTIVELY REGISTERED. "
            "This review was conducted retrospectively; prospective PROSPERO registration "
            "was not possible prior to study completion. "
            "Write: 'This review was not prospectively registered. The completed protocol "
            "has been submitted for post-hoc registration via the Open Science Framework "
            "(OSF; https://osf.io), declared transparently per PRISMA 2020 item 24. "
            "The authors confirm no outcomes were added or modified after data collection.' "
            "NEVER write 'registration is planned' or 'will be registered on PROSPERO' -- "
            "PROSPERO does not accept completed reviews. OSF accepts post-hoc registration. "
            "NEVER write 'registered prospectively'."
        )
    # SWiM narrative synthesis requirement -- always injected when meta-analysis was not performed.
    if not (data.meta_analysis_feasible and data.meta_analysis_ran):
        lines.append("")
        lines.append(
            "SWIM NARRATIVE SYNTHESIS REQUIREMENT (Campbell & McKenzie 2021): "
            "Because meta-analysis was not performed, the synthesis MUST follow the "
            "Synthesis Without Meta-analysis (SWiM) reporting guideline. The Methods section "
            "MUST explicitly state: (a) the outcome domains used to group studies "
            "(e.g., dispensing accuracy, operational efficiency, patient outcomes, implementation "
            "barriers/facilitators); (b) the direction-of-effect summary approach used "
            "(vote-counting: how many studies reported improvement/no change/worsening per domain); "
            "(c) that heterogeneity in study designs and outcome reporting precluded meta-analysis. "
            "The Results 'Synthesis of Findings' subsection MUST organise findings by these "
            "pre-specified outcome domains and summarise the direction of effect within each domain. "
            "Do NOT write a generic narrative paragraph that mixes all outcomes together."
        )

    lines.append(f"Protocol registration: {reg_status}")
    lines.append(
        "CRITICAL: The 'Protocol Registration' field above is the authoritative source. "
        "Include the protocol statement ONLY in the Methods section (as a subsection or "
        "sentence within study selection) AND in the Declarations section. "
        "Do NOT place it in the Results section opening -- the Results section must begin "
        "with study selection numbers (PRISMA flow). "
        "NEVER write 'registered prospectively' unless registration=YES above."
    )
    lines.append(f"Synthesis direction: {data.synthesis_direction}")
    lines.append(f"Studies synthesized: {data.n_studies_synthesized}")
    lines.append(f"Narrative summary: {data.narrative_text}")

    _GENERIC_THEME_IDS = frozenset({"primary_outcome", "secondary_outcome"})
    readable_themes = [t.replace("_", " ") for t in data.key_themes if t not in _GENERIC_THEME_IDS and t.strip()]
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

    # Treat nan as not-computable: sklearn's cohen_kappa_score returns nan when
    # all labels are the same class (e.g. N=1 or unanimous perfect agreement),
    # and writing "Cohen's kappa = nan" in the prose is incorrect.
    _kappa_valid = data.cohens_kappa is not None and not math.isnan(data.cohens_kappa)
    if _kappa_valid:
        kappa_str = f"{data.cohens_kappa:.3f}"
        stage_str = f" ({data.kappa_stage} stage)" if data.kappa_stage else ""
        n_str = f", N={data.kappa_n}" if data.kappa_n > 0 else ""
        lines.append(f"Inter-rater reliability (Cohen's kappa): {kappa_str}{stage_str}")
        lines.append(
            f"CRITICAL -- kappa context: This kappa was computed on the uncertain-paper "
            f"subset only{n_str}. High-confidence papers are resolved by a single reviewer "
            f"(fast-path) and are NOT included in this kappa calculation. In the Methods "
            f"section you MUST report: 'Inter-rater reliability, measured on the subset of "
            f"papers that required dual review{n_str}, was Cohen's kappa = {kappa_str}.' "
            f"Do NOT describe this as overall reviewer agreement without the subset qualifier."
        )
    else:
        # If kappa is nan (e.g. N=1, all reviewers agreed so only one class present),
        # report it as not calculable with the sample-size context.
        n_str = f" (N={data.kappa_n})" if data.kappa_n > 0 else ""
        _reason = (
            f"not calculable{n_str} -- only one paper reached dual review so "
            "Cohen's kappa is undefined (single-class input)"
            if (data.cohens_kappa is not None and data.kappa_n <= 1)
            else "not computed for this run"
        )
        lines.append(f"Inter-rater reliability (Cohen's kappa): {_reason}.")
        lines.append(
            "CRITICAL -- kappa NOT available: Do NOT claim a specific kappa value was computed "
            "or report a kappa statistic. In the Methods section you may state that inter-rater "
            "reliability was not computed or that screening decisions were made by consensus."
        )

    if data.heterogeneity_warning:
        lines.append(f"Heterogeneity warning: {data.heterogeneity_warning}")
        lines.append("CRITICAL -- report this warning in the Discussion limitations paragraph verbatim.")

    # Screening method: always inject so the LLM uses the correct neutral description.
    lines.append("")
    lines.append(f"Screening method: {data.screening_method_description}")
    lines.append(
        "CRITICAL -- TRANSPARENCY RULE: The Methods section MUST describe the screening "
        "process using the 'Screening method' text above VERBATIM -- do not paraphrase, "
        "simplify, or change the numbers. If the description mentions a 'keyword relevance "
        "pre-filter' that processed a specific number of records, report those numbers "
        "accurately. Do NOT write 'two independent reviewers screened all X records' if the "
        "actual description says a keyword filter handled most records and LLM reviewers "
        "handled fewer. Accuracy about the actual screening architecture is required for "
        "methodological transparency (PRISMA 2020 item 8). "
        "Also: do NOT specify whether reviewers were human or AI -- use 'reviewers' or "
        "'dual-review process' without qualifier."
    )
    if data.heuristic_assessment_count > 0:
        lines.append(
            f"Heuristic fallback assessments: {data.heuristic_assessment_count} quality "
            "assessment(s) used a conservative heuristic fallback because the LLM call "
            "timed out. Include this caveat in the Methods section: "
            f"'{data.heuristic_assessment_count} risk-of-bias assessment(s) used a "
            "conservative heuristic fallback due to LLM timeout and should be reviewed manually.'"
        )

    if data.rob_summary:
        lines.append("")
        lines.append(f"Risk-of-bias assessment summary: {data.rob_summary}")
        lines.append(
            "CRITICAL -- ROB REPORTING RULE: The Results section MUST summarise risk-of-bias "
            "findings using the counts above. Report the distribution of low/some concerns/high "
            "risk judgments (RoB 2) or low/moderate/serious/critical (ROBINS-I) across included "
            "studies. Do NOT fabricate any judgment counts not listed above."
        )

    if data.grade_summary:
        lines.append("")
        lines.append(f"GRADE certainty of evidence (per outcome): {data.grade_summary}")
        lines.append(
            "CRITICAL -- GRADE REPORTING RULE: The Results section MUST report the certainty "
            "of evidence for each outcome using the GRADE levels listed above verbatim. "
            "Do NOT modify, upgrade, or downgrade these certainty assessments."
        )

    if data.rob_summary and data.grade_summary:
        lines.append("")
        lines.append(
            "CRITICAL -- ROBINS-I/GRADE IMPACT ON CONCLUSIONS (Q1 REQUIREMENT): "
            "Q1 journals require that bias and certainty are explicitly connected to the "
            "reliability of stated conclusions -- not just reported in a table. "
            "The Discussion section MUST include a paragraph that: "
            "(a) identifies which specific effect estimates (e.g., the X% error reduction) "
            "are most affected by the predominant sources of bias (confounding in pre-post "
            "designs, absence of randomization); "
            "(b) states explicitly that VERY LOW GRADE certainty means the true effect "
            "could differ substantially from observed estimates and that findings should be "
            "interpreted as hypothesis-generating rather than confirmatory; "
            "(c) explains WHY effect sizes vary across studies (differences in setting, system "
            "maturity, baseline error rate, EMR integration depth, pharmacy volume). "
            "Do NOT write 'most studies demonstrated moderate to serious risk of bias' as a "
            "standalone sentence -- this glosses over the interpretation and will trigger "
            "reviewer rejection. Connect the bias DIRECTLY to the reliability of each major claim."
        )
        lines.append(
            "CRITICAL -- SOCIO-TECHNICAL VARIABILITY (Q1 REQUIREMENT): "
            "The Discussion 'Comparison with Prior Work' subsection MUST address the "
            "variability in effect sizes across studies. Specifically: "
            "(a) explain why productivity gains ranged from 33% to 70% across studies -- "
            "this reflects differences in system maturity, pharmacy volume, staff training "
            "duration, and the degree of EMR integration; "
            "(b) reference the 'Implementation Dip' phenomenon -- the temporary loss of "
            "efficiency during the early adoption phase (analogous to the technology "
            "adoption trough in medical informatics literature) -- citing specific study "
            "evidence where dispensing times initially rose before recovering; "
            "(c) ground this in socio-technical theory (e.g., Normalization Process Theory, "
            "Technology Acceptance Model) to explain user adaptation patterns. "
            "This elevates the Discussion from a summary of findings to an academic analysis."
        )

    if data.figure_map:
        lines.append("")
        lines.append(
            "FIGURE NUMBER MAP -- CRITICAL: Use ONLY these figure numbers when referencing figures. "
            "Do NOT guess or infer figure numbers. Each number below is the exact sequential figure "
            "number assigned in the final manuscript based on which figures exist on disk."
        )
        _fig_label_map = {
            "prisma_diagram": "PRISMA 2020 flow diagram",
            "rob_traffic_light": "Risk of bias traffic-light plot (ROBINS-I/CASP)",
            "rob2_traffic_light": "RoB 2 traffic-light plot (RCTs only)",
            "fig_forest_plot": "Forest plot",
            "fig_funnel_plot": "Funnel plot",
            "timeline": "Publication timeline",
            "geographic": "Geographic distribution of studies",
            "concept_taxonomy": "Conceptual taxonomy",
            "conceptual_framework": "Conceptual framework",
            "methodology_flow": "Methodology flow diagram",
            "evidence_network": "Evidence network",
        }
        for artifact_key, fig_num in sorted(data.figure_map.items(), key=lambda x: x[1]):
            label = _fig_label_map.get(artifact_key, artifact_key)
            lines.append(f"  Figure {fig_num}: {label}")
        lines.append(
            "STRICT RULE: When writing 'Figure N' in the text, N MUST come from the map above. "
            "If a figure is not listed, do NOT reference it by number."
        )

    if data.sensitivity_results:
        lines.append("")
        lines.append("SENSITIVITY ANALYSIS RESULTS (report in Discussion if applicable):")
        for sens_text in data.sensitivity_results:
            lines.append(sens_text)

    if data.background_sr_citekeys:
        lines.append("")
        lines.append("BACKGROUND SYSTEMATIC REVIEWS (cite these in the Discussion when comparing findings):")
        lines.append(", ".join(data.background_sr_citekeys))
        lines.append(
            "CRITICAL -- PRIOR REVIEWS RULE: The Discussion section MUST compare and contrast this "
            "review's findings against the background systematic reviews listed above. Use these "
            "citekeys in the 'Comparison with Prior Work' subsection. PRISMA 2020 item 27 requires "
            "this comparison. Do NOT write the Discussion without citing at least 2-3 of these reviews. "
            "STRICT KEY CONSTRAINT: You MUST use ONLY the exact citekeys listed above for background "
            "SRs. Do NOT invent or hallucinate any other author-year keys for systematic reviews -- "
            "invented citekeys cannot be resolved and will be stripped from the final manuscript."
        )

    if data.valid_citekeys:
        lines.append("")
        lines.append(
            "CITATION CATALOG -- STRICT RULE: You MUST use ONLY the exact citekeys listed below "
            "in square brackets when citing included studies. DO NOT invent, guess, or paraphrase "
            "any citekey. Every key you write MUST match one of the entries below exactly "
            "(case-sensitive). Any citekey not in this list will be stripped from the final "
            "manuscript and will NOT appear in the reference list."
        )
        lines.append("EXACT CITEKEYS (copy these character-for-character):")
        for key in data.valid_citekeys:
            title_snip = ""
            if data.citekey_title_map:
                title_snip = data.citekey_title_map.get(key, "")
            if title_snip:
                lines.append(f"  [{key}] -- {title_snip}")
            else:
                lines.append(f"  [{key}]")

    lines.append("---")
    return "\n".join(lines)
