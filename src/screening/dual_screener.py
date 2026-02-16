"""Dual-reviewer screening workflow with adjudication."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Protocol, Sequence

from pydantic import BaseModel, Field, ValidationError

from src.db.repositories import WorkflowRepository
from src.llm.provider import LLMProvider
from src.models import (
    CandidatePaper,
    DecisionLogEntry,
    ExclusionReason,
    ReviewConfig,
    ReviewerType,
    ScreeningDecision,
    ScreeningDecisionType,
    SettingsConfig,
)
from src.screening.prompts import adjudicator_prompt, reviewer_a_prompt, reviewer_b_prompt


class ScreeningResponse(BaseModel):
    decision: ScreeningDecisionType
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    exclusion_reason: ExclusionReason | None = None


class ScreeningLLMClient(Protocol):
    async def complete_json(
        self,
        prompt: str,
        *,
        agent_name: str,
        model: str,
        temperature: float,
    ) -> str:
        """Return a JSON string matching ScreeningResponse."""


class HeuristicScreeningClient:
    """Fallback client used in tests and offline runs."""

    async def complete_json(
        self,
        prompt: str,
        *,
        agent_name: str,
        model: str,
        temperature: float,
    ) -> str:
        lower = prompt.lower()
        if "no full text" in lower or "not retrieved" in lower:
            payload = ScreeningResponse(
                decision=ScreeningDecisionType.EXCLUDE,
                confidence=0.95,
                reasoning="Full text is unavailable for full-text screening.",
                exclusion_reason=ExclusionReason.NO_FULL_TEXT,
            )
        elif "exclude" in lower and "stage: fulltext" in lower and "conference abstract" in lower:
            payload = ScreeningResponse(
                decision=ScreeningDecisionType.EXCLUDE,
                confidence=0.9,
                reasoning="Exclusion criterion applies.",
                exclusion_reason=ExclusionReason.NOT_PEER_REVIEWED,
            )
        elif "reviewer b" in lower:
            payload = ScreeningResponse(
                decision=ScreeningDecisionType.UNCERTAIN,
                confidence=0.6,
                reasoning="Borderline evidence requires adjudication.",
            )
        else:
            payload = ScreeningResponse(
                decision=ScreeningDecisionType.INCLUDE,
                confidence=0.9,
                reasoning="Inclusion criteria are plausibly met.",
            )
        return payload.model_dump_json()


@dataclass(frozen=True)
class ReviewerSpec:
    agent_name: str
    reviewer_type: ReviewerType


class DualReviewerScreener:
    def __init__(
        self,
        repository: WorkflowRepository,
        provider: LLMProvider,
        review: ReviewConfig,
        settings: SettingsConfig,
        llm_client: ScreeningLLMClient | None = None,
    ):
        self.repository = repository
        self.provider = provider
        self.review = review
        self.settings = settings
        self.llm_client = llm_client or HeuristicScreeningClient()

    async def screen_title_abstract(self, workflow_id: str, paper: CandidatePaper) -> ScreeningDecision:
        result = await self._screen_one(
            workflow_id=workflow_id,
            paper=paper,
            stage="title_abstract",
            full_text=None,
        )
        return result

    async def screen_full_text(self, workflow_id: str, paper: CandidatePaper, full_text: str) -> ScreeningDecision:
        result = await self._screen_one(
            workflow_id=workflow_id,
            paper=paper,
            stage="fulltext",
            full_text=full_text,
        )
        return result

    async def screen_batch(
        self,
        workflow_id: str,
        stage: str,
        papers: Sequence[CandidatePaper],
        full_text_by_paper: dict[str, str] | None = None,
    ) -> list[ScreeningDecision]:
        processed = await self.repository.get_processed_paper_ids(workflow_id, stage)
        outputs: list[ScreeningDecision] = []
        for paper in papers:
            if paper.paper_id in processed:
                continue
            if stage == "fulltext":
                text = (full_text_by_paper or {}).get(paper.paper_id, "")
                outputs.append(await self.screen_full_text(workflow_id, paper, text))
            else:
                outputs.append(await self.screen_title_abstract(workflow_id, paper))
        return outputs

    async def _screen_one(
        self,
        workflow_id: str,
        paper: CandidatePaper,
        stage: str,
        full_text: str | None,
    ) -> ScreeningDecision:
        # Ensure FK integrity before writing screening decisions.
        await self.repository.save_paper(paper)
        reviewer_a = await self._run_reviewer(
            workflow_id=workflow_id,
            paper=paper,
            stage=stage,
            full_text=full_text,
            spec=ReviewerSpec(
                agent_name="screening_reviewer_a",
                reviewer_type=ReviewerType.REVIEWER_A,
            ),
        )
        reviewer_b = await self._run_reviewer(
            workflow_id=workflow_id,
            paper=paper,
            stage=stage,
            full_text=full_text,
            spec=ReviewerSpec(
                agent_name="screening_reviewer_b",
                reviewer_type=ReviewerType.REVIEWER_B,
            ),
        )

        if reviewer_a.decision == reviewer_b.decision:
            final_decision = reviewer_a
            adjudication_needed = False
            adjudication = None
        else:
            adjudication = await self._run_adjudicator(
                workflow_id=workflow_id,
                paper=paper,
                stage=stage,
                full_text=full_text,
                reviewer_a=reviewer_a,
                reviewer_b=reviewer_b,
            )
            final_decision = adjudication
            adjudication_needed = True

        if stage == "fulltext" and final_decision.decision == ScreeningDecisionType.EXCLUDE:
            final_decision = self._enforce_fulltext_exclusion_reason(final_decision)

        await self.repository.save_dual_screening_result(
            workflow_id=workflow_id,
            paper_id=paper.paper_id,
            stage=stage,
            agreement=reviewer_a.decision == reviewer_b.decision,
            final_decision=final_decision.decision,
            adjudication_needed=adjudication_needed,
        )
        await self.repository.append_decision_log(
            DecisionLogEntry(
                decision_type="dual_screening_final",
                paper_id=paper.paper_id,
                decision=final_decision.decision.value,
                rationale=final_decision.reason or "Final decision from dual-review workflow.",
                actor="dual_screener",
                phase="phase_3_screening",
            )
        )
        return final_decision

    async def _run_reviewer(
        self,
        workflow_id: str,
        paper: CandidatePaper,
        stage: str,
        full_text: str | None,
        spec: ReviewerSpec,
    ) -> ScreeningDecision:
        if spec.reviewer_type == ReviewerType.REVIEWER_A:
            prompt = reviewer_a_prompt(self.review, paper, stage, full_text)
        else:
            prompt = reviewer_b_prompt(self.review, paper, stage, full_text)
        decision = await self._request_decision(prompt=prompt, spec=spec, paper_id=paper.paper_id)
        if stage == "fulltext" and decision.decision == ScreeningDecisionType.EXCLUDE:
            decision = self._enforce_fulltext_exclusion_reason(decision)
        await self.repository.save_screening_decision(workflow_id=workflow_id, stage=stage, decision=decision)
        await self.repository.append_decision_log(
            DecisionLogEntry(
                decision_type="screening_reviewer_decision",
                paper_id=paper.paper_id,
                decision=decision.decision.value,
                rationale=decision.reason or "Reviewer decision generated.",
                actor=decision.reviewer_type.value,
                phase="phase_3_screening",
            )
        )
        return decision

    async def _run_adjudicator(
        self,
        workflow_id: str,
        paper: CandidatePaper,
        stage: str,
        full_text: str | None,
        reviewer_a: ScreeningDecision,
        reviewer_b: ScreeningDecision,
    ) -> ScreeningDecision:
        prompt = adjudicator_prompt(self.review, paper, stage, reviewer_a, reviewer_b, full_text)
        decision = await self._request_decision(
            prompt=prompt,
            spec=ReviewerSpec(
                agent_name="screening_adjudicator",
                reviewer_type=ReviewerType.ADJUDICATOR,
            ),
            paper_id=paper.paper_id,
        )
        await self.repository.save_screening_decision(workflow_id=workflow_id, stage=stage, decision=decision)
        await self.repository.append_decision_log(
            DecisionLogEntry(
                decision_type="screening_adjudication",
                paper_id=paper.paper_id,
                decision=decision.decision.value,
                rationale=decision.reason or "Adjudication decision generated.",
                actor=ReviewerType.ADJUDICATOR.value,
                phase="phase_3_screening",
            )
        )
        return decision

    async def _request_decision(self, prompt: str, spec: ReviewerSpec, paper_id: str) -> ScreeningDecision:
        runtime = await self.provider.reserve_call_slot(spec.agent_name)
        started = time.perf_counter()
        raw = await self.llm_client.complete_json(
            prompt,
            agent_name=spec.agent_name,
            model=runtime.model,
            temperature=runtime.temperature,
        )
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        await self.provider.log_cost(
            model=runtime.model,
            tokens_in=max(1, len(prompt.split())),
            tokens_out=max(1, len(raw.split())),
            cost_usd=0.0,
            latency_ms=elapsed_ms,
            phase="phase_3_screening",
        )
        parsed = self._parse_response(raw)
        return ScreeningDecision(
            paper_id=paper_id,
            decision=parsed.decision,
            reason=parsed.reasoning,
            exclusion_reason=parsed.exclusion_reason,
            reviewer_type=spec.reviewer_type,
            confidence=parsed.confidence,
        )

    @staticmethod
    def _parse_response(raw: str) -> ScreeningResponse:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return ScreeningResponse(
                decision=ScreeningDecisionType.UNCERTAIN,
                confidence=0.0,
                reasoning="Model output was not valid JSON.",
            )
        try:
            return ScreeningResponse.model_validate(payload)
        except ValidationError:
            return ScreeningResponse(
                decision=ScreeningDecisionType.UNCERTAIN,
                confidence=0.0,
                reasoning="Model output did not match expected schema.",
            )

    @staticmethod
    def _enforce_fulltext_exclusion_reason(decision: ScreeningDecision) -> ScreeningDecision:
        if decision.exclusion_reason is not None:
            return decision
        return decision.model_copy(update={"exclusion_reason": ExclusionReason.OTHER})
