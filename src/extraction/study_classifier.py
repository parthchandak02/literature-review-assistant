"""Agentic study design classifier for extraction routing."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from typing import Protocol

import aiohttp
from pydantic import BaseModel, Field, ValidationError

from src.db.repositories import WorkflowRepository
from src.llm.provider import LLMProvider
from src.models import CandidatePaper, DecisionLogEntry, ReviewConfig, StudyDesign


class StudyClassificationResult(BaseModel):
    study_design: StudyDesign
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str


class StudyClassificationLLMClient(Protocol):
    async def complete_json(
        self,
        prompt: str,
        *,
        agent_name: str,
        model: str,
        temperature: float,
    ) -> str:
        """Return a JSON string matching StudyClassificationResult."""


class GeminiStudyClassificationClient:
    """Default runtime client backed by Gemini generateContent API."""

    base_url = "https://generativelanguage.googleapis.com/v1beta/models"

    async def complete_json(
        self,
        prompt: str,
        *,
        agent_name: str,
        model: str,
        temperature: float,
    ) -> str:
        _ = agent_name
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is required for study classification client.")
        model_name = model.split(":", 1)[-1]
        url = f"{self.base_url}/{model_name}:generateContent"
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                    ]
                }
            ],
            "generationConfig": {
                "temperature": temperature,
            },
        }
        params = {"key": api_key}
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=45)) as session:
            async with session.post(url, params=params, json=payload) as response:
                if response.status != 200:
                    body = await response.text()
                    raise RuntimeError(
                        f"Gemini classification request failed: status={response.status}, body={body[:250]}"
                    )
                data = await response.json()
        candidates = data.get("candidates") or []
        if not candidates:
            raise RuntimeError("Gemini classification response had no candidates.")
        parts = candidates[0].get("content", {}).get("parts", [])
        text = "".join(str(part.get("text") or "") for part in parts).strip()
        if not text:
            raise RuntimeError("Gemini classification response had no text payload.")
        return text


class StudyClassifier:
    """Classify study design via a Pro-tier agent with typed fallback."""

    def __init__(
        self,
        provider: LLMProvider,
        repository: WorkflowRepository,
        review: ReviewConfig,
        llm_client: StudyClassificationLLMClient | None = None,
        low_confidence_threshold: float = 0.70,
        on_llm_call: Callable[..., None] | None = None,
    ):
        self.provider = provider
        self.repository = repository
        self.review = review
        self.llm_client = llm_client or GeminiStudyClassificationClient()
        self.low_confidence_threshold = low_confidence_threshold
        self.on_llm_call = on_llm_call
        # Use quality_assessment profile for single Pro-tier behavior.
        self.agent_name = "quality_assessment"

    def _build_prompt(self, paper: CandidatePaper) -> str:
        return "\n".join(
            [
                "Role: Study Design Classification Specialist",
                "Goal: Classify study design for downstream quality-assessment routing.",
                "Backstory: You support systematic reviews across changing domains and topics.",
                f"Topic: {self.review.scope}",
                f"Research Question: {self.review.research_question}",
                f"Domain: {self.review.domain}",
                f"Keywords: {', '.join(self.review.keywords)}",
                "",
                f"Paper ID: {paper.paper_id}",
                f"Title: {paper.title}",
                f"Abstract: {paper.abstract or ''}",
                "",
                "Return ONLY valid JSON matching this exact schema:",
                '{"study_design":"rct|non_randomized|cohort|case_control|qualitative|mixed_methods|cross_sectional|other","confidence":0.0,"reasoning":"..."}',
            ]
        )

    @staticmethod
    def _parse_response(raw: str) -> StudyClassificationResult | None:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return None
        try:
            return StudyClassificationResult.model_validate(payload)
        except ValidationError:
            return None

    async def classify(self, workflow_id: str, paper: CandidatePaper) -> StudyDesign:
        prompt = self._build_prompt(paper)
        runtime = await self.provider.reserve_call_slot(self.agent_name)
        started = time.perf_counter()
        raw = await self.llm_client.complete_json(
            prompt,
            agent_name=self.agent_name,
            model=runtime.model,
            temperature=runtime.temperature,
        )
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        tokens_in = max(1, len(prompt.split()))
        tokens_out = max(1, len(raw.split()))
        cost_usd = self.provider.estimate_cost(runtime.model, tokens_in, tokens_out)
        parsed = self._parse_response(raw)
        await self.provider.log_cost(
            model=runtime.model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost_usd,
            latency_ms=elapsed_ms,
            phase="phase_4_extraction_quality",
        )
        if self.on_llm_call:
            details = f"{paper.paper_id[:12]} {parsed.study_design.value}" if parsed else f"{paper.paper_id[:12]} parse_error"
            self.on_llm_call(
                source="study_type_detection",
                status="success",
                details=details,
                records=None,
                call_type="llm_classification",
                raw_response=raw,
                latency_ms=elapsed_ms,
                model=runtime.model,
                paper_id=paper.paper_id,
                phase="phase_4_extraction_quality",
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cost_usd=cost_usd,
            )
        if parsed is None:
            final_design = StudyDesign.NON_RANDOMIZED
            rationale = "Malformed classifier output. Applied non_randomized fallback."
            confidence = 0.0
            predicted = "parse_error"
        elif parsed.confidence < self.low_confidence_threshold:
            final_design = StudyDesign.NON_RANDOMIZED
            rationale = (
                f"Low confidence ({parsed.confidence:.2f} < {self.low_confidence_threshold:.2f}). "
                "Applied non_randomized fallback."
            )
            confidence = parsed.confidence
            predicted = parsed.study_design.value
        else:
            final_design = parsed.study_design
            rationale = parsed.reasoning
            confidence = parsed.confidence
            predicted = parsed.study_design.value

        await self.repository.append_decision_log(
            DecisionLogEntry(
                decision_type="study_design_classification",
                paper_id=paper.paper_id,
                decision=final_design.value,
                rationale=(
                    f"predicted={predicted}; confidence={confidence:.2f}; "
                    f"threshold={self.low_confidence_threshold:.2f}; rationale={rationale}"
                ),
                actor="study_classifier_agent",
                phase="phase_4_extraction_quality",
            )
        )
        return final_design
