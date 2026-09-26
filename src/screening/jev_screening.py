"""Jev-backed title/abstract screening for reviewer B."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from src.db.repositories import WorkflowRepository
from src.llm.jev_client import (
    JevAskResult,
    JevQuestionChoice,
    ask_jev,
    bounded_gather,
    jev_cost_phase,
    log_jev_cost,
    record_jev_decision,
)
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
_PHASE = "phase_3_screening"
SURFACE = "screening_reviewer_b"


@dataclass(frozen=True)
class JevScreeningOutcome:
    routed: str  # "jev" | "escalate"
    decision: ScreeningDecision | None = None
    confidence: float | None = None
    choice: str | None = None


@dataclass(frozen=True)
class JevScreeningCall:
    paper_id: str
    choice: str = ""
    confidence: float = 0.0
    probabilities: dict[str, Any] = field(default_factory=dict)
    result: JevAskResult | None = None
    error: str | None = None


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


def route_screening_call(call: JevScreeningCall, jev: JevConfig) -> tuple[str, str]:
    """Return (routed, reason) the live path would take for this Jev answer."""
    if call.error is not None:
        return "escalate", f"error:{call.error}"
    if call.choice not in _SCREENING_CHOICE:
        return "escalate", "invalid_jev_choice"
    threshold = _confidence_threshold_for(_map_choice(call.choice), jev)
    if call.confidence < threshold:
        return "escalate", f"below_threshold_{threshold}"
    return "jev", "accepted"


async def call_jev_screening(*, review: ReviewConfig, paper: CandidatePaper, jev: JevConfig) -> JevScreeningCall:
    """One Jev title/abstract call. Never raises; errors land in ``error``."""
    try:
        result = await asyncio.wait_for(
            ask_jev(
                model=jev.model,
                state=_build_state(review, paper),
                questions={"screen": _choice_question()},
                timeout_seconds=jev.timeout_seconds,
            ),
            timeout=jev.timeout_seconds + 5.0,
        )
    except Exception as exc:
        return JevScreeningCall(paper_id=paper.paper_id, error=type(exc).__name__ + ": " + str(exc)[:200])
    answer = result.answers.get("screen") or {}
    probabilities = answer.get("probabilities") if isinstance(answer.get("probabilities"), dict) else {}
    try:
        confidence = float(answer.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    return JevScreeningCall(
        paper_id=paper.paper_id,
        choice=str(answer.get("choice") or "").strip().upper(),
        confidence=confidence,
        probabilities=probabilities,
        result=result,
    )


async def jev_screen_title_abstract(
    *,
    review: ReviewConfig,
    paper: CandidatePaper,
    jev: JevConfig,
    workflow_id: str,
    repository: WorkflowRepository,
    provider: LLMProvider | None,
) -> JevScreeningOutcome:
    """Live reviewer-B path. Fail-open: returns escalate on any error."""
    _ = provider
    call = await call_jev_screening(review=review, paper=paper, jev=jev)
    routed, reason = route_screening_call(call, jev)
    cost: float | None = None
    if call.result is not None:
        cost = await log_jev_cost(
            repository, jev=jev, result=call.result, phase=jev_cost_phase(_PHASE, "live"), workflow_id=workflow_id
        )
    await record_jev_decision(
        repository,
        workflow_id=workflow_id,
        phase=_PHASE,
        surface=SURFACE,
        paper_id=paper.paper_id,
        choice=call.choice,
        confidence=call.confidence,
        routed=routed if call.error is None else "error",
        mode="live",
        result=call.result,
        cost_usd=cost,
        details={"reason": reason, "probabilities": call.probabilities, "stage": "title_abstract"},
    )
    if routed != "jev":
        if call.error is not None:
            logger.warning("Jev screening failed for %s (%s); escalating to LLM.", paper.paper_id[:12], call.error)
        return JevScreeningOutcome(routed="escalate", confidence=call.confidence, choice=call.choice)

    decision_type = _map_choice(call.choice)
    decision = ScreeningDecision(
        paper_id=paper.paper_id,
        decision=decision_type,
        reason=f"Jev screening ({call.choice}, conf={call.confidence:.2f})",
        exclusion_reason=ExclusionReason.OTHER if decision_type == ScreeningDecisionType.EXCLUDE else None,
        reviewer_type=ReviewerType.REVIEWER_B,
        confidence=call.confidence,
    )
    return JevScreeningOutcome(routed="jev", decision=decision, confidence=call.confidence, choice=call.choice)


async def jev_live_screen_papers(
    *,
    review: ReviewConfig,
    papers: list[CandidatePaper],
    jev: JevConfig,
    workflow_id: str,
    repository: WorkflowRepository,
) -> dict[str, JevScreeningOutcome]:
    """Live reviewer-B over a chunk with bounded concurrency."""
    outcomes = await bounded_gather(
        (
            jev_screen_title_abstract(
                review=review, paper=p, jev=jev, workflow_id=workflow_id, repository=repository, provider=None
            )
            for p in papers
        ),
        jev.shadow_concurrency,
    )
    return {p.paper_id: o for p, o in zip(papers, outcomes, strict=True)}


async def jev_shadow_screen_papers(
    *, review: ReviewConfig, papers: list[CandidatePaper], jev: JevConfig
) -> dict[str, JevScreeningCall]:
    """Shadow Jev calls for a chunk (bounded, fail-open). Persist via record_screening_shadow."""
    calls = await bounded_gather(
        (call_jev_screening(review=review, paper=p, jev=jev) for p in papers), jev.shadow_concurrency
    )
    return {c.paper_id: c for c in calls}


async def record_screening_shadow(
    repository: WorkflowRepository | None,
    *,
    jev: JevConfig,
    workflow_id: str,
    stage: str,
    calls: dict[str, JevScreeningCall],
    llm_decisions: dict[str, ScreeningDecision],
) -> None:
    """Persist shadow Jev answers next to the LLM reviewer-B decision. Never raises."""
    for paper_id, call in calls.items():
        would_route, reason = route_screening_call(call, jev)
        cost: float | None = None
        if call.result is not None:
            cost = await log_jev_cost(
                repository,
                jev=jev,
                result=call.result,
                phase=jev_cost_phase(_PHASE, "shadow"),
                workflow_id=workflow_id,
            )
        llm = llm_decisions.get(paper_id)
        await record_jev_decision(
            repository,
            workflow_id=workflow_id,
            phase=_PHASE,
            surface=SURFACE,
            paper_id=paper_id,
            choice=call.choice,
            confidence=call.confidence,
            routed="shadow" if call.error is None else "shadow_error",
            mode="shadow",
            result=call.result,
            cost_usd=cost,
            details={
                "stage": stage,
                "would_route": would_route,
                "reason": reason,
                "probabilities": call.probabilities,
                "llm_decision": llm.decision.value if llm is not None else None,
                "llm_confidence": llm.confidence if llm is not None else None,
            },
        )
