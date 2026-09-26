"""Jev-backed title/abstract screening for reviewer B."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from src.db.repositories import WorkflowRepository
from src.llm.jev_client import JevQuestionChoice, ask_jev
from src.llm.provider import LLMProvider
from src.models import (
    CandidatePaper,
    ExclusionReason,
    ReviewConfig,
    ReviewerType,
    ScreeningDecision,
    ScreeningDecisionType,
)
from src.models.config import JevConfig

logger = logging.getLogger(__name__)

_SCREENING_CHOICE = ("INCLUDE", "EXCLUDE", "UNCERTAIN")


@dataclass(frozen=True)
class JevScreeningOutcome:
    routed: str  # "jev" | "escalate"
    decision: ScreeningDecision | None = None
    confidence: float | None = None
    choice: str | None = None


def _build_state(review: ReviewConfig, paper: CandidatePaper) -> dict[str, object]:
    pico = review.pico
    return {
        "review": {
            "research_question": review.research_question,
            "scope": review.scope,
            "population": pico.population,
            "intervention": pico.intervention,
            "comparison": pico.comparison,
            "outcome": pico.outcome,
            "inclusion_criteria": review.inclusion_criteria[:12],
            "exclusion_criteria": review.exclusion_criteria[:12],
        },
        "paper": {
            "title": paper.title or "",
            "abstract": (paper.abstract or "")[:4000],
            "year": paper.year,
            "source_database": paper.source_database,
        },
    }


def _choice_question() -> JevQuestionChoice:
    return JevQuestionChoice(
        instructions=(
            "For this paper's title and abstract: screening decision against the review "
            "population, intervention, and study-design criteria in review."
        ),
        criteria={
            "INCLUDE": "Clearly meets population, intervention, and eligible study design",
            "EXCLUDE": "Clearly fails at least one inclusion criterion or is out of scope",
            "UNCERTAIN": "Insufficient information to include or exclude confidently",
        },
    )


def _map_choice(choice: str) -> ScreeningDecisionType:
    normalized = choice.strip().upper()
    if normalized == "INCLUDE":
        return ScreeningDecisionType.INCLUDE
    if normalized == "EXCLUDE":
        return ScreeningDecisionType.EXCLUDE
    return ScreeningDecisionType.UNCERTAIN


def _confidence_threshold_for(decision: ScreeningDecisionType, cfg: JevConfig) -> float:
    if decision == ScreeningDecisionType.EXCLUDE:
        return cfg.exclude_confidence
    return cfg.route_confidence


async def jev_screen_title_abstract(
    *,
    review: ReviewConfig,
    paper: CandidatePaper,
    jev: JevConfig,
    workflow_id: str,
    repository: WorkflowRepository,
    provider: LLMProvider | None,
) -> JevScreeningOutcome:
    """Run Jev for reviewer B. Fail-open: returns escalate on any error."""
    try:
        result = await ask_jev(
            model=jev.model,
            state=_build_state(review, paper),
            questions={"screen": _choice_question()},
            timeout_seconds=jev.timeout_seconds,
        )
        answer = result.answers.get("screen") or {}
        choice = str(answer.get("choice") or "").strip().upper()
        confidence = float(answer.get("confidence") or 0.0)
        if choice not in _SCREENING_CHOICE:
            await _persist_decision_log(
                repository,
                workflow_id,
                paper.paper_id,
                routed="escalate",
                choice=choice,
                confidence=confidence,
                reason="invalid_jev_choice",
            )
            return JevScreeningOutcome(routed="escalate", confidence=confidence, choice=choice)

        decision_type = _map_choice(choice)
        threshold = _confidence_threshold_for(decision_type, jev)
        if confidence < threshold:
            await _persist_decision_log(
                repository,
                workflow_id,
                paper.paper_id,
                routed="escalate",
                choice=choice,
                confidence=confidence,
                reason=f"below_threshold_{threshold}",
            )
            return JevScreeningOutcome(
                routed="escalate",
                confidence=confidence,
                choice=choice,
            )

        decision = ScreeningDecision(
            paper_id=paper.paper_id,
            decision=decision_type,
            reason=f"Jev screening ({choice}, conf={confidence:.2f})",
            exclusion_reason=ExclusionReason.OTHER if decision_type == ScreeningDecisionType.EXCLUDE else None,
            reviewer_type=ReviewerType.REVIEWER_B,
            confidence=confidence,
        )
        await _persist_decision_log(
            repository,
            workflow_id,
            paper.paper_id,
            routed="jev",
            choice=choice,
            confidence=confidence,
            reason="accepted",
        )
        if provider is not None:
            tok_in = int(result.usage.get("input_tokens", 0))
            tok_out = int(result.usage.get("output_tokens", 0))
            cost = provider.estimate_cost(result.model or jev.model, tok_in, tok_out)
            await provider.log_cost(
                model=result.model or jev.model,
                tokens_in=tok_in,
                tokens_out=tok_out,
                cost_usd=cost,
                latency_ms=result.latency_ms,
                phase="phase_3_screening_jev",
                workflow_id=workflow_id,
            )
        return JevScreeningOutcome(
            routed="jev",
            decision=decision,
            confidence=confidence,
            choice=choice,
        )
    except Exception as exc:
        logger.warning("Jev screening failed for %s (%s); escalating to LLM.", paper.paper_id[:12], exc)
        return JevScreeningOutcome(routed="escalate")


async def _persist_decision_log(
    repository: WorkflowRepository,
    workflow_id: str,
    paper_id: str,
    *,
    routed: str,
    choice: str,
    confidence: float,
    reason: str,
) -> None:
    try:
        await repository.save_jev_decision(
            workflow_id=workflow_id,
            phase="phase_3_screening",
            surface="screening_reviewer_b",
            paper_id=paper_id,
            choice=choice,
            confidence=confidence,
            routed=routed,
            details_json=json.dumps({"reason": reason}, sort_keys=True),
        )
    except Exception:
        logger.debug("jev_decisions persist skipped", exc_info=True)
