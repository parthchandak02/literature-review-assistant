"""Jev study-design classification before Pro-tier LLM."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from src.llm.jev_client import JevQuestionChoice, ask_jev
from src.llm.provider import LLMProvider
from src.models import CandidatePaper, ReviewConfig, StudyDesign
from src.models.config import JevConfig

if TYPE_CHECKING:
    from src.db.repositories import WorkflowRepository

logger = logging.getLogger(__name__)

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


async def jev_classify_study_design(
    *,
    review: ReviewConfig,
    paper: CandidatePaper,
    jev: JevConfig,
    workflow_id: str,
    repository: WorkflowRepository | None,
    provider: LLMProvider | None,
) -> StudyDesign | None:
    """Return a study design when Jev is confident; None escalates to LLM."""
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
        result = await ask_jev(model=jev.model, state=state, questions={"design": question}, timeout_seconds=jev.timeout_seconds)
    except Exception as exc:
        logger.warning("jev study design failed for %s: %s", paper.paper_id[:12], exc)
        return None

    answer = result.answers.get("design") or {}
    choice = str(answer.get("choice") or "")
    confidence = float(answer.get("confidence") or 0.0)
    if confidence < jev.route_confidence:
        routed = "escalate"
        design = None
    else:
        design = _map_design(choice)
        routed = "jev" if design is not None else "escalate"

    if repository and workflow_id:
        try:
            await repository.save_jev_decision(
                workflow_id=workflow_id,
                phase="phase_4_extraction_quality",
                surface="study_design_classifier",
                paper_id=paper.paper_id,
                choice=choice,
                confidence=confidence,
                routed=routed,
                details_json=json.dumps({"mapped": design.value if design else None}, sort_keys=True),
            )
        except Exception:
            logger.debug("jev study design log skipped", exc_info=True)

    if provider is not None and routed == "jev":
        tok_in = int(result.usage.get("input_tokens", 0))
        tok_out = int(result.usage.get("output_tokens", 0))
        await provider.log_cost(
            model=result.model or jev.model,
            tokens_in=tok_in,
            tokens_out=tok_out,
            cost_usd=provider.estimate_cost(result.model or jev.model, tok_in, tok_out),
            latency_ms=result.latency_ms,
            phase="phase_4_extraction_quality_jev",
            workflow_id=workflow_id,
        )
    return design
