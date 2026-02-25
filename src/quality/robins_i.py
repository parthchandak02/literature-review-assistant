"""ROBINS-I assessor for non-randomized studies - LLM-based with heuristic fallback."""

from __future__ import annotations

import logging
import time
from typing import Literal

from pydantic import BaseModel

from src.llm.base_client import LLMBackend
from src.llm.pydantic_client import PydanticAIClient
from src.models import ExtractionRecord, RobinsIAssessment, RobinsIJudgment
from src.models.config import SettingsConfig

logger = logging.getLogger(__name__)

_ROBINS_JUDGMENT = Literal["low", "moderate", "serious", "critical", "no_information"]


class _RobinsILLMResponse(BaseModel):
    domain_1_confounding: _ROBINS_JUDGMENT = "moderate"
    domain_1_rationale: str = ""
    domain_2_selection: _ROBINS_JUDGMENT = "moderate"
    domain_2_rationale: str = ""
    domain_3_classification: _ROBINS_JUDGMENT = "moderate"
    domain_3_rationale: str = ""
    domain_4_deviations: _ROBINS_JUDGMENT = "moderate"
    domain_4_rationale: str = ""
    domain_5_missing_data: _ROBINS_JUDGMENT = "moderate"
    domain_5_rationale: str = ""
    domain_6_measurement: _ROBINS_JUDGMENT = "moderate"
    domain_6_rationale: str = ""
    domain_7_reported_result: _ROBINS_JUDGMENT = "moderate"
    domain_7_rationale: str = ""
    overall_judgment: _ROBINS_JUDGMENT = "moderate"
    overall_rationale: str = ""


def _to_robins_judgment(value: str) -> RobinsIJudgment:
    mapping = {
        "low": RobinsIJudgment.LOW,
        "moderate": RobinsIJudgment.MODERATE,
        "serious": RobinsIJudgment.SERIOUS,
        "critical": RobinsIJudgment.CRITICAL,
        "no_information": RobinsIJudgment.NO_INFORMATION,
    }
    return mapping.get(str(value).lower(), RobinsIJudgment.MODERATE)


def _worst(values: list[RobinsIJudgment]) -> RobinsIJudgment:
    ranking = {
        RobinsIJudgment.LOW: 0,
        RobinsIJudgment.MODERATE: 1,
        RobinsIJudgment.SERIOUS: 2,
        RobinsIJudgment.CRITICAL: 3,
        RobinsIJudgment.NO_INFORMATION: 4,
    }
    return max(values, key=lambda item: ranking[item])


def _build_robins_prompt(record: ExtractionRecord, full_text: str) -> str:
    results = record.results_summary.get("summary", "")[:2000]
    text_excerpt = full_text[:3000] if full_text.strip() else results
    return "\n".join([
        "You are an expert systematic review methodologist.",
        "Assess Risk of Bias using ROBINS-I for the following non-randomized study.",
        "",
        f"Intervention: {record.intervention_description[:400]}",
        f"Comparator: {record.comparator_description or 'not reported'}",
        f"Setting: {record.setting or 'not reported'}",
        f"Participants: {record.participant_count or 'not reported'}",
        f"Results summary: {results}",
        "",
        "Text excerpt:",
        text_excerpt,
        "",
        "ROBINS-I Domains - assign 'low', 'moderate', 'serious', 'critical', or 'no_information':",
        "D1 - Confounding: Were confounders controlled? Are there major unmeasured confounders?",
        "D2 - Selection of participants: Is the selected sample representative?",
        "D3 - Classification of interventions: Were interventions classified consistently?",
        "D4 - Deviations from intended interventions: Were there protocol deviations?",
        "D5 - Missing data: Are there missing outcome or exposure data?",
        "D6 - Measurement of outcomes: Was the outcome measured without knowledge of intervention?",
        "D7 - Selection of the reported result: Was there selective reporting of outcomes?",
        "Overall: apply worst-domain logic.",
        "",
        "Return ONLY valid JSON matching the schema. Provide a 1-2 sentence rationale per domain.",
    ])


class RobinsIAssessor:
    """Assess seven ROBINS-I domains. Uses Gemini Pro when available; heuristic fallback otherwise."""

    def __init__(
        self,
        llm_client: LLMBackend | None = None,
        settings: SettingsConfig | None = None,
        provider: object | None = None,
    ):
        self.llm_client = llm_client
        self.settings = settings
        self.provider = provider

    def _heuristic(self, record: ExtractionRecord) -> RobinsIAssessment:
        """Conservative heuristic fallback when LLM call fails.

        All domains default to MODERATE (not LOW) and the assessment is
        flagged as heuristic so downstream consumers can identify these entries.
        """
        mod = RobinsIJudgment.MODERATE
        return RobinsIAssessment(
            paper_id=record.paper_id,
            domain_1_confounding=mod,
            domain_1_rationale="Heuristic fallback: LLM unavailable; conservative default applied.",
            domain_2_selection=mod,
            domain_2_rationale="Heuristic fallback: LLM unavailable; conservative default applied.",
            domain_3_classification=mod,
            domain_3_rationale="Heuristic fallback: LLM unavailable; conservative default applied.",
            domain_4_deviations=mod,
            domain_4_rationale="Heuristic fallback: LLM unavailable; conservative default applied.",
            domain_5_missing_data=mod,
            domain_5_rationale="Heuristic fallback: LLM unavailable; conservative default applied.",
            domain_6_measurement=mod,
            domain_6_rationale="Heuristic fallback: LLM unavailable; conservative default applied.",
            domain_7_reported_result=mod,
            domain_7_rationale="Heuristic fallback: LLM unavailable; conservative default applied.",
            overall_judgment=mod,
            overall_rationale="Heuristic fallback: conservative overall judgment.",
            assessment_source="heuristic",
        )

    async def assess(self, record: ExtractionRecord, full_text: str = "") -> RobinsIAssessment:
        if self.llm_client is not None and self.settings is not None:
            try:
                agent = self.settings.agents.get("quality_assessment")
                model = agent.model if agent else "google-gla:gemini-2.5-pro"
                temperature = agent.temperature if agent else 0.2
                prompt = _build_robins_prompt(record, full_text)
                schema = _RobinsILLMResponse.model_json_schema()
                t0 = time.monotonic()
                if self.provider is not None and isinstance(self.llm_client, PydanticAIClient):
                    raw, tok_in, tok_out, cw, cr = await self.llm_client.complete_with_usage(
                        prompt, model=model, temperature=temperature, json_schema=schema
                    )
                    latency_ms = int((time.monotonic() - t0) * 1000)
                    cost = self.provider.estimate_cost_usd(model, tok_in, tok_out, cw, cr)
                    await self.provider.log_cost(model, tok_in, tok_out, cost, latency_ms, phase="quality_robins_i", cache_read_tokens=cr, cache_write_tokens=cw)
                else:
                    raw = await self.llm_client.complete(
                        prompt, model=model, temperature=temperature, json_schema=schema
                    )
                parsed = _RobinsILLMResponse.model_validate_json(raw)
                return RobinsIAssessment(
                    paper_id=record.paper_id,
                    domain_1_confounding=_to_robins_judgment(parsed.domain_1_confounding),
                    domain_1_rationale=parsed.domain_1_rationale or "LLM assessment.",
                    domain_2_selection=_to_robins_judgment(parsed.domain_2_selection),
                    domain_2_rationale=parsed.domain_2_rationale or "LLM assessment.",
                    domain_3_classification=_to_robins_judgment(parsed.domain_3_classification),
                    domain_3_rationale=parsed.domain_3_rationale or "LLM assessment.",
                    domain_4_deviations=_to_robins_judgment(parsed.domain_4_deviations),
                    domain_4_rationale=parsed.domain_4_rationale or "LLM assessment.",
                    domain_5_missing_data=_to_robins_judgment(parsed.domain_5_missing_data),
                    domain_5_rationale=parsed.domain_5_rationale or "LLM assessment.",
                    domain_6_measurement=_to_robins_judgment(parsed.domain_6_measurement),
                    domain_6_rationale=parsed.domain_6_rationale or "LLM assessment.",
                    domain_7_reported_result=_to_robins_judgment(parsed.domain_7_reported_result),
                    domain_7_rationale=parsed.domain_7_rationale or "LLM assessment.",
                    overall_judgment=_to_robins_judgment(parsed.overall_judgment),
                    overall_rationale=parsed.overall_rationale or "LLM overall judgment.",
                )
            except Exception as exc:
                logger.warning(
                    "ROBINS-I LLM assessment failed for %s (%s); using heuristic.",
                    record.paper_id[:12],
                    type(exc).__name__,
                )
        return self._heuristic(record)
