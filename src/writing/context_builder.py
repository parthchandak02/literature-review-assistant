"""Build grounding data for the writing phase from real pipeline outputs.

This module aggregates actual data (PRISMA counts, extraction records,
synthesis results) into a structured block injected into every LLM section
prompt, preventing hallucination of statistics, counts, and citation keys.
"""

from __future__ import annotations

from datetime import datetime

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
    other_methods_searched: list[str]
    search_date: str

    # PRISMA counts
    total_identified: int
    duplicates_removed: int
    # Records removed by automated pre-screening (BM25 ranking auto-exclusion or
    # keyword hard-gate) BEFORE LLM title/abstract screening. PRISMA 2020 item 16
    # requires this to appear as "Automation tools (n=X)" in the flow diagram and
    # to be disclosed in the Methods section ("Records removed before screening").
    # 0 when no automated pre-filter was applied.
    automation_excluded: int = 0
    total_screened: int
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
        "Two independent reviewers (large language models) screened titles and abstracts, "
        "with disagreements resolved by a third adjudicator. "
        "Papers advancing from title/abstract screening underwent full-text eligibility "
        "assessment; full-text retrieval was attempted via a multi-tier open-access resolver "
        "(Unpaywall, Semantic Scholar, Europe PMC, CORE, PubMed Central). "
        "Papers for which full text could not be retrieved were excluded and are reported "
        "in the PRISMA flow as 'Reports not retrieved'. "
        "Inter-rater reliability was measured using Cohen's kappa on the subset of papers "
        "requiring dual review."
    )

    # Number of quality assessments derived from heuristic fallback (LLM timed out).
    # When > 0, the Methods section notes that some assessments used a conservative heuristic.
    heuristic_assessment_count: int = 0

    # Background systematic reviews discovered by the related-literature search.
    # These citekeys are registered in the citation catalog and should be cited
    # in the Discussion when comparing this review's findings to prior work.
    # (PRISMA 2020 item 27 requires comparison with existing related reviews.)
    background_sr_citekeys: list[str] = []


def _build_screening_method_description(
    screening_decisions: list[object] | None,
    total_screened: int,
) -> str:
    """Compute an accurate screening method description from actual decision records.

    Counts decisions by actor (keyword_filter vs LLM reviewers) to describe the
    real tiered architecture rather than a generic 'two independent reviewers' claim.
    This ensures the Methods section accurately reflects what the pipeline did.
    """
    if not screening_decisions:
        return (
            "Two independent reviewers (large language models) screened titles and abstracts, "
            "with disagreements resolved by a third adjudicator. "
            "Papers advancing from title/abstract screening underwent full-text eligibility "
            "assessment; full-text retrieval was attempted via a multi-tier open-access resolver "
            "(Unpaywall, Semantic Scholar, Europe PMC, CORE, PubMed Central). "
            "Inter-rater reliability was measured using Cohen's kappa on the subset of papers "
            "requiring dual review."
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

    if kf_count > 0 and llm_count < kf_count:
        # Tiered architecture detected: keyword filter handled the majority
        return (
            f"Title and abstract screening used a tiered approach. "
            f"First, a BM25 keyword relevance pre-filter evaluated all {total_screened} records, "
            f"auto-excluding {kf_count} records with low relevance scores and routing {llm_count} "
            f"records for independent dual LLM review. "
            f"Two large language model reviewers then independently screened the {llm_count} "
            f"pre-filtered records, with a third adjudicator resolving any disagreements. "
            f"Papers advancing from title/abstract screening underwent full-text eligibility "
            f"assessment; full-text retrieval was attempted via a multi-tier open-access resolver "
            f"(Unpaywall, Semantic Scholar, Europe PMC, CORE, PubMed Central). "
            f"Inter-rater reliability was measured using Cohen's kappa on the {llm_count} records "
            f"evaluated by the dual LLM reviewers."
        )
    else:
        # Symmetric dual-review: both reviewers assessed all (or nearly all) records
        return (
            "Two independent reviewers (large language models) screened titles and abstracts, "
            "with disagreements resolved by a third adjudicator. "
            "Papers advancing from title/abstract screening underwent full-text eligibility "
            "assessment; full-text retrieval was attempted via a multi-tier open-access resolver "
            "(Unpaywall, Semantic Scholar, Europe PMC, CORE, PubMed Central). "
            "Inter-rater reliability was measured using Cohen's kappa on the subset of papers "
            "requiring dual review."
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

    # Extract valid citekeys from the citation catalog
    valid_citekeys: list[str] = []
    for line in citation_catalog.splitlines():
        line = line.strip()
        if line.startswith("[") and "]" in line:
            key = line[1 : line.index("]")]
            if key:
                valid_citekeys.append(key)

    total_included_count = prisma_counts.studies_included_qualitative + prisma_counts.studies_included_quantitative
    fulltext_excluded_count = max(0, prisma_counts.reports_assessed - total_included_count)

    return WritingGroundingData(
        databases_searched=active_dbs,
        zero_yield_databases=zero_yield_dbs,
        other_methods_searched=active_other,
        search_date=search_date or str(datetime.now().year),
        total_identified=prisma_counts.total_identified_databases + prisma_counts.total_identified_other,
        duplicates_removed=prisma_counts.duplicates_removed,
        automation_excluded=prisma_counts.automation_excluded,
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
            screening_decisions, prisma_counts.records_screened
        ),
        background_sr_citekeys=background_sr_citekeys or [],
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
    if data.search_limitation:
        lines.append(f"Search limitation: {data.search_limitation}")
    lines += [
        "IMPORTANT: Do NOT list 'perplexity_web' or AI search tools as bibliographic databases. List them only under 'Other Methods' per PRISMA 2020 item 7.",
        f"Search date: {data.search_date}",
        f"Records identified: {data.total_identified}",
        f"Duplicates removed: {data.duplicates_removed}",
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
        f"Full-text assessed: {data.fulltext_assessed}",
        f"Full-text articles excluded: {data.fulltext_excluded}",
        f"Studies included: {data.total_included}",
    ]

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
        lines.append(f"Publication year range: {data.year_range}")

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
            "NOT REGISTERED. Do NOT write 'registered prospectively'. "
            "State that the protocol was not registered or that registration is pending."
        )
    lines.append(f"Protocol registration: {reg_status}")
    lines.append(
        "CRITICAL: The 'Protocol Registration' field above is the authoritative source. "
        "Every section (Methods AND Declarations) MUST use identical wording. "
        "NEVER write 'registered prospectively' unless registration=YES."
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

    if data.cohens_kappa is not None:
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
        lines.append("Inter-rater reliability (Cohen's kappa): not computed for this run.")
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
            "this comparison. Do NOT write the Discussion without citing at least 2-3 of these reviews."
        )

    if data.valid_citekeys:
        lines.append("")
        lines.append("VALID CITATION KEYS - use ONLY these keys in square brackets, e.g. [Smith2023]:")
        lines.append(", ".join(data.valid_citekeys))

    lines.append("---")
    return "\n".join(lines)
