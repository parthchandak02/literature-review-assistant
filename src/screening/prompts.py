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


def _output_schema_block() -> str:
    return "\n".join(
        [
            'Return ONLY valid JSON matching this exact schema:',
            '{"decision": "include|exclude|uncertain", "confidence": 0.0, "reasoning": "...", "exclusion_reason": "wrong_population|wrong_intervention|wrong_comparator|wrong_outcome|wrong_study_design|not_peer_reviewed|duplicate|insufficient_data|wrong_language|no_full_text|other|null"}',
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
            _paper_block(paper, stage, full_text),
            "Screening policy: Inclusion-emphasis reviewer.",
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
            _paper_block(paper, stage, full_text),
            "Screening policy: Exclusion-emphasis reviewer.",
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
                backstory="You are the tie-breaker for systematic review decisions.",
            ),
            _paper_block(paper, stage, full_text),
            decision_context,
            _output_schema_block(),
        ]
    )
