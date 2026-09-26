"""Jev study-design classification before Pro-tier LLM."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.llm.jev_client import (
    JevAskResult,
    JevQuestionChoice,
    ask_jev,
    jev_cost_phase,
    log_jev_cost,
    record_jev_decision,
)
from src.llm.provider import LLMProvider
from src.models import CandidatePaper, ReviewConfig, StudyDesign
from src.models.config import JevConfig

if TYPE_CHECKING:
    from src.db.repositories import WorkflowRepository

logger = logging.getLogger(__name__)

_PHASE = "phase_4_extraction_quality"
SURFACE = "study_design_classifier"

_DESIGN_CRITERIA: dict[str, str] = {
    "rct": "Randomized controlled trial",
    "non_randomized": "Non-randomized controlled study with comparator",
    "quasi_experimental": "Quasi-experimental / non-equivalent groups",
    "cohort": "Cohort study",
    "case_control": "Case-control study",
    "pre_post": "Single-group pre-post without control arm",
    "cross_sectional": "Cross-sectional or single time-point observation",
    "qualitative": "Qualitative study",
    "mixed_methods": "Mixed methods",
    "usability_study": "Usability/acceptability evaluation only",
    "development_study": "System/method paper with no quantitative evaluation",
    "protocol": "Protocol without results",
    "conference_abstract": "Conference abstract/poster only",
    "narrative_review": "Review or meta-analysis paper",
    "other": "None of the above",
}


def _map_design(choice: str) -> StudyDesign | None:
    key = choice.strip().lower()
    try:
        return StudyDesign(key)
    except ValueError:
        return None


@dataclass(frozen=True)
class JevDesignCall:
    choice: str = ""
    confidence: float = 0.0
    design: StudyDesign | None = None
    result: JevAskResult | None = None
    error: str | None = None


async def jev_study_design_call(*, review: ReviewConfig, paper: CandidatePaper, jev: JevConfig) -> JevDesignCall:
    """One Jev study-design call. Never raises."""
    state = {
        "research_question": review.research_question[:400],
        "topic": review.expert_topic()[:200],
        "paper": {
            "title": (paper.title or "")[:300],
            "abstract": (paper.abstract or "")[:3500].replace("\n", " "),
        },
    }
    question = JevQuestionChoice(
        instructions=(
            "Classify this paper's study design for systematic review routing. "
            "If the abstract reports any quantitative evaluation, do NOT choose development_study."
        ),
        criteria=_DESIGN_CRITERIA,
    )
    try:
        result = await asyncio.wait_for(
            ask_jev(model=jev.model, state=state, questions={"design": question}, timeout_seconds=jev.timeout_seconds),
            timeout=jev.timeout_seconds + 5.0,
        )
    except Exception as exc:
        return JevDesignCall(error=f"{type(exc).__name__}: {str(exc)[:200]}")
    answer = result.answers.get("design") or {}
    choice = str(answer.get("choice") or "")
    try:
        confidence = float(answer.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    return JevDesignCall(choice=choice, confidence=confidence, design=_map_design(choice), result=result)


def _would_route(call: JevDesignCall, jev: JevConfig) -> str:
    if call.error is not None or call.design is None or call.confidence < jev.route_confidence:
        return "escalate"
    return "jev"


async def jev_classify_study_design(
    *,
    review: ReviewConfig,
    paper: CandidatePaper,
    jev: JevConfig,
    workflow_id: str,
    repository: WorkflowRepository | None,
    provider: LLMProvider | None,
) -> StudyDesign | None:
    """Live path: return a study design when Jev is confident; None escalates to LLM."""
    _ = provider
    call = await jev_study_design_call(review=review, paper=paper, jev=jev)
    routed = _would_route(call, jev)
    cost: float | None = None
    if call.result is not None:
        cost = await log_jev_cost(
            repository, jev=jev, result=call.result, phase=jev_cost_phase(_PHASE, "live"), workflow_id=workflow_id
        )
    else:
        logger.warning("jev study design failed for %s: %s", paper.paper_id[:12], call.error)
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
        details={"mapped": call.design.value if call.design else None, "error": call.error},
    )
    return call.design if routed == "jev" else None


async def record_study_design_shadow(
    repository: WorkflowRepository | None,
    *,
    jev: JevConfig,
    workflow_id: str,
    paper_id: str,
    call: JevDesignCall,
    llm_design: StudyDesign,
    llm_predicted: str,
    llm_confidence: float,
) -> None:
    """Persist the shadow Jev answer next to the LLM classifier result. Never raises."""
    try:
        cost: float | None = None
        if call.result is not None:
            cost = await log_jev_cost(
                repository, jev=jev, result=call.result, phase=jev_cost_phase(_PHASE, "shadow"), workflow_id=workflow_id
            )
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
                "mapped": call.design.value if call.design else None,
                "would_route": _would_route(call, jev),
                "error": call.error,
                "llm_decision": llm_design.value,
                "llm_predicted": llm_predicted,
                "llm_confidence": llm_confidence,
            },
        )
    except Exception:
        logger.debug("jev study design shadow record skipped", exc_info=True)
