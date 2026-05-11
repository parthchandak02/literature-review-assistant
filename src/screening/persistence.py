"""Persistence helpers for screening heuristic decisions."""

from __future__ import annotations

from collections.abc import Callable

from src.db.repositories import WorkflowRepository
from src.models import (
    DecisionLogEntry,
    ExclusionReason,
    ReviewerType,
    ScreeningDecision,
    ScreeningDecisionType,
)


async def persist_no_fulltext_exclusion(
    repository: WorkflowRepository,
    *,
    workflow_id: str,
    stage: str,
    paper_id: str,
    on_screening_decision: Callable[[str, str, str, str | None, float | None], None] | None = None,
) -> ScreeningDecision:
    decision = ScreeningDecision(
        paper_id=paper_id,
        decision=ScreeningDecisionType.EXCLUDE,
        confidence=1.0,
        reason="Full text not retrievable.",
        reviewer_type=ReviewerType.ADJUDICATOR,
        exclusion_reason=ExclusionReason.NO_FULL_TEXT,
    )
    await repository.save_screening_decision(workflow_id=workflow_id, stage=stage, decision=decision)
    await repository.save_dual_screening_result(
        workflow_id=workflow_id,
        paper_id=paper_id,
        stage=stage,
        agreement=True,
        final_decision=ScreeningDecisionType.EXCLUDE,
        adjudication_needed=False,
    )
    await repository.append_decision_log(
        DecisionLogEntry(
            decision_type="screening_no_fulltext",
            paper_id=paper_id,
            decision=ScreeningDecisionType.EXCLUDE.value,
            rationale="Full text not retrievable; excluded per skip_fulltext_if_no_pdf.",
            actor=ReviewerType.ADJUDICATOR.value,
            phase="phase_3_screening",
        )
    )
    if on_screening_decision:
        on_screening_decision(paper_id, stage, "exclude", "fulltext_no_pdf_heuristic", 1.0)
    return decision


async def persist_protocol_exclusion(
    repository: WorkflowRepository,
    *,
    workflow_id: str,
    stage: str,
    paper_id: str,
    on_screening_decision: Callable[[str, str, str, str | None, float | None], None] | None = None,
) -> ScreeningDecision:
    decision = ScreeningDecision(
        paper_id=paper_id,
        decision=ScreeningDecisionType.EXCLUDE,
        confidence=0.95,
        reason="Protocol-only heuristic: title or abstract indicates a study protocol with no reported results.",
        reviewer_type=ReviewerType.KEYWORD_FILTER,
        exclusion_reason=ExclusionReason.PROTOCOL_ONLY,
    )
    await repository.save_screening_decision(workflow_id=workflow_id, stage=stage, decision=decision)
    await repository.append_decision_log(
        DecisionLogEntry(
            decision_type="screening_protocol_heuristic",
            paper_id=paper_id,
            decision=ScreeningDecisionType.EXCLUDE.value,
            rationale="Protocol-only auto-exclusion (no results available).",
            actor=ReviewerType.KEYWORD_FILTER.value,
            phase="phase_3_screening",
        )
    )
    if on_screening_decision:
        on_screening_decision(paper_id, stage, "exclude", "protocol_only_heuristic", 0.95)
    return decision


async def persist_insufficient_content_exclusion(
    repository: WorkflowRepository,
    *,
    workflow_id: str,
    stage: str,
    paper_id: str,
    abstract_word_count: int,
    min_words_threshold: int,
    on_screening_decision: Callable[[str, str, str, str | None, float | None], None] | None = None,
) -> ScreeningDecision:
    decision = ScreeningDecision(
        paper_id=paper_id,
        decision=ScreeningDecisionType.EXCLUDE,
        confidence=0.90,
        reason="Insufficient content: abstract absent, too short, or title-only stub -- no data extractable.",
        reviewer_type=ReviewerType.KEYWORD_FILTER,
        exclusion_reason=ExclusionReason.INSUFFICIENT_DATA,
    )
    await repository.save_screening_decision(workflow_id=workflow_id, stage=stage, decision=decision)
    await repository.append_decision_log(
        DecisionLogEntry(
            decision_type="screening_insufficient_content_heuristic",
            paper_id=paper_id,
            decision=ScreeningDecisionType.EXCLUDE.value,
            rationale=(
                f"Abstract absent or stub ({abstract_word_count} words). "
                f"Threshold: fewer than {min_words_threshold} words or explicit no-abstract marker."
            ),
            actor=ReviewerType.KEYWORD_FILTER.value,
            phase="phase_3_screening",
        )
    )
    if on_screening_decision:
        on_screening_decision(
            paper_id,
            stage,
            "exclude",
            f"insufficient_content_heuristic|{abstract_word_count}w",
            0.90,
        )
    return decision
