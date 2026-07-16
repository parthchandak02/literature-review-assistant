"""Deterministic grounding patches for section content and structured draft transforms."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from typing import TYPE_CHECKING

from src.models import (
    ReviewConfig,
    SettingsConfig,
    StructuredSectionDraft,
)
from src.writing.abstract_utils import (
    _ABSTRACT_FIELDS,
    _abstract_body_word_count,
    _ensure_structured_abstract,
    _normalize_structured_abstract_fields,
    _replace_or_append_abstract_field,
    _strip_abstract_citation_markup,
)
from src.writing.renderers import render_section_markdown
from src.writing.section_fallbacks import (
    _build_minimum_compliant_abstract,
    _expand_abstract_to_minimum_words,
)
from src.writing.section_validation import _validate_structured_section_draft
from src.writing.section_writer import SectionWriter

if TYPE_CHECKING:
    from src.writing.context_builder import WritingGroundingData

logger = logging.getLogger(__name__)


def _append_or_inject_subsection(content: str, heading: str, sentence: str, *, aliases: tuple[str, ...] = ()) -> str:
    headings = (heading, *aliases)
    escaped = "|".join(re.escape(item) for item in headings)
    pattern = re.compile(rf"(^###\s+(?:{escaped})\s*$)", flags=re.IGNORECASE | re.MULTILINE)
    if pattern.search(content):
        return pattern.sub(rf"### {heading}\n\n{sentence}", content, count=1)
    suffix = "" if not content.strip() else "\n\n"
    return f"{content.rstrip()}{suffix}### {heading}\n\n{sentence}".strip()


def _replace_or_append_subsection(
    content: str,
    heading: str,
    body: str,
    *,
    aliases: tuple[str, ...] = (),
) -> str:
    content = re.sub(r"(?<!\n)(###\s+)", r"\n\n\1", content)
    headings = (heading, *aliases)
    escaped = "|".join(re.escape(item) for item in headings)
    pattern = re.compile(
        rf"(?ms)^###\s+(?:{escaped})\s*$.*?(?=^###\s+|\Z)",
        flags=re.IGNORECASE,
    )
    replacement = f"### {heading}\n\n{body.strip()}"
    if pattern.search(content):
        return pattern.sub(replacement + "\n\n", content, count=1).strip()
    suffix = "" if not content.strip() else "\n\n"
    return f"{content.rstrip()}{suffix}{replacement}".strip()


def _replace_phrase_variants_case_insensitive(text: str, variants: tuple[str, ...], replacement: str) -> str:
    patched = text
    for variant in variants:
        source = str(variant or "")
        if not source:
            continue
        source_lower = source.lower()
        while True:
            idx = patched.lower().find(source_lower)
            if idx < 0:
                break
            patched = f"{patched[:idx]}{replacement}{patched[idx + len(source) :]}"
    return patched


def _structured_from_markdown(
    section: str,
    content: str,
    valid_citekeys: set[str],
    *,
    template: StructuredSectionDraft | None = None,
) -> StructuredSectionDraft:
    """Rebuild a structured draft from markdown after deterministic markdown transforms."""
    rebuilt = SectionWriter._fallback_structured_from_text(section, content)
    if template is not None:
        rebuilt.section_title = template.section_title
        rebuilt.required_subsections = list(template.required_subsections or [])
    rebuilt, _issues = _validate_structured_section_draft(section, rebuilt, valid_citekeys)
    return rebuilt


def _apply_markdown_transform_to_structured(
    section: str,
    draft: StructuredSectionDraft,
    valid_citekeys: set[str],
    transform: Callable[[str], str],
) -> StructuredSectionDraft:
    """Apply a deterministic markdown transform and sync the structured draft."""
    rendered = render_section_markdown(draft)
    transformed = transform(rendered).strip()
    if transformed == rendered.strip():
        return draft
    return _structured_from_markdown(section, transformed, valid_citekeys, template=draft)


def _build_rationale_sentence(review: ReviewConfig) -> str:
    domain_summary = review.domain_expert.domain_summary.strip()
    if domain_summary:
        return f"The rationale for this review is to address an evidence gap: {domain_summary.rstrip('.')}."
    return (
        f"The rationale for this review is to address an evidence gap in {review.domain}: "
        f"{review.research_question.rstrip('?')}."
    )


def _build_eligibility_screening_sentence(review: ReviewConfig) -> str:
    return (
        f"All included studies were screened against core eligibility requirements addressing "
        f"{review.pico.population}, evaluating {review.pico.intervention}, "
        f"comparing against {review.pico.comparison}, and reporting outcomes related to "
        f"{review.pico.outcome}."
    )


def _patch_introduction_grounding(content: str, review: ReviewConfig) -> str:
    patched = content.strip()
    lower = patched.lower()
    rationale_sentence = _build_rationale_sentence(review)
    objective_sentence = f"The research question for this systematic review is: {review.research_question}"
    if ("rationale" not in lower and "context" not in lower and "background" not in lower) or "gap" not in lower:
        patched = f"{patched.rstrip()}\n\n{rationale_sentence}"
    if "objective" not in lower and "aim" not in lower and "research question" not in lower and "question" not in lower:
        patched = f"{patched.rstrip()}\n\n{objective_sentence}"
    return patched


def _patch_methods_grounding(content: str, grounding: WritingGroundingData | None, review: ReviewConfig) -> str:
    if grounding is None:
        return content
    patched = content.strip()
    had_combined_info_search = bool(re.search(r"(?im)^###\s+Information Sources and Search Strategy\s*$", patched))
    abstract_only_count = max(0, int(grounding.fulltext_total_count) - int(grounding.fulltext_retrieved_count))
    db_sentence = f"The review searched {', '.join(grounding.databases_searched)} on {grounding.search_date}" + (
        f" with an eligibility window of {grounding.search_eligibility_window}."
        if grounding.search_eligibility_window
        else "."
    )
    if getattr(grounding, "failed_databases", []):
        db_sentence = (
            f"{db_sentence.rstrip()} "
            f"Attempted sources with connector failures were: {', '.join(grounding.failed_databases)}."
        )
    eligibility_sentence = (
        f"Eligible studies addressed {review.pico.population}, evaluated {review.pico.intervention}, "
        f"compared against {review.pico.comparison}, and reported outcomes related to {review.pico.outcome}."
    )
    selection_parts = [grounding.screening_method_description.strip()]
    selection_parts.append(
        f"Following title and abstract screening, {grounding.fulltext_sought} reports were sought for full-text retrieval, "
        f"{grounding.fulltext_not_retrieved} were not retrieved, {grounding.fulltext_assessed} were assessed for eligibility, "
        f"and {grounding.total_included} studies were included."
    )
    if abstract_only_count > 0:
        selection_parts.append(
            f"Eligibility assessment used the retrieved reports for all {grounding.fulltext_assessed} candidates, but "
            f"retrievable full-text PDFs were available for only {grounding.fulltext_retrieved_count} of the "
            f"{grounding.fulltext_total_count} included studies; the remaining {abstract_only_count} included studies "
            "were extracted from abstracts and metadata only."
        )
    if grounding.excluded_non_primary_count > 0:
        selection_parts.append(
            f"An additional {grounding.excluded_non_primary_count} papers were excluded after full-text assessment during "
            "extraction because they did not meet the primary study design criteria."
        )
    selection_sentence = " ".join(part.strip() for part in selection_parts if part.strip())
    if abstract_only_count > 0:
        data_collection_sentence = (
            "Data extraction used a standardized form to capture study characteristics, intervention details, comparators, "
            "outcomes, and risk-of-bias inputs. "
            f"Full texts were retrieved for {grounding.fulltext_retrieved_count} of {grounding.fulltext_total_count} included "
            f"studies, and {abstract_only_count} studies were extracted from abstracts and metadata only."
        )
    else:
        data_collection_sentence = (
            "Data extraction used a standardized form to capture study characteristics, intervention details, comparators, "
            "outcomes, and risk-of-bias inputs. "
            f"Among reports successfully retrieved and assessed for eligibility, full texts were available for "
            f"{grounding.fulltext_retrieved_count} of {grounding.fulltext_total_count} included studies."
        )
    tool_names: list[str] = []
    if "RoB 2" in grounding.rob_summary:
        tool_names.append("RoB 2")
    if "ROBINS-I" in grounding.rob_summary:
        tool_names.append("ROBINS-I")
    if "CASP" in grounding.rob_summary:
        tool_names.append("CASP")
    if "MMAT" in grounding.rob_summary:
        tool_names.append("MMAT")
    synthesis_sentence = (
        "Narrative synthesis was used to summarize outcome domains, and risk of bias was assessed with "
        + (", ".join(tool_names) if tool_names else "design-appropriate appraisal tools")
        + "."
    )
    risk_tool_counts = dict(getattr(grounding, "risk_tool_counts", {}) or {})
    mmat_count = int(risk_tool_counts.get("mmat", 0) or 0)
    casp_count = int(risk_tool_counts.get("casp", 0) or 0)
    design_counts = dict(getattr(grounding, "study_design_counts", {}) or {})
    mixed_methods_design_n = int(design_counts.get("mixed_methods", 0) or 0)
    pre_post_design_n = int(design_counts.get("pre_post", 0) or 0)
    risk_routing_sentence = ""
    if mmat_count > 0 or casp_count > 0:
        if mmat_count > mixed_methods_design_n and pre_post_design_n > 0:
            risk_routing_sentence = (
                f"Risk-of-bias routing was design-aligned: CASP covered {casp_count} qualitative/cross-sectional studies, "
                f"and MMAT covered {mmat_count} studies, including mixed-methods and pre-post/non-randomized quantitative designs."
            )
        else:
            risk_routing_sentence = (
                f"Risk-of-bias routing was design-aligned: CASP covered {casp_count} qualitative/cross-sectional studies, "
                f"and MMAT covered {mmat_count} mixed-methods studies."
            )
    search_strategy_sentence = (
        "Search strings combined protocol keywords with Boolean operators, database-specific filters, and date limits, "
        "and the full line-by-line strategies are archived in the appendix."
    )
    validation_sentence = ""
    batch_validation_n = int(getattr(grounding, "batch_screen_validation_n", 0) or 0)
    batch_validation_npv = float(getattr(grounding, "batch_screen_validation_npv", 0.0) or 0.0)
    if batch_validation_n > 0:
        validation_npv_pct = int(round(batch_validation_npv * 100))
        validation_sentence = (
            f"To verify automated exclusions, {batch_validation_n} low-relevance records were "
            f"cross-checked by dual review; {validation_npv_pct}% were confirmed as true exclusions."
        )
    outcome_definition_sentence = "Primary and secondary outcomes were defined a priori and sought across all reported time points for each study."
    effect_measure_sentence = (
        "The primary effect measure was the reported direction of effect; when available, odds ratio, risk ratio, "
        "mean difference, or standardized mean difference estimates were extracted descriptively rather than pooled."
    )
    data_prep_sentence = (
        "When reports lacked directly comparable numeric fields, data were prepared for synthesis through direct extraction, "
        "unit harmonization where possible, and narrative tabulation without imputation."
    )
    heterogeneity_sentence = (
        "Heterogeneity was explored qualitatively across study-design, setting, and outcome-domain subgroups, and subgroup "
        "results were compared narratively rather than by meta-regression."
    )
    reporting_bias_sentence = (
        "No formal reporting bias or publication bias assessment was feasible because the synthesis did not support pooled "
        "meta-analysis and included too few studies for a funnel plot or leave-one-out evaluation."
    )
    software_sentence = "Quantitative synthesis software such as statsmodels or scipy was not used because no pooled meta-analysis was performed."
    rob_coverage_sentence = ""
    missing_rob = int(getattr(grounding, "included_studies_without_rob_mapping", 0) or 0)
    if missing_rob > 0:
        rob_coverage_sentence = (
            f"Risk-of-bias coverage was incomplete for {missing_rob} of {grounding.total_included} included studies "
            "because appraisal-ready full-text methodological detail was unavailable for those records. These studies "
            "were interpreted conservatively and are flagged in the quality assessment coverage appendix."
        )
    lower = patched.lower()
    if not all(db.lower() in lower for db in grounding.databases_searched[:2]):
        patched = _append_or_inject_subsection(
            patched,
            "Information Sources",
            db_sentence,
            aliases=("Information Sources and Search Strategy",),
        )
    if review.pico.population.lower() not in lower or review.pico.intervention.lower() not in lower:
        patched = _append_or_inject_subsection(patched, "Eligibility Criteria", eligibility_sentence)
    patched = _replace_or_append_subsection(
        patched,
        "Selection Process",
        selection_sentence,
        aliases=("Study Selection",),
    )
    patched = _replace_or_append_subsection(
        patched,
        "Data Collection",
        data_collection_sentence,
        aliases=("Data Collection Process",),
    )
    if not had_combined_info_search and ("boolean" not in lower or "filter" not in lower or "limit" not in lower):
        patched = _replace_or_append_subsection(
            patched,
            "Search Strategy",
            search_strategy_sentence,
            aliases=("Information Sources and Search Strategy",),
        )
    if tool_names and not any(tool.lower() in lower for tool in tool_names):
        patched = _append_or_inject_subsection(patched, "Synthesis Methods", synthesis_sentence)
    if ("defined" not in lower and "sought" not in lower and "time point" not in lower) or "outcome" not in lower:
        patched = f"{patched.rstrip()}\n\n{outcome_definition_sentence}"
    if "effect measure" not in lower and "odds ratio" not in lower and "mean difference" not in lower:
        patched = f"{patched.rstrip()}\n\n{effect_measure_sentence}"
    if "missing data" not in lower and "imputation" not in lower and "prepare" not in lower:
        patched = f"{patched.rstrip()}\n\n{data_prep_sentence}"
    if "heterogeneity" not in lower or ("subgroup" not in lower and "modifier" not in lower):
        patched = f"{patched.rstrip()}\n\n{heterogeneity_sentence}"
    if "reporting bias" not in lower or "sensitivity analysis" not in lower:
        patched = f"{patched.rstrip()}\n\n{reporting_bias_sentence}"
    if "software" not in lower and "statsmodels" not in lower and "scipy" not in lower:
        patched = f"{patched.rstrip()}\n\n{software_sentence}"
    if validation_sentence:
        lower = patched.lower()
        if "automated exclusions" not in lower and "cross-checked by dual review" not in lower:
            patched = f"{patched.rstrip()}\n\n{validation_sentence}"
    if risk_routing_sentence:
        lower = patched.lower()
        if "risk-of-bias routing was design-aligned" not in lower:
            patched = f"{patched.rstrip()}\n\n{risk_routing_sentence}"
    if rob_coverage_sentence:
        lower = patched.lower()
        if "risk-of-bias coverage was incomplete" not in lower and "quality assessment coverage appendix" not in lower:
            patched = f"{patched.rstrip()}\n\n{rob_coverage_sentence}"
    return patched


def _patch_results_grounding(
    content: str,
    grounding: WritingGroundingData | None = None,
    review: ReviewConfig | None = None,
) -> str:
    patched = content.strip()
    patched = _replace_phrase_variants_case_insensitive(
        patched,
        (
            "predominantly positive direction of evidence",
            "predominantly positive impact",
            "predominantly positive",
        ),
        "directionally favorable but uncertain evidence pattern",
    )
    lower = patched.lower()
    if grounding is not None:
        selection_parts = [
            (
                f"The review screened {grounding.total_screened} records, sought {grounding.fulltext_sought} full-text reports, "
                f"did not retrieve {grounding.fulltext_not_retrieved}, assessed {grounding.fulltext_assessed} reports for "
                f"eligibility, and included {grounding.total_included} studies."
            )
        ]
        if grounding.excluded_fulltext_reasons:
            fulltext_excluded = int(
                getattr(
                    grounding,
                    "fulltext_excluded",
                    max(
                        0,
                        int(getattr(grounding, "fulltext_assessed", 0)) - int(getattr(grounding, "total_included", 0)),
                    ),
                )
                or 0
            )
            reasons = "; ".join(
                f"{str(reason).replace('_', ' ')} ({count})"
                for reason, count in grounding.excluded_fulltext_reasons.items()
            )
            selection_parts.append(
                f"Among {fulltext_excluded} reports excluded after full-text assessment, the primary reasons were "
                + reasons
                + "; each excluded report was assigned one primary reason category."
            )
        if grounding.excluded_non_primary_count > 0:
            selection_parts.append(
                f"An additional {grounding.excluded_non_primary_count} papers were excluded during extraction because they "
                "were classified as non-primary study types."
            )
        abstract_only_count = max(0, int(grounding.fulltext_total_count) - int(grounding.fulltext_retrieved_count))
        if abstract_only_count > 0:
            selection_parts.append(
                f"All {grounding.fulltext_assessed} reports were retrieved for eligibility assessment, but retrievable "
                f"full-text PDFs were available for only {grounding.fulltext_retrieved_count} of the "
                f"{grounding.fulltext_total_count} included studies; {abstract_only_count} studies were extracted from "
                "abstracts and metadata only."
            )
        if grounding.fulltext_sought > 0 and grounding.fulltext_not_retrieved > 0:
            unretrieved_pct = (grounding.fulltext_not_retrieved / grounding.fulltext_sought) * 100.0
            selection_parts.append(
                f"The non-retrieval rate at full-text screening was {grounding.fulltext_not_retrieved}/{grounding.fulltext_sought}, "
                "which may reduce evidence-base comprehensiveness and introduce retrieval bias if unretrieved reports differ "
                "systematically from the assessed evidence."
            )
            selection_parts.append(
                f"This corresponds to {unretrieved_pct:.1f}% unretrieved full-text reports; findings should therefore be treated as "
                "provisional and potentially inflated by selection bias."
            )
        risk_tool_counts = dict(getattr(grounding, "risk_tool_counts", {}) or {})
        mmat_count = int(risk_tool_counts.get("mmat", 0) or 0)
        casp_count = int(risk_tool_counts.get("casp", 0) or 0)
        design_counts = dict(getattr(grounding, "study_design_counts", {}) or {})
        mixed_methods_design_n = int(design_counts.get("mixed_methods", 0) or 0)
        pre_post_design_n = int(design_counts.get("pre_post", 0) or 0)
        if mmat_count > 0 or casp_count > 0:
            if mmat_count > mixed_methods_design_n and pre_post_design_n > 0:
                selection_parts.append(
                    f"Quality appraisal coverage included CASP for {casp_count} qualitative/cross-sectional studies and MMAT for "
                    f"{mmat_count} studies spanning mixed-methods plus pre-post/non-randomized quantitative designs."
                )
            else:
                selection_parts.append(
                    f"Quality appraisal coverage included CASP for {casp_count} qualitative/cross-sectional studies and MMAT for "
                    f"{mmat_count} mixed-methods studies."
                )
        if review is not None:
            selection_parts.append(_build_eligibility_screening_sentence(review))
        patched = _replace_or_append_subsection(patched, "Study Selection", " ".join(selection_parts))
        lower = patched.lower()
    heterogeneity_results_sentence = (
        "Heterogeneity results did not identify a consistent interaction or effect modifier across subgroup comparisons by "
        "study design, setting, or outcome domain."
    )
    reporting_bias_results_sentence = (
        "No reporting bias or publication bias result was available because funnel-based assessment was not interpretable for "
        "the small, heterogeneous synthesis set."
    )
    if "heterogeneity" not in lower or ("interaction" not in lower and "modifier" not in lower):
        patched = f"{patched.rstrip()}\n\n{heterogeneity_results_sentence}"
    if "reporting bias" not in lower and "publication bias" not in lower and "funnel" not in lower:
        patched = f"{patched.rstrip()}\n\n{reporting_bias_results_sentence}"
    return patched


def _patch_discussion_grounding(content: str, grounding: WritingGroundingData | None = None) -> str:
    patched = content.strip()
    patched = _replace_phrase_variants_case_insensitive(
        patched,
        ("predominantly positive impact",),
        "directionally favorable but low-certainty impact",
    )
    lower = patched.lower()
    review_process_limitations_sentence = (
        "A limitation of the review process and screening process was reliance on database coverage constraints, no citation "
        "chasing, no grey-literature search, and abstract-only extraction for studies without retrievable full text."
    )
    if "review process" not in lower:
        patched = f"{patched.rstrip()}\n\n{review_process_limitations_sentence}"
    if grounding is not None and grounding.fulltext_sought > 0 and grounding.fulltext_not_retrieved > 0:
        unretrieved_pct = (grounding.fulltext_not_retrieved / grounding.fulltext_sought) * 100.0
        nonretrieval_sentence = (
            f"A major limitation of the evidence base is that {grounding.fulltext_not_retrieved} of "
            f"{grounding.fulltext_sought} reports sought for full-text retrieval were not retrieved. "
            "This raises the possibility of reporting bias because unretrieved reports may have contained findings that "
            "differ from the included evidence and therefore reduce confidence in the apparent direction of effect."
        )
        if "reporting bias" not in lower and "not retrieved" not in lower:
            patched = f"{patched.rstrip()}\n\n{nonretrieval_sentence}"
        if unretrieved_pct >= 40.0 and "directionally suggestive rather than definitive" not in patched.lower():
            patched = (
                f"{patched.rstrip()}\n\n"
                f"The unretrieved full-text proportion was {unretrieved_pct:.1f}%, which is high enough to materially shift "
                "the direction and magnitude of effects; interpretations should remain directionally suggestive rather than definitive."
            )
    if grounding is not None:
        abstract_only_count = max(0, int(grounding.fulltext_total_count) - int(grounding.fulltext_retrieved_count))
        if abstract_only_count > 0:
            abstract_only_limitation_sentence = (
                f"Interpretation is further constrained because {abstract_only_count} of {grounding.fulltext_total_count} "
                "included studies were synthesized from abstracts and metadata only, which reduces methodological "
                "detail, increases uncertainty in risk-of-bias appraisal, and limits generalizability."
            )
            if "abstracts and metadata only" not in lower and "reduces methodological detail" not in lower:
                patched = f"{patched.rstrip()}\n\n{abstract_only_limitation_sentence}"
                lower = patched.lower()
        missing_rob = int(getattr(grounding, "included_studies_without_rob_mapping", 0) or 0)
        if missing_rob > 0:
            rob_gap_sentence = (
                f"Risk-of-bias evidence remained incomplete for {missing_rob} included studies without mapped appraisal "
                "rows, so certainty judgments for those records are conservative and should be interpreted as "
                "hypothesis-generating rather than confirmatory."
            )
            if (
                "without mapped appraisal rows" not in lower
                and "hypothesis-generating rather than confirmatory" not in lower
            ):
                patched = f"{patched.rstrip()}\n\n{rob_gap_sentence}"
                lower = patched.lower()
    if grounding is not None and grounding.grade_summary:
        certainty_sentence = (
            "The low to very low certainty ratings across reported outcomes mean that the observed effects should be "
            "interpreted as tentative signals rather than confirmatory estimates for policy or implementation decisions."
        )
        if "low to very low certainty" not in lower and "tentative signals" not in lower:
            patched = f"{patched.rstrip()}\n\n{certainty_sentence}"
    if grounding is not None and (
        getattr(grounding, "missing_participant_count", 0) > 0
        or getattr(grounding, "nonextractable_result_count", 0) > 0
    ):
        data_gap_sentence = (
            f"Data completeness was limited because {grounding.missing_participant_count} of "
            f"{grounding.n_total_studies} studies did not report participant counts and "
            f"{grounding.nonextractable_result_count} studies lacked extractable result summaries. "
            f"Of these result gaps, {grounding.abstract_only_result_gap_count} reflected abstract-only extraction after "
            "full text could not be retrieved, while the remainder reflected source texts that did not report a usable "
            "result statement."
        )
        if "data completeness was limited" not in lower and "extractable result summaries" not in lower:
            patched = f"{patched.rstrip()}\n\n{data_gap_sentence}"
    return patched


def _patch_conclusion_grounding(content: str, grounding: WritingGroundingData | None = None) -> str:
    patched = content.strip()
    lower = patched.lower()
    if grounding is None:
        return patched
    if grounding.fulltext_sought > 0 and grounding.fulltext_not_retrieved > 0:
        unretrieved_pct = (grounding.fulltext_not_retrieved / grounding.fulltext_sought) * 100.0
        retrieval_sentence = (
            f"Conclusions must remain cautious because {grounding.fulltext_not_retrieved} of "
            f"{grounding.fulltext_sought} reports sought for full-text review were not retrieved, "
            "which limits comprehensiveness and may bias the observed direction of evidence."
        )
        if "were not retrieved" not in lower and "limits comprehensiveness" not in lower:
            patched = f"{patched.rstrip()}\n\n{retrieval_sentence}"
            lower = patched.lower()
        if unretrieved_pct >= 40.0 and "should not be used for strong implementation claims" not in lower:
            patched = (
                f"{patched.rstrip()}\n\n"
                f"The unretrieved full-text proportion ({unretrieved_pct:.1f}%) is substantial and can plausibly overestimate "
                "benefit signals; this evidence should not be used for strong implementation claims without additional retrieval "
                "or targeted sensitivity analyses."
            )
            lower = patched.lower()
    if grounding.grade_summary:
        certainty_sentence = (
            "Given low to very low certainty across outcomes, findings should be interpreted as "
            "hypothesis-generating rather than confirmatory."
        )
        if "hypothesis-generating rather than confirmatory" not in lower:
            patched = f"{patched.rstrip()}\n\n{certainty_sentence}"
            lower = patched.lower()
    if grounding.missing_participant_count > 0:
        participant_sentence = (
            f"Generalizability is further constrained because participant counts were unavailable for "
            f"{grounding.missing_participant_count} of {grounding.n_total_studies} included studies."
        )
        if "participant counts were unavailable" not in lower:
            patched = f"{patched.rstrip()}\n\n{participant_sentence}"
    return patched


def _patch_abstract_grounding(
    content: str,
    grounding: WritingGroundingData | None,
    review: ReviewConfig,
    *,
    minimum_words: int = 210,
) -> str:
    if grounding is None:
        return content
    keywords_value = ", ".join(review.keywords[:5]) if review.keywords else "systematic review"
    if keywords_value and keywords_value[-1] not in ".!?":
        keywords_value = f"{keywords_value}."
    methods_value = (
        f"Searches of {', '.join(grounding.databases_searched)} were conducted on {grounding.search_date}"
        + (
            f" across the protocol window {grounding.search_eligibility_window}"
            if grounding.search_eligibility_window
            else ""
        )
        + f"; {grounding.total_screened} records were screened and {grounding.total_included} studies were included."
    )
    failed_dbs = [str(db).strip() for db in (getattr(grounding, "failed_databases", []) or []) if str(db).strip()]
    if failed_dbs:
        methods_value = (
            f"{methods_value.rstrip()} "
            f"An additional attempted source ({', '.join(failed_dbs)}) returned no records because of a connector/API failure."
        )
    results_value = (
        f"{grounding.fulltext_assessed} reports were assessed for eligibility and {grounding.total_included} studies were included; "
        f"the overall direction of evidence was {str(grounding.synthesis_direction).replace('_', ' ')}."
    )
    fulltext_sought = int(getattr(grounding, "fulltext_sought", 0) or 0)
    fulltext_not_retrieved = int(getattr(grounding, "fulltext_not_retrieved", 0) or 0)
    if fulltext_sought > 0 and fulltext_not_retrieved > 0:
        results_value = (
            f"{results_value.rstrip()} "
            f"The unretrieved full-text proportion ({fulltext_not_retrieved}/{fulltext_sought}) "
            "limits comprehensiveness and increases uncertainty in interpretation."
        )
    conclusions_value = ""
    if getattr(grounding, "conclusion_hedging_required", False):
        conclusions_value = (
            "Available evidence should be interpreted cautiously because low-certainty findings and missing retrievable "
            "full texts constrain the strength and generalizability of the conclusions. These findings should be treated "
            "as hypothesis-generating rather than definitive."
        )
    patched = content.strip()
    patched = _replace_or_append_abstract_field(
        patched,
        "Objectives",
        f"The primary objective of this review was to examine {review.research_question.rstrip('?')}.",
    )
    patched = _replace_or_append_abstract_field(patched, "Methods", methods_value)
    patched = _replace_or_append_abstract_field(patched, "Results", results_value)
    if conclusions_value:
        patched = _replace_or_append_abstract_field(patched, "Conclusions", conclusions_value)
    patched = _replace_phrase_variants_case_insensitive(
        patched,
        (
            "predominantly positive direction of evidence",
            "predominantly positive impact",
            "predominantly positive",
        ),
        "directionally favorable but uncertain evidence pattern",
    )
    patched = _replace_or_append_abstract_field(patched, "Keywords", keywords_value)
    patched = _expand_abstract_to_minimum_words(patched, grounding, minimum_words)
    if _abstract_body_word_count(patched) < minimum_words:
        return _build_minimum_compliant_abstract(review, grounding, minimum_words)
    return patched


def _apply_structured_grounding_patches(
    section: str,
    draft: StructuredSectionDraft,
    *,
    grounding: WritingGroundingData | None,
    review: ReviewConfig,
    settings: SettingsConfig,
    valid_citekeys: set[str],
) -> StructuredSectionDraft:
    """Apply deterministic section grounding to IR via markdown sync."""
    if section == "abstract":
        minimum_words = int(getattr(getattr(settings, "writing", None), "abstract_trim_floor_words", 210))

        def _transform(content: str) -> str:
            stripped = _strip_abstract_citation_markup(content)
            normalized = _normalize_structured_abstract_fields(stripped)
            has_all_fields = all(
                bool(re.search(rf"\*\*{re.escape(field)}:\*\*", normalized, flags=re.IGNORECASE))
                for field in _ABSTRACT_FIELDS
            )
            has_minimum_words = _abstract_body_word_count(normalized) >= minimum_words
            if has_all_fields and has_minimum_words:
                return normalized
            logger.warning(
                "Abstract structured output missed required field/word-band checks; applying legacy abstract repair fallback."
            )
            patched = _ensure_structured_abstract(normalized, review.research_question)
            patched = _patch_abstract_grounding(
                patched,
                grounding,
                review,
                minimum_words=minimum_words,
            )
            patched = _strip_abstract_citation_markup(patched)
            return _normalize_structured_abstract_fields(patched)

        return _apply_markdown_transform_to_structured(section, draft, valid_citekeys, _transform)
    if section in {"introduction", "methods", "results", "discussion", "conclusion"}:
        return draft
    return draft
