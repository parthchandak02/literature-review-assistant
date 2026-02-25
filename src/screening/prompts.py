"""Prompt builders for dual-reviewer screening."""

from __future__ import annotations

from src.models import CandidatePaper, ReviewConfig, ScreeningDecision


def _topic_header(review: ReviewConfig, role: str, goal: str, backstory: str) -> str:
    keyword_block = ", ".join(review.keywords)
    return "\n".join(
        [
            f"Role: {role}",
            f"Goal: {goal}",
            f"Backstory: {backstory}",
            f"Topic: {review.scope}",
            f"Research Question: {review.research_question}",
            f"Domain: {review.domain}",
            f"Keywords: {keyword_block}",
            "",
        ]
    )


def _quality_criteria_block() -> str:
    """Hard-floor data quality exclusion criteria applied before topic relevance.

    Both recall-biased and precision-biased reviewers must apply these criteria
    first. A paper failing any criterion is excluded regardless of topic match.
    """
    return "\n".join([
        "MANDATORY DATA QUALITY EXCLUSION CRITERIA (evaluate BEFORE topic relevance):",
        "EXCLUDE with exclusion_reason=insufficient_data if ANY of the following apply:",
        "- No authors are listed (Authors field is empty or blank)",
        "- The paper is an editorial, letter, opinion piece, commentary, or news item",
        "  with no original empirical data",
        "- The paper is a conference abstract only (no full peer-reviewed publication)",
        "- No study population or participant count can be identified (purely theoretical)",
        "- No measurable outcomes or quantitative/qualitative results are described",
        "- The paper is purely descriptive technology marketing with no evaluation",
        "",
        "EXCLUDE with exclusion_reason=protocol_only if the paper is a study PROTOCOL:",
        "- The title or abstract indicates this is a trial/study protocol, study design,",
        "  or registered trial with no reported results (e.g. 'Protocol for a randomized",
        "  trial', 'Study design and methods', 'trial registration', 'PROSPERO protocol')",
        "- A RCT protocol registered on ClinicalTrials.gov or PROSPERO with no outcome data",
        "- Review protocols (without data), methodology papers without empirical findings",
        "- NOTE: A completed trial that has a companion protocol paper is INCLUDED if the",
        "  paper you are reviewing contains actual results/outcome data.",
        "",
    ])


def _output_schema_block() -> str:
    return "\n".join(
        [
            "Return ONLY valid JSON matching this exact schema:",
            '{"decision": "include|exclude|uncertain", "confidence": 0.0, "short_reason": "one-line summary max 80 chars", "reasoning": "full explanation", "exclusion_reason": "wrong_population|wrong_intervention|wrong_comparator|wrong_outcome|wrong_study_design|not_peer_reviewed|duplicate|insufficient_data|wrong_language|no_full_text|protocol_only|other|null"}',
            "Provide short_reason (one line, max 80 chars) for quick scanning; reasoning for full justification.",
        ]
    )


def _paper_block(paper: CandidatePaper, stage: str, full_text: str | None) -> str:
    lines = [
        f"Stage: {stage}",
        f"Paper ID: {paper.paper_id}",
        f"Title: {paper.title}",
        f"Authors: {', '.join(paper.authors)}",
        f"Abstract: {paper.abstract or ''}",
    ]
    if stage == "fulltext":
        lines.append(f"Full Text (truncated to 8000 chars): {(full_text or '')[:8000]}")
    return "\n".join(lines)


def reviewer_a_prompt(review: ReviewConfig, paper: CandidatePaper, stage: str, full_text: str | None = None) -> str:
    return "\n\n".join(
        [
            _topic_header(
                review=review,
                role="Reviewer A",
                goal="Include the paper if any inclusion criterion is plausibly met.",
                backstory="You prioritize recall for systematic review screening.",
            ),
            _quality_criteria_block(),
            _paper_block(paper, stage, full_text),
            "Screening policy: Inclusion-emphasis reviewer. Apply mandatory data quality criteria above first.",
            _output_schema_block(),
        ]
    )


def reviewer_b_prompt(review: ReviewConfig, paper: CandidatePaper, stage: str, full_text: str | None = None) -> str:
    return "\n\n".join(
        [
            _topic_header(
                review=review,
                role="Reviewer B",
                goal="Exclude the paper if any exclusion criterion clearly applies.",
                backstory="You prioritize precision and strict exclusion decisions.",
            ),
            _quality_criteria_block(),
            _paper_block(paper, stage, full_text),
            "Screening policy: Exclusion-emphasis reviewer. Apply mandatory data quality criteria above first. When evidence is ambiguous on topic, prefer uncertain over exclude.",
            _output_schema_block(),
        ]
    )


def adjudicator_prompt(
    review: ReviewConfig,
    paper: CandidatePaper,
    stage: str,
    reviewer_a: ScreeningDecision,
    reviewer_b: ScreeningDecision,
    full_text: str | None = None,
) -> str:
    decision_context = "\n".join(
        [
            f"Reviewer A decision: {reviewer_a.decision.value} (confidence={reviewer_a.confidence:.2f}) reason={reviewer_a.reason or ''}",
            f"Reviewer B decision: {reviewer_b.decision.value} (confidence={reviewer_b.confidence:.2f}) reason={reviewer_b.reason or ''}",
        ]
    )
    return "\n\n".join(
        [
            _topic_header(
                review=review,
                role="Adjudicator",
                goal="Resolve disagreement between reviewer decisions.",
                backstory="You are the tie-breaker for systematic review decisions. When reviewers disagree and evidence is equivocal, lean toward include to preserve recall for full-text screening.",
            ),
            _quality_criteria_block(),
            _paper_block(paper, stage, full_text),
            decision_context,
            _output_schema_block(),
        ]
    )
